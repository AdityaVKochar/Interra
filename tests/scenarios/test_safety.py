import unittest
from tests.helpers import Harness, ScriptedPlanner, spec, plan


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_write_with_different_keys(self):
        p = plan()
        a = p["tool_requests"][0]
        p["tool_requests"] = [{**a, "operation_key": "one"}, {**a, "operation_key": "two"}]
        async with Harness(ScriptedPlanner(p, p), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(effect="STATE_MODIFYING")])
            await h.text("change")
            call = await h.action("TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=call.payload["call_id"], ok=True, result={"committed": True})
            await h.runtime.input.join()
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 1)
            self.assertGreaterEqual(h.kinds().count("DUPLICATE_WRITE_BLOCKED"), 1)
            self.assertEqual(h.runtime.ledger.operations["one"].status, "COMMITTED")

    async def test_write_timeout_never_retried(self):
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(effect="STATE_MODIFYING", timeout=1., max_retries=3)])
            await h.text("change")
            call = await h.action("TOOL_CALL")
            await h.advance(1.)
            clarify = await h.action("CLARIFY")
            self.assertIn("unknown", clarify.payload["question"])
            await h.advance(20.)
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 1)
            self.assertTrue(h.runtime.ledger.uncertain)
            self.assertIn("WRITE_OUTCOME_UNKNOWN", h.kinds())

    async def test_cancelled_write_blocks_new_write_and_late_success_only_reconciles(self):
        async with Harness(ScriptedPlanner(plan(), plan("Mumbai")), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(effect="STATE_MODIFYING")])
            await h.text("change")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.text("Mumbai")
            await h.action("CLARIFY")
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 1)
            self.assertIn("WRITE_BLOCKED_UNCERTAIN", h.kinds())
            await h.send("CANCEL_ACK", call_id=old)
            self.assertTrue(h.runtime.ledger.uncertain)
            await h.send("TOOL_RESULT", call_id=old, ok=True, result={"committed": True})
            self.assertFalse(h.runtime.ledger.uncertain)
            self.assertIn("STALE_WRITE_RECONCILED", h.kinds())
            self.assertIn("STALE_RESULT_DISCARDED", h.kinds())
            self.assertFalse(h.runtime.results)
            self.assertEqual(h.runtime.state.snapshot.slots["destination"], "Mumbai")

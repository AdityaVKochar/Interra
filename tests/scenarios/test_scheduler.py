import unittest
from tests.helpers import Harness, ScriptedPlanner, spec, plan


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_chained_unseen_tools(self):
        provider = ScriptedPlanner(plan(name="opaque_721"), plan(name="opaque_983"), {"final_response": "Found"})
        async with Harness(provider, self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec("opaque_721"), spec("opaque_983")])
            await h.text("look up")
            a = await h.action("TOOL_CALL")
            self.assertEqual(a.payload["tool_name"], "opaque_721")
            await h.send("TOOL_RESULT", call_id=a.payload["call_id"], ok=True, result={"id": 17})
            b = await h.action("TOOL_CALL")
            self.assertEqual(b.payload["tool_name"], "opaque_983")
            self.assertIn(a.payload["call_id"], provider.contexts[1].results)
            await h.send("TOOL_RESULT", call_id=b.payload["call_id"], ok=True, result={"found": True})
            await h.action("FINAL")
            self.assertEqual(h.kinds().count("RESULT_ACCEPTED"), 2)

    async def test_timeout_retry_bounded(self):
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(timeout=1., max_retries=1, retry_delay=.5)])
            await h.text("lookup")
            first = await h.action("TOOL_CALL")
            await h.advance(1.)
            self.assertIn("TIMED_OUT", h.kinds())
            await h.advance(1.5)
            second = await h.action("TOOL_CALL")
            self.assertNotEqual(first.payload["call_id"], second.payload["call_id"])
            await h.advance(2.5)
            await h.action("CLARIFY")
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 2)
        self.assertEqual(h.clock.pending, 0)

    async def test_failure_retry_and_duplicate_result(self):
        async with Harness(ScriptedPlanner(plan(), {"final_response": "Found"}), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(max_retries=1, retry_delay=.5)])
            await h.text("lookup")
            first = await h.action("TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=first.payload["call_id"], ok=False, result=None, error="transient")
            await h.advance(.5)
            second = await h.action("TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=second.payload["call_id"], ok=True, result={})
            await h.action("FINAL")
            await h.send("TOOL_RESULT", call_id=second.payload["call_id"], ok=True, result={})
            self.assertIn("DUPLICATE_RESULT_DISCARDED", h.kinds())
            self.assertEqual(h.kinds().count("RESULT_ACCEPTED"), 1)

    async def test_invalid_batch_is_atomic(self):
        bad = plan()
        bad["tool_requests"].append({"tool_name": "invented", "arguments": {}})
        async with Harness(ScriptedPlanner(bad), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("lookup")
            await h.action("CLARIFY")
            self.assertFalse(h.runtime.calls)
            self.assertEqual(h.runtime.state.snapshot.version, 0)
            self.assertIn("PROPOSAL_REJECTED", h.kinds())

    async def test_unknown_tool_is_never_dispatched(self):
        invented = {
            "state_patch": {"intent": "unsupported_request"},
            "tool_requests": [{
                "tool_name": "not_in_manifest",
                "arguments": {"value": "x"},
            }],
        }
        async with Harness(ScriptedPlanner(invented), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec("available_lookup")])
            await h.text("perform an unsupported request")
            clarification = await h.action("CLARIFY")

            self.assertIn("invalid", clarification.payload["question"].lower())
            self.assertFalse(h.runtime.calls)
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 0)
            self.assertIn("PROPOSAL_REJECTED", h.kinds())

    async def test_bad_payload_does_not_kill_consumer(self):
        async with Harness(ScriptedPlanner({"clarification": "Which item?"}), self.id()) as h:
            await h.send("TEXT_CHUNK", text="x", end_of_turn="true")
            await h.text("item")
            await h.action("CLARIFY")
            self.assertIn("INPUT_REJECTED", h.kinds())

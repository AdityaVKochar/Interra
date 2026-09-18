import asyncio
import unittest
from agent.models import CallStatus
from agent.runtime import Completion
from agent.models import Proposal
from tests.helpers import Harness, ScriptedPlanner, spec, plan


def correction(value):
    proposal = plan(value)
    proposal["state_patch"]["set_slots"].pop("origin")
    return proposal


class InterruptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_boundary_matrix(self):
        # Both input insertion orders at equal timestamps are explicitly exercised.
        for offset, result_first in [(-.05, True), (-.01, True), (-.001, True),
                                     (0., True), (0., False), (.001, False), (.01, False), (.05, False)]:
            with self.subTest(offset=offset, result_first=result_first):
                responses = [plan()]
                if result_first:
                    responses.append({"final_response": "Old result before correction"})
                responses += [correction("Mumbai"), {"final_response": "Latest options"}]
                async with Harness(ScriptedPlanner(*responses), self.id()+str(offset)+str(result_first)) as h:
                    await h.send("TOOL_MANIFEST", tools=[spec()])
                    await h.text("Delhi")
                    old = (await h.action("TOOL_CALL")).payload["call_id"]
                    if result_first:
                        await h.advance(1 + offset)
                        await h.send("TOOL_RESULT", call_id=old, ok=True, result={"city": "Delhi"})
                        await h.action("FINAL")
                    await h.advance(1.)
                    await h.text("Mumbai instead")
                    new = (await h.action("TOOL_CALL")).payload["call_id"]
                    if not result_first:
                        await h.advance(1 + offset)
                        await h.send("TOOL_RESULT", call_id=old, ok=True, result={"city": "Delhi"})
                        self.assertIn("STALE_RESULT_DISCARDED", h.kinds())
                        self.assertLess(h.kinds().index("CALL_INVALIDATED"), h.kinds().index("STALE_RESULT_DISCARDED"))
                    await h.send("TOOL_RESULT", call_id=new, ok=True, result={"city": "Mumbai"})
                    final = await h.action("FINAL")
                    self.assertEqual(final.payload["state_snapshot"]["slots"], {"destination": "Mumbai", "origin": "Chennai"})
                    self.assertNotIn(old, h.runtime.results)

    async def test_rapid_corrections_and_cancel_ack(self):
        async with Harness(ScriptedPlanner(plan(), correction("Mumbai"), correction("Bengaluru")), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            ids = []
            for city in ["Delhi", "Mumbai", "Bengaluru"]:
                await h.text(city)
                ids.append((await h.action("TOOL_CALL")).payload["call_id"])
            await h.send("CANCEL_ACK", call_id=ids[0])
            self.assertEqual(h.runtime.calls[ids[0]].status, CallStatus.CANCELLED)
            for call_id in ids[:2]:
                await h.send("TOOL_RESULT", call_id=call_id, ok=True, result={})
            self.assertEqual(h.kinds().count("STALE_RESULT_DISCARDED"), 2)
            self.assertEqual(h.runtime.state.snapshot.slots["destination"], "Bengaluru")

    async def test_result_while_correction_is_reasoning(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(plan(), pending), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Delhi")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.text("Mumbai")
            await h.send("TOOL_RESULT", call_id=old, ok=True, result={"city": "Delhi"})
            self.assertIn("RESULT_PLANNING_DEFERRED", h.kinds())
            pending.set_result(correction("Mumbai"))
            await h.action("TOOL_CALL")
            self.assertNotIn(old, h.runtime.results)
            self.assertEqual(h.runtime.state.snapshot.slots["destination"], "Mumbai")

    async def test_intent_switch_and_stale_plan(self):
        switched = {"state_patch": {"intent": "support", "set_slots": {"issue": "battery"}}, "clarification": "Which device?"}
        async with Harness(ScriptedPlanner(plan(), switched), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Delhi")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            old_token = h.runtime.token
            await h.text("support instead")
            await h.action("CLARIFY")
            await h.runtime.input.put(Completion(old_token, Proposal(final_response="obsolete")))
            await h.runtime.input.join()
            await h.send("TOOL_RESULT", call_id=old, ok=True, result={})
            self.assertEqual(h.runtime.state.snapshot.slots, {"issue": "battery"})
            self.assertIn("STALE_PLAN_DISCARDED", h.kinds())
            self.assertIn("STALE_RESULT_DISCARDED", h.kinds())

    async def test_unrelated_slot_preserves_call(self):
        update = {"state_patch": {"set_slots": {"address": "home"}}}
        async with Harness(ScriptedPlanner(plan(), update, {"final_response": "Found"}), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Delhi")
            call = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.text("address home")
            # Drain a coordinator completion without imposing clock delays.
            await asyncio.sleep(0)
            await h.runtime.input.join()
            await h.send("TOOL_RESULT", call_id=call, ok=True, result={})
            final = await h.action("FINAL")
            self.assertNotIn("CALL_INVALIDATED", h.kinds())
            self.assertEqual(final.payload["state_snapshot"]["slots"]["address"], "home")

    async def test_retry_becomes_stale(self):
        async with Harness(ScriptedPlanner(plan(), correction("Mumbai")), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(max_retries=1, retry_delay=1.)])
            await h.text("Delhi")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.send("TOOL_RESULT", call_id=old, ok=False, result=None)
            await h.text("Mumbai")
            await h.action("TOOL_CALL")
            await h.advance(1.)
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 2)
            self.assertEqual(h.runtime.calls[old].status, CallStatus.STALE)

    async def test_explicit_interrupt_without_semantics(self):
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Delhi")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.send("INTERRUPTION", reason="barge in")
            await h.action("CANCEL_TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=old, ok=True, result={})
            self.assertIn("STALE_RESULT_DISCARDED", h.kinds())
            self.assertEqual(h.runtime.state.snapshot.slots["destination"], "Delhi")

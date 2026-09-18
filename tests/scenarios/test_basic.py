import unittest
from tests.helpers import Harness, ScriptedPlanner, spec, plan


class BasicTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_turn_exact_trace(self):
        async with Harness(ScriptedPlanner(plan(), {"final_response": "Found options"}), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Find Delhi")
            call = await h.action("TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=call.payload["call_id"], ok=True, result={"options": [1]})
            final = await h.action("FINAL")
            self.assertEqual(final.payload["state_snapshot"]["slots"]["destination"], "Delhi")
            self.assertEqual(h.kinds(), ["INPUT_RECEIVED", "MANIFEST_UPDATED", "INPUT_RECEIVED",
                "PLANNER_STARTED", "PROPOSAL_ACCEPTED", "STATE_UPDATED", "CALL_DISPATCHED",
                "ACTION_EMITTED", "INPUT_RECEIVED", "RESULT_ACCEPTED", "PLANNER_STARTED",
                "PROPOSAL_ACCEPTED", "ACTION_EMITTED"])
        self.assertFalse(h.runtime.tasks)

    async def test_chunks_and_invalid_model(self):
        provider = ScriptedPlanner({"unexpected": 1})
        async with Harness(provider, self.id()) as h:
            await h.send("TEXT_CHUNK", text="Find ", end_of_turn=False)
            self.assertEqual(provider.contexts, [])
            await h.text("something")
            await h.action("CLARIFY")
            self.assertEqual(provider.contexts[0].input["text"], "Find something")
            self.assertIn("PLANNER_FAILED", h.kinds())
            self.assertFalse(h.runtime.calls)

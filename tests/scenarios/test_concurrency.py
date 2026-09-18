import asyncio
import unittest

from tests.helpers import Harness, ScriptedPlanner, plan, spec


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_sessions_share_no_state_or_identifiers(self):
        async with (
            Harness(ScriptedPlanner(plan("Delhi")), "session-a") as first,
            Harness(ScriptedPlanner(plan("Mumbai")), "session-b") as second,
        ):
            await asyncio.gather(
                first.send("TOOL_MANIFEST", tools=[spec()]),
                second.send("TOOL_MANIFEST", tools=[spec()]),
            )
            await asyncio.gather(first.text("Delhi"), second.text("Mumbai"))
            first_call, second_call = await asyncio.gather(
                first.action("TOOL_CALL"),
                second.action("TOOL_CALL"),
            )

            self.assertEqual(
                first.runtime.state.snapshot.slots["destination"],
                "Delhi",
            )
            self.assertEqual(
                second.runtime.state.snapshot.slots["destination"],
                "Mumbai",
            )
            self.assertNotEqual(
                first_call.payload["call_id"],
                second_call.payload["call_id"],
            )
            self.assertTrue(first_call.payload["call_id"].startswith("session-a:"))
            self.assertTrue(second_call.payload["call_id"].startswith("session-b:"))
            self.assertNotIn(
                second_call.payload["call_id"],
                first.runtime.calls,
            )
            self.assertNotIn(
                first_call.payload["call_id"],
                second.runtime.calls,
            )

    async def test_reverse_order_results_match_call_ids(self):
        concurrent = plan("Delhi")
        concurrent["tool_requests"] = [
            {
                "tool_name": name,
                "arguments": {"value": "Delhi"},
                "bindings": {"value": "destination"},
            }
            for name in ("opaque_a", "opaque_b")
        ]
        planner = ScriptedPlanner(
            concurrent,
            {},
            {"final_response": "Both lookups completed."},
        )

        async with Harness(planner, self.id()) as h:
            await h.send(
                "TOOL_MANIFEST",
                tools=[spec("opaque_a"), spec("opaque_b")],
            )
            await h.text("Run both lookups")
            first = await h.action("TOOL_CALL")
            second = await h.action("TOOL_CALL")

            await h.send(
                "TOOL_RESULT",
                call_id=second.payload["call_id"],
                ok=True,
                result={"source": "second"},
            )
            await asyncio.sleep(0)
            await h.runtime.input.join()
            await h.send(
                "TOOL_RESULT",
                call_id=first.payload["call_id"],
                ok=True,
                result={"source": "first"},
            )
            await h.action("FINAL")

            self.assertEqual(
                planner.contexts[1].results[second.payload["call_id"]]["result"],
                {"source": "second"},
            )
            self.assertNotIn(
                first.payload["call_id"],
                planner.contexts[1].results,
            )
            self.assertEqual(set(planner.contexts[2].results), {
                first.payload["call_id"],
                second.payload["call_id"],
            })
            self.assertEqual(h.kinds().count("RESULT_ACCEPTED"), 2)

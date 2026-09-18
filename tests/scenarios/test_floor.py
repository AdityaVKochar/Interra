import asyncio
import unittest
from tests.helpers import Harness, ScriptedPlanner


class FloorTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_response_precedes_slow_planner(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(pending), self.id()) as h:
            await h.advance(2.)
            await h.text("please do something")
            speak = await h.action("SPEAK")
            self.assertEqual(speak.timestamp, 2.)
            self.assertNotIn("done", speak.payload["text"].lower())
            self.assertFalse(pending.done())
            latency = [e for e in h.runtime.trace.entries if e.kind == "FIRST_RESPONSE_LATENCY"]
            self.assertEqual(latency[0].data["latency"], 0.)
            pending.set_result({"clarification": "Which item should I check?"})
            clarify = await h.action("CLARIFY")
            self.assertEqual(clarify.payload["question"], "Which item should I check?")

    async def test_one_ack_per_chunked_turn_and_interrupt(self):
        async with Harness(ScriptedPlanner({"clarification": "Which destination?"}), self.id()) as h:
            for chunk in ["find", " a", " destination"]:
                await h.send("TEXT_CHUNK", text=chunk, end_of_turn=False)
            await h.text(" please")
            await h.action("CLARIFY")
            speaks = lambda: [e for e in h.runtime.trace.entries if e.kind == "ACTION_EMITTED" and e.data["action"]["type"] == "SPEAK"]
            self.assertEqual(len(speaks()), 1)
            await h.send("INTERRUPTION", reason="stop")
            await h.action("SPEAK")
            self.assertEqual(len(speaks()), 2)

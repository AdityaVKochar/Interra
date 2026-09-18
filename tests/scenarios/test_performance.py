import unittest

from agent.metrics import analyze_trace
from tests.helpers import Harness, ScriptedPlanner, plan, spec


class PerformanceTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_records_injected_clock_latencies(self):
        async with Harness(
            ScriptedPlanner(plan("Delhi"), plan("Mumbai")),
            self.id(),
        ) as h:
            await h.advance(1.0)
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Find Delhi options")
            await h.action("TOOL_CALL")

            await h.advance(1.25)
            await h.text("Mumbai instead")
            await h.action("CANCEL_TOOL_CALL")

            metrics = analyze_trace(h.runtime.trace.entries)
            self.assertTrue(metrics.input_queue_latencies)
            self.assertEqual(metrics.max_input_queue_latency, 0.0)
            self.assertEqual(metrics.max_first_response_latency, 0.0)
            self.assertEqual(metrics.max_cancellation_latency, 0.0)
            self.assertEqual(metrics.duplicate_operation_dispatches, 0)

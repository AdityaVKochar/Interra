import unittest

from agent.metrics import analyze_trace
from agent.models import TraceEntry


def entry(sequence, timestamp, kind, **data):
    return TraceEntry(
        session_id="s",
        timestamp=timestamp,
        trace_id=f"t{sequence}",
        kind=kind,
        data=data,
    )


class MetricsTests(unittest.TestCase):
    def test_trace_metrics_report_latency_and_safety_invariants(self):
        entries = [
            entry(1, 1.0, "INPUT_RECEIVED"),
            entry(2, 1.0, "INPUT_QUEUE_LATENCY", latency=0.0),
            entry(3, 1.1, "FIRST_RESPONSE_LATENCY", latency=0.1),
            entry(
                4,
                1.2,
                "CALL_DISPATCHED",
                call={"operation_key": "write:one"},
            ),
            entry(
                5,
                1.3,
                "CALL_DISPATCHED",
                call={"operation_key": "write:one"},
            ),
            entry(6, 1.4, "CANCEL_EMISSION_LATENCY", latency=0.2),
            entry(7, 1.5, "STALE_RESULT_DISCARDED"),
            entry(8, 1.6, "DUPLICATE_WRITE_BLOCKED"),
            entry(9, 1.7, "PLANNER_STARTED"),
            entry(10, 1.8, "STALE_PLAN_DISCARDED"),
            entry(11, 1.9, "ACTION_EMITTED", action={"type": "FINAL"}),
        ]

        metrics = analyze_trace(entries)

        self.assertEqual(metrics.events_received, 1)
        self.assertEqual(metrics.actions_emitted, 1)
        self.assertEqual(metrics.final_actions, 1)
        self.assertEqual(metrics.max_input_queue_latency, 0.0)
        self.assertEqual(metrics.max_first_response_latency, 0.1)
        self.assertEqual(metrics.max_cancellation_latency, 0.2)
        self.assertEqual(metrics.stale_results_discarded, 1)
        self.assertEqual(metrics.duplicate_writes_blocked, 1)
        self.assertEqual(metrics.duplicate_operation_dispatches, 1)
        self.assertEqual(metrics.planner_starts, 1)
        self.assertEqual(metrics.stale_plans_discarded, 1)

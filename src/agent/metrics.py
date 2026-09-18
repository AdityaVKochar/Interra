"""Deterministic local metrics derived from immutable scenario traces."""
from dataclasses import dataclass
from typing import Iterable

from .models import TraceEntry


@dataclass(frozen=True)
class RuntimeMetrics:
    events_received: int
    actions_emitted: int
    final_actions: int
    planner_starts: int
    stale_plans_discarded: int
    stale_results_discarded: int
    duplicate_writes_blocked: int
    duplicate_operation_dispatches: int
    invalid_inputs: int
    provider_failures: int
    input_queue_latencies: tuple[float, ...]
    first_response_latencies: tuple[float, ...]
    cancellation_latencies: tuple[float, ...]

    @property
    def max_input_queue_latency(self) -> float | None:
        return max(self.input_queue_latencies, default=None)

    @property
    def max_first_response_latency(self) -> float | None:
        return max(self.first_response_latencies, default=None)

    @property
    def max_cancellation_latency(self) -> float | None:
        return max(self.cancellation_latencies, default=None)


def analyze_trace(entries: Iterable[TraceEntry]) -> RuntimeMetrics:
    counts: dict[str, int] = {}
    latencies = {
        "INPUT_QUEUE_LATENCY": [],
        "FIRST_RESPONSE_LATENCY": [],
        "CANCEL_EMISSION_LATENCY": [],
    }
    operation_keys: set[str] = set()
    duplicate_operations = 0
    final_actions = 0

    for entry in entries:
        counts[entry.kind] = counts.get(entry.kind, 0) + 1
        if entry.kind in latencies:
            latencies[entry.kind].append(float(entry.data["latency"]))
        if entry.kind == "ACTION_EMITTED":
            final_actions += entry.data["action"]["type"] == "FINAL"
        if entry.kind == "CALL_DISPATCHED":
            operation_key = entry.data["call"].get("operation_key")
            if operation_key:
                duplicate_operations += operation_key in operation_keys
                operation_keys.add(operation_key)

    return RuntimeMetrics(
        events_received=counts.get("INPUT_RECEIVED", 0),
        actions_emitted=counts.get("ACTION_EMITTED", 0),
        final_actions=final_actions,
        planner_starts=counts.get("PLANNER_STARTED", 0),
        stale_plans_discarded=counts.get("STALE_PLAN_DISCARDED", 0),
        stale_results_discarded=counts.get("STALE_RESULT_DISCARDED", 0),
        duplicate_writes_blocked=counts.get("DUPLICATE_WRITE_BLOCKED", 0),
        duplicate_operation_dispatches=duplicate_operations,
        invalid_inputs=counts.get("INPUT_REJECTED", 0),
        provider_failures=(
            counts.get("PLANNER_FAILED", 0)
            + counts.get("PERCEPTION_FAILED", 0)
        ),
        input_queue_latencies=tuple(latencies["INPUT_QUEUE_LATENCY"]),
        first_response_latencies=tuple(latencies["FIRST_RESPONSE_LATENCY"]),
        cancellation_latencies=tuple(latencies["CANCEL_EMISSION_LATENCY"]),
    )

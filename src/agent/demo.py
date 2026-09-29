"""Minimal developer timeline driven by the real session runtime."""
import asyncio
from dataclasses import dataclass
from typing import Iterable

from .clock import VirtualClock
from .metrics import RuntimeMetrics, analyze_trace
from .models import Call, State, TraceEntry
from .runtime import SessionRuntime


class SequencePlanner:
    """Deterministic edge adapter for the local demo, not orchestration logic."""

    def __init__(self, proposals):
        self.proposals = list(proposals)

    async def plan(self, context):
        del context
        if not self.proposals:
            raise RuntimeError("demo planner exhausted")
        return self.proposals.pop(0)


@dataclass(frozen=True)
class DemoResult:
    trace: tuple[TraceEntry, ...]
    state: State
    calls: dict[str, Call]
    metrics: RuntimeMetrics
    rendered: str


def render_timeline(
    entries: Iterable[TraceEntry],
    state: State,
    calls: dict[str, Call],
    metrics: RuntimeMetrics,
) -> str:
    lines = ["TIME   EVENT / ACTION"]
    for entry in entries:
        detail = ""
        if entry.kind == "INPUT_RECEIVED":
            detail = entry.data["event"]["type"]
        elif entry.kind == "ACTION_EMITTED":
            action = entry.data["action"]
            detail = action["type"]
            if action["type"] in {"TOOL_CALL", "CANCEL_TOOL_CALL"}:
                detail += f" {action['payload']['call_id']}"
        elif entry.kind == "STATE_UPDATED":
            after = entry.data["after"]
            detail = f"v{after['version']} {after['slots']}"
        elif "call_id" in entry.data:
            detail = entry.data["call_id"]
        if detail or entry.kind in {
            "CALL_INVALIDATED",
            "STALE_RESULT_DISCARDED",
            "RESULT_ACCEPTED",
        }:
            lines.append(f"{entry.timestamp:5.2f}  {entry.kind} {detail}".rstrip())

    slots = " ".join(
        f"{name}={value}"
        for name, value in sorted(state.slots.items())
    )
    lines.extend([
        "",
        f"STATE  v{state.version} intent={state.intent} {slots}".rstrip(),
        "CALLS",
    ])
    for call_id, call in calls.items():
        lines.append(
            f"  {call_id} {call.request.tool_name} {call.status.value}"
        )
    lines.extend([
        "METRICS",
        f"  first_response_max={metrics.max_first_response_latency}",
        f"  cancellation_max={metrics.max_cancellation_latency}",
        f"  stale_results_discarded={metrics.stale_results_discarded}",
        f"  duplicate_operation_dispatches={metrics.duplicate_operation_dispatches}",
    ])
    return "\n".join(lines)


async def run_hero_demo() -> DemoResult:
    lookup = {
        "name": "lookup_options",
        "description": "Look up options matching a destination.",
        "argument_schema": {
            "type": "object",
            "properties": {"destination": {"type": "string"}},
            "required": ["destination"],
            "additionalProperties": False,
        },
        "effect_type": "READ_ONLY",
        "timeout": 30.0,
    }

    def search(destination):
        return {
            "state_patch": {
                "intent": "lookup_options",
                "set_slots": {
                    "origin": "Chennai",
                    "destination": destination,
                },
            },
            "tool_requests": [{
                "tool_name": lookup["name"],
                "arguments": {"destination": destination},
                "bindings": {"destination": "destination"},
            }],
        }

    planner = SequencePlanner([
        search("Delhi"),
        search("Mumbai"),
        {"final_response": "Found the current Mumbai options."},
    ])
    clock = VirtualClock()
    runtime = SessionRuntime("demo", planner, clock)
    task = asyncio.create_task(runtime.run())
    event_number = 0

    async def send(kind, **payload):
        nonlocal event_number
        event_number += 1
        await runtime.input.put({
            "event_id": f"demo-event-{event_number}",
            "session_id": runtime.session_id,
            "timestamp": clock.now(),
            "type": kind,
            "payload": payload,
        })
        await runtime.input.join()

    async def action(kind):
        async with asyncio.timeout(5):
            while True:
                candidate = await runtime.output.get()
                if candidate.type == kind:
                    return candidate

    try:
        await send("TOOL_MANIFEST", tools=[lookup])
        await send("TEXT_CHUNK", text="Find Chennai to Delhi options.", end_of_turn=True)
        old_call = await action("TOOL_CALL")

        clock.advance_to(0.5)
        await send("INTERRUPTION", reason="user_barge_in")
        await action("CANCEL_TOOL_CALL")
        await send("TEXT_CHUNK", text="Mumbai instead.", end_of_turn=True)
        new_call = await action("TOOL_CALL")

        await send(
            "TOOL_RESULT",
            call_id=old_call.payload["call_id"],
            ok=True,
            result={"destination": "Delhi"},
        )
        clock.advance_to(0.8)
        await send(
            "TOOL_RESULT",
            call_id=new_call.payload["call_id"],
            ok=True,
            result={"destination": "Mumbai"},
        )
        await action("FINAL")
    finally:
        runtime.input.put_nowait(None)
        await task

    trace = tuple(runtime.trace.entries)
    state = runtime.state.snapshot
    calls = dict(runtime.calls)
    metrics = analyze_trace(trace)
    return DemoResult(
        trace=trace,
        state=state,
        calls=calls,
        metrics=metrics,
        rendered=render_timeline(trace, state, calls, metrics),
    )


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--scenario')
    parser.add_argument('--save', type=Path, help='Save the actual runtime demonstration trace')
    args = parser.parse_args()
    if args.replay:
        from .replay import load_trace, render_replay
        print(render_replay(load_trace(args.replay, args.scenario)))
    else:
        result = asyncio.run(run_hero_demo())
        print('SCRIPTED REASONING - actual SessionRuntime, virtual timestamps; not a live model benchmark')
        print(result.rendered)
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            args.save.write_text(''.join(json.dumps(e.model_dump(mode='json')) + '\n'
                                         for e in result.trace), encoding='utf-8')


if __name__ == "__main__":
    main()

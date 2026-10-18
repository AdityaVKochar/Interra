"""Run the camera lookup and booking gate on one scripted correction.

No LiveKit room and no camera are required. The walkthrough looks up a visible
code, drops a Friday visit when the person changes the day, and stores Saturday.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.commit import CommitGate
from agent.device_catalog import DeviceDesk, GatedAction
from agent.replay import render_page


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Trace:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def append(self, kind: str, **payload: object) -> None:
        self.events.append({"kind": kind, **payload})


async def walkthrough() -> tuple[list[dict], list[dict]]:
    """Return the stored visits and the trace of executed and dropped calls."""
    clock = _Clock()
    gate = CommitGate(quiet_seconds=0.6, clock=clock)
    desk = DeviceDesk()
    trace = _Trace()
    actions = GatedAction(gate, trace, "camera-demo")

    clock.now = 0.6
    await actions.run("lookup_indicator", {"code": "E1"}, lambda: desk.lookup("E1"))

    gate.set_speaking(True)
    friday = asyncio.create_task(
        actions.run(
            "schedule_check",
            {"day": "Friday", "window": "morning"},
            lambda: desk.schedule("Friday", "morning"),
        )
    )
    await asyncio.sleep(0)
    gate.note_transcript()
    dropped = json.loads(await friday)
    if dropped.get("status") != "superseded":
        raise RuntimeError("The corrected Friday visit was stored.")

    gate.set_speaking(False)
    saturday = asyncio.create_task(
        actions.run(
            "schedule_check",
            {"day": "Saturday", "window": "morning"},
            lambda: desk.schedule("Saturday", "morning"),
        )
    )
    clock.now = 1.2
    await saturday
    listed = json.loads(await actions.run("list_scheduled_checks", {}, desk.list_visits))
    return listed["visits"], trace.events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("artifacts/extension-demo/replay.html"),
    )
    args = parser.parse_args()
    visits, events = asyncio.run(walkthrough())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_page(events, "Camera correction: Friday dropped, Saturday kept"),
        encoding="utf-8",
    )
    print(f"Visits stored: {json.dumps(visits)}")
    print(args.output)


if __name__ == "__main__":
    main()

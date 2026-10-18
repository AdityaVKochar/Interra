"""Practice catalog for the camera troubleshooting session.

These codes are Interra's own demo labels for a shown appliance. They are not
a manufacturer manual and they are not benchmark answers.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from agent.commit import SUPERSEDED, CommitGate


CATALOG: dict[str, dict[str, str]] = {
    "E1": {
        "meaning": "The door or lid is not closed.",
        "check": "Close it until it latches, then start the cycle again.",
    },
    "E2": {
        "meaning": "The drain path is blocked.",
        "check": "Clear the filter and the drain hose, then run a drain cycle.",
    },
    "E3": {
        "meaning": "Water is not reaching the machine.",
        "check": "Open the inlet and check that the hose is not kinked.",
    },
}


def normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


class DeviceDesk:
    """One session's lookups and scheduled checks. Nothing is shared across sessions."""

    def __init__(self) -> None:
        self.visits: list[dict[str, str]] = []

    def lookup(self, code: str) -> dict[str, Any]:
        key = normalize_code(code)
        row = CATALOG.get(key)
        if row is None:
            return {
                "status": "unknown",
                "code": key,
                "message": "That code is not in the demo catalog. Ask for a closer view of the display.",
            }
        return {"status": "found", "code": key, **row}

    def schedule(self, day: str, window: str) -> dict[str, Any]:
        visit = {
            "id": f"visit-{len(self.visits) + 1}",
            "day": day.strip(),
            "window": window.strip(),
        }
        self.visits.append(visit)
        return {"status": "scheduled", "visit": visit}

    def list_visits(self) -> dict[str, Any]:
        return {"status": "ok", "visits": list(self.visits)}


class GatedAction:
    """Run a session action only after the commit gate stays quiet."""

    def __init__(self, gate: CommitGate, trace: Any, room_name: str) -> None:
        self.gate = gate
        self.trace = trace
        self.room_name = room_name

    async def run(self, name: str, arguments: dict[str, Any], action: Callable[[], dict[str, Any]]) -> str:
        epoch = self.gate.epoch
        if not await self.gate.allow(epoch):
            self.trace.append(
                "tool_call_dropped",
                room=self.room_name,
                call={"function": name, "args": arguments},
                reason="user continued",
            )
            return SUPERSEDED
        result = action()
        self.trace.append(
            "tool_call",
            room=self.room_name,
            status="completed",
            call={"function": name, "args": arguments},
            result=result,
        )
        return json.dumps(result, ensure_ascii=False)

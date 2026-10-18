"""Hold a tool call until the person has stopped speaking.

A call that loses the floor is returned as superseded and is not logged.
The quiet window is short because the voice session already waits for the
turn to end before it asks for a tool.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any


SUPERSEDED = json.dumps(
    {
        "status": "superseded",
        "message": "The person kept speaking, so this call was not executed.",
    }
)


class CommitGate:
    def __init__(self, quiet_seconds: float = 0.6, clock: Any = time.monotonic) -> None:
        self.quiet_seconds = quiet_seconds
        self._clock = clock
        self.epoch = 0
        self.speaking = False
        self._quiet_since = self._clock()
        self._changed = asyncio.Event()

    def set_speaking(self, speaking: bool) -> None:
        speaking = bool(speaking)
        if speaking == self.speaking:
            return
        self.speaking = speaking
        if speaking:
            self.epoch += 1
            self._quiet_since = None
        else:
            self._quiet_since = self._clock()
        self._changed.set()

    def note_transcript(self) -> None:
        """A newer transcript invalidates a call planned on the previous words."""
        self.epoch += 1
        if not self.speaking:
            self._quiet_since = self._clock()
        self._changed.set()

    def _ready(self, epoch: int) -> bool | None:
        if self.epoch != epoch:
            return False
        if self.speaking or self._quiet_since is None:
            return None
        if self._clock() - self._quiet_since >= self.quiet_seconds:
            return self.epoch == epoch
        return None

    async def allow(self, epoch: int) -> bool:
        while True:
            ready = self._ready(epoch)
            if ready is not None:
                return ready
            self._changed.clear()
            ready = self._ready(epoch)
            if ready is not None:
                return ready
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=0.02)
            except TimeoutError:
                continue

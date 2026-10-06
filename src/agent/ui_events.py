"""Stream agent events to the live demo console over the room's data channel.

The console (``agent.demo_console``) shows what the agent is doing while it
talks: tool calls and their arguments, held turns, discarded stale results,
suppressed duplicate writes and the camera frames attached to each turn. The
agent publishes those events as JSON on the ``interra.events`` topic.

Publishing never blocks the caller and may be called from any thread: events go
into a bounded queue that one owned task drains. When the queue is full the
oldest event is dropped and counted. A failed send is counted and the loop keeps
going, so the console can never break a conversation.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

TOPIC = "interra.events"
# LiveKit recommends reliable data packets stay below about 15 KiB.
MAX_PACKET_BYTES = 14_000


def encode_event(kind: str, payload: dict[str, Any]) -> bytes:
    """JSON-encode one event; drop the optional thumbnail if the packet is too large."""
    record = {"kind": kind, "time": payload.pop("time", time.time()), **payload}
    data = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
    if len(data) > MAX_PACKET_BYTES and "thumbnail" in record:
        record.pop("thumbnail")
        record["thumbnail_dropped"] = True
        data = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
    if len(data) > MAX_PACKET_BYTES:
        record = {"kind": kind, "time": record["time"], "truncated": True}
        data = json.dumps(record).encode("utf-8")
    return data


class RoomEventPublisher:
    """Own one task that publishes queued events to a LiveKit room."""

    def __init__(self, room: Any, *, max_queue: int = 500) -> None:
        self._room = room
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(max_queue)
        self._task: asyncio.Task[None] | None = None
        self.dropped = 0
        self.failed = 0
        self.sent = 0

    def start(self) -> None:
        if self._task is None:
            self._task = self._loop.create_task(self._run(), name="interra-ui-events")

    def publish(self, kind: str, **payload: Any) -> None:
        """Queue one event. Safe to call from any thread; never blocks."""
        data = encode_event(kind, payload)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._put(data)
        else:
            self._loop.call_soon_threadsafe(self._put, data)

    def forward(self, record: dict[str, Any]) -> None:
        """Adapter for ``TraceWriter`` listeners: forward a trace record as an event."""
        record = dict(record)
        self.publish(str(record.pop("kind", "event")), **record)

    def _put(self, data: bytes) -> None:
        if self._queue.full():
            self._queue.get_nowait()
            self.dropped += 1
        self._queue.put_nowait(data)

    async def _run(self) -> None:
        while True:
            data = await self._queue.get()
            try:
                await self._room.local_participant.publish_data(data, reliable=True, topic=TOPIC)
                self.sent += 1
            except Exception:  # a console that is not listening must not stop the agent
                self.failed += 1

    async def aclose(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

import asyncio
import heapq
import itertools
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...


class RealClock:
    def now(self) -> float:
        return asyncio.get_running_loop().time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class VirtualClock:
    """Explicit advancement; insertion order breaks equal-deadline ties."""
    def __init__(self):
        self._now = 0.0
        self._sequence = itertools.count()
        self._waiters = []

    def now(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("negative delay")
        future = asyncio.get_running_loop().create_future()
        entry = (self._now + seconds, next(self._sequence), future)
        heapq.heappush(self._waiters, entry)
        try:
            await future
        finally:
            if entry in self._waiters:
                self._waiters.remove(entry)
                heapq.heapify(self._waiters)

    def advance_to(self, timestamp: float) -> None:
        if timestamp < self._now:
            raise ValueError("clock cannot go backwards")
        self._now = timestamp
        while self._waiters and self._waiters[0][0] <= timestamp:
            _, _, future = heapq.heappop(self._waiters)
            if not future.done():
                future.set_result(None)

    @property
    def pending(self) -> int:
        return len(self._waiters)

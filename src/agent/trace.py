from copy import deepcopy
import json
from pathlib import Path

from .models import TraceEntry


class IDs:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.sequence = 0

    def new(self, prefix: str) -> str:
        self.sequence += 1
        return f"{self.session_id}:{prefix}:{self.sequence}"


class TraceRecorder:
    def __init__(self, session_id, clock, ids):
        self.session_id, self.clock, self.ids = session_id, clock, ids
        self._entries = []

    @property
    def entries(self):
        return deepcopy(self._entries)

    def record(self, kind, **data):
        entry = TraceEntry(session_id=self.session_id, timestamp=self.clock.now(),
                           trace_id=self.ids.new("trace"), kind=kind, data=deepcopy(data))
        self._entries.append(entry)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e.model_dump(mode="json"), allow_nan=False)
                                + "\n" for e in self._entries), encoding="utf-8")

"""Both demo agents can run at once: the benchmark agent declines camera-extension rooms.

Regression: live rehearsal 2026-10-06. The benchmark agent is auto-dispatched to every
new room, so it also joined the camera troubleshooter's rooms and had to be stopped
mid-recording between the two demo parts.
"""
import sys
import unittest
from pathlib import Path

from agent.fdb_livekit import accepts_room, on_job_request
from agent.troubleshooting import EXTENSION_ROOM_PREFIX

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import demo_room  # noqa: E402


class FakeRoom:
    def __init__(self, name):
        self.name = name


class FakeJobRequest:
    def __init__(self, room_name):
        self.room = FakeRoom(room_name)
        self.decision = None

    async def accept(self):
        self.decision = "accept"

    async def reject(self):
        self.decision = "reject"


class RoomRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_benchmark_rooms_are_joined(self):
        # The official recorder names rooms itself; the console uses interra-demo-*.
        for name in ("fdb-v3-travel_07-abc", "interra-demo-1a2b3c4d", "any-room"):
            request = FakeJobRequest(name)
            await on_job_request(request)
            self.assertEqual(request.decision, "accept", name)

    async def test_camera_extension_rooms_are_declined(self):
        request = FakeJobRequest(f"{EXTENSION_ROOM_PREFIX}1a2b3c4d")
        await on_job_request(request)
        self.assertEqual(request.decision, "reject")
        self.assertFalse(accepts_room(f"{EXTENSION_ROOM_PREFIX}x"))

    def test_room_creators_use_the_same_prefix(self):
        self.assertEqual(demo_room.EXTENSION_ROOM_PREFIX, EXTENSION_ROOM_PREFIX)


if __name__ == "__main__":
    unittest.main()

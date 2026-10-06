"""Extension tools: stale lookups are discarded, cancellations propagate, writes never repeat."""
import asyncio
import json
import unittest

from agent.extension_livekit import TroubleshootingTools, frame_thumbnail
from agent.troubleshooting import TicketDesk, TurnGuard


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, kind, **payload):
        self.events.append((kind, payload))

    def kinds(self):
        return [kind for kind, _ in self.events]


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def make(self, sleep=None):
        self.guard = TurnGuard()
        self.guard.advance("first turn")
        self.events = Recorder()
        ids = iter(f"T-00000{i}" for i in range(1, 9))
        desk = TicketDesk(None, new_id=lambda: next(ids))
        return TroubleshootingTools(desk, self.guard, self.events, lookup_seconds=0.0,
                                    sleep=sleep or (lambda _s: asyncio.sleep(0)))

    async def test_current_lookup_answers(self):
        tools = self.make()
        result = json.loads(await tools.look_up_fix("router", "internet light is off"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.events.kinds(), ["tool_started", "tool_finished"])

    async def test_lookup_finishing_after_a_correction_is_discarded(self):
        async def correction_arrives(_seconds):
            self.guard.advance("correction while a tool was running")

        tools = self.make(sleep=correction_arrives)
        result = json.loads(await tools.look_up_fix("router", "no power"))
        self.assertEqual(result["status"], "discarded")
        self.assertEqual(self.events.kinds(), ["tool_started", "stale_result_discarded"])
        stale = self.events.events[1][1]
        self.assertEqual((stale["request_version"], stale["current_version"]), (1, 2))

    async def test_cancelled_lookup_is_reported_and_not_swallowed(self):
        started = asyncio.Event()

        async def slow(_seconds):
            started.set()
            await asyncio.sleep(10)

        tools = self.make(sleep=slow)
        task = asyncio.create_task(tools.look_up_fix("printer", "paper jam"))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events.kinds(), ["tool_started", "tool_cancelled"])

    async def test_repeated_ticket_request_does_not_open_a_second_ticket(self):
        tools = self.make()
        first = json.loads(await tools.open_support_ticket("router", "no internet", "restarted"))
        second = json.loads(await tools.open_support_ticket("router", "no internet", "asked twice"))
        self.assertEqual((first["status"], second["status"]), ("created", "already_open"))
        self.assertEqual(first["ticket_id"], second["ticket_id"])
        self.assertIn("duplicate_write_suppressed", self.events.kinds())

    async def test_cancel_is_idempotent_and_unknown_ids_are_reported(self):
        tools = self.make()
        ticket = json.loads(await tools.open_support_ticket("router", "no internet", "s"))["ticket_id"]
        self.assertEqual(json.loads(await tools.cancel_support_ticket(ticket, "wrong device"))["status"], "cancelled")
        self.assertEqual(json.loads(await tools.cancel_support_ticket(ticket, "again"))["status"], "already_cancelled")
        self.assertEqual(json.loads(await tools.cancel_support_ticket("T-404", "x"))["status"], "not_found")

    async def test_interrupted_write_is_skipped_visibly(self):
        tools = self.make()
        result = json.loads(tools.write_skipped("open_support_ticket", {"device": "router"}))
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(self.events.kinds(), ["write_skipped"])
        self.assertEqual(tools.desk.tickets(), [])


class ThumbnailTests(unittest.TestCase):
    def test_frame_thumbnail_is_a_small_jpeg(self):
        import base64
        from livekit import rtc

        frame = rtc.VideoFrame(640, 480, rtc.VideoBufferType.RGBA, bytes([20, 120, 220, 255]) * (640 * 480))
        data = base64.b64decode(frame_thumbnail(frame))
        self.assertEqual(data[:2], b"\xff\xd8")
        self.assertLess(len(data), 10_000)

    def test_unencodable_frame_gives_no_thumbnail(self):
        self.assertIsNone(frame_thumbnail(object()))


if __name__ == "__main__":
    unittest.main()

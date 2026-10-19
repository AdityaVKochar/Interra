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


class SpeechDuringLookupTests(unittest.IsolatedAsyncioTestCase):
    """Regression: live run 2026-10-06. The person said "wait, it's not the router" while the
    router lookup ran; LiveKit paused the reply, the lookup finished as "ok" and its output was
    committed to the chat history before the reply was interrupted."""

    def make(self):
        self.guard = TurnGuard()
        self.guard.advance("first turn")
        self.events = Recorder()
        self.release = asyncio.Event()
        self.started = asyncio.Event()

        async def lookup_latency(_seconds):
            self.started.set()
            await self.release.wait()

        return TroubleshootingTools(TicketDesk(None), self.guard, self.events, sleep=lookup_latency)

    async def test_speech_during_a_lookup_discards_its_result(self):
        tools = self.make()
        task = asyncio.create_task(tools.look_up_fix("router", "internet light is off"))
        await self.started.wait()
        self.assertEqual(tools.supersede_running_lookups("person spoke"), 2)
        self.release.set()
        result = json.loads(await task)
        self.assertEqual(result["status"], "discarded")
        self.assertNotIn("checks", result)  # the old answer never reaches the chat history
        self.assertEqual(self.events.kinds(), ["tool_started", "stale_result_discarded"])
        stale = self.events.events[1][1]
        self.assertEqual((stale["request_version"], stale["current_version"]), (1, 2))

    async def test_one_utterance_supersedes_a_lookup_once(self):
        tools = self.make()
        task = asyncio.create_task(tools.look_up_fix("router", "no internet"))
        await self.started.wait()
        self.assertEqual(tools.supersede_running_lookups("speech started"), 2)
        self.assertIsNone(tools.supersede_running_lookups("final transcript"))
        self.release.set()
        await task
        self.assertEqual(self.guard.version, 2)

    async def test_speech_without_a_running_lookup_changes_nothing(self):
        tools = self.make()
        self.assertIsNone(tools.supersede_running_lookups("backchannel"))
        self.assertEqual(self.guard.version, 1)
        self.assertEqual(self.events.kinds(), [])

    async def test_lookup_repeated_after_a_discard_answers(self):
        tools = self.make()
        first = asyncio.create_task(tools.look_up_fix("router", "no internet"))
        await self.started.wait()
        tools.supersede_running_lookups("false start")
        self.release.set()
        self.assertEqual(json.loads(await first)["status"], "discarded")
        self.assertEqual(json.loads(await tools.look_up_fix("router", "no internet"))["status"], "ok")

    async def test_cancelled_lookup_is_no_longer_running(self):
        tools = self.make()
        task = asyncio.create_task(tools.look_up_fix("router", "no internet"))
        await self.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(tools.supersede_running_lookups("speech after cancel"))


class FakeSpeechHandle:
    def __init__(self):
        self.allow_interruptions = True


class FakeRunContext:
    def __init__(self, interrupted=False):
        self.speech_handle = FakeSpeechHandle()
        self.interrupted = interrupted

    def disallow_interruptions(self):
        if self.interrupted:
            raise RuntimeError("Cannot set allow_interruptions to False, the SpeechHandle is already interrupted")
        self.speech_handle.allow_interruptions = False


class ScopedWriteTests(unittest.IsolatedAsyncioTestCase):
    """Regression: live run 2026-10-06. disallow_interruptions() left the whole confirmation
    uninterruptible, LiveKit fed silence to STT meanwhile, and "Open the ticket please" was lost."""

    def make(self):
        self.events = Recorder()
        return TroubleshootingTools(TicketDesk(None), TurnGuard(), self.events)

    async def test_interruptions_are_held_only_while_the_write_runs(self):
        tools = self.make()
        context = FakeRunContext()
        during = []

        async def write():
            during.append(context.speech_handle.allow_interruptions)
            return await tools.open_support_ticket("power strip", "no power", "switch light off")

        result = json.loads(await tools.write_without_interruption(context, "open_support_ticket", {}, write))
        self.assertEqual(result["status"], "created")
        self.assertEqual(during, [False])
        self.assertTrue(context.speech_handle.allow_interruptions)

    async def test_failed_write_still_allows_interruptions_again(self):
        tools = self.make()
        context = FakeRunContext()

        async def write():
            raise OSError("journal unavailable")

        with self.assertRaises(OSError):
            await tools.write_without_interruption(context, "open_support_ticket", {}, write)
        self.assertTrue(context.speech_handle.allow_interruptions)

    async def test_write_on_an_interrupted_turn_is_skipped(self):
        tools = self.make()
        context = FakeRunContext(interrupted=True)

        async def write():
            raise AssertionError("must not run")

        result = json.loads(await tools.write_without_interruption(context, "open_support_ticket", {"device": "x"}, write))
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

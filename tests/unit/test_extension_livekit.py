"""Camera frame lifecycle regressions without requiring a LiveKit connection."""

import asyncio
import inspect
import pickle
import unittest
from types import SimpleNamespace

from agent.extension_livekit import (
    EXTENSION_INSTRUCTIONS, LatestFrameSource, entrypoint, camera_matches, clear_previous_images,
)


class FakeStream:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[object] = asyncio.Queue()
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return SimpleNamespace(frame=item)

    async def aclose(self) -> None:
        self.closed = True
        await self.queue.put(None)


class ExtensionLiveKitTests(unittest.IsolatedAsyncioTestCase):
    async def test_frame_is_consumed_once_and_new_track_discards_old_frame(self):
        frames = LatestFrameSource()
        first, second = FakeStream(), FakeStream()
        frames.attach(first)
        await first.queue.put("old frame")
        await asyncio.sleep(0)
        self.assertEqual(frames.take(), "old frame")
        self.assertIsNone(frames.take())

        await first.queue.put("stale frame")
        await asyncio.sleep(0)
        frames.attach(second)
        self.assertIsNone(frames.take())
        await second.queue.put("current frame")
        await asyncio.sleep(0)
        self.assertEqual(frames.take(), "current frame")
        await frames.close()
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertTrue(all(task.done() for task in frames._tasks))

    async def test_sources_are_session_scoped(self):
        first, second = LatestFrameSource(), LatestFrameSource()
        first_stream, second_stream = FakeStream(), FakeStream()
        first.attach(first_stream)
        second.attach(second_stream)
        await first_stream.queue.put("session one")
        await asyncio.sleep(0)
        self.assertEqual(first.take(), "session one")
        self.assertIsNone(second.take())
        await first.close()
        await second.close()

    def test_livekit_entrypoint_and_image_turn_hook_are_present(self):
        self.assertEqual(entrypoint.__qualname__, "entrypoint")
        pickle.dumps(entrypoint)
        source = inspect.getsource(entrypoint)
        self.assertIn('ctx.add_shutdown_callback(frames.close)', source)
        self.assertIn('content.append(llm.ImageContent(image=frame))', source)
        self.assertIn('ctx.room.on("track_subscribed"', source)
        self.assertIn("latest frame", EXTENSION_INSTRUCTIONS)
        self.assertNotIn("search_flights", source)
        self.assertNotIn("benchmark", EXTENSION_INSTRUCTIONS.lower())

    async def test_newer_frame_replaces_an_unconsumed_frame(self):
        frames = LatestFrameSource()
        stream = FakeStream()
        frames.attach(stream)
        await stream.queue.put("before correction")
        await stream.queue.put("after correction")
        for _ in range(5):
            await asyncio.sleep(0)
        self.assertEqual(frames.take(), "after correction")
        await frames.close()

    async def test_closed_source_rejects_a_new_track(self):
        frames = LatestFrameSource()
        await frames.close()
        with self.assertRaises(RuntimeError):
            frames.attach(FakeStream())

    async def test_disconnect_discards_unconsumed_frame(self):
        frames = LatestFrameSource()
        stream = FakeStream()
        frames.attach(stream)
        await stream.queue.put("before camera stopped")
        await asyncio.sleep(0)
        frames.detach()
        self.assertIsNone(frames.take())
        await frames.close()
        self.assertTrue(stream.closed)

    async def test_close_failure_still_awaits_reader_and_other_streams(self):
        class BrokenStream(FakeStream):
            async def aclose(self):
                raise RuntimeError("camera close failed")
        frames = LatestFrameSource()
        first, second = FakeStream(), BrokenStream()
        frames.attach(first)
        frames.attach(second)
        with self.assertRaisesRegex(RuntimeError, "camera close failed"):
            await frames.close()
        self.assertTrue(first.closed)
        self.assertTrue(frames._reader_task.done())
        self.assertFalse(frames._tasks)

    async def test_concurrent_close_calls_both_wait_for_cleanup(self):
        gate = asyncio.Event()
        class SlowStream(FakeStream):
            async def aclose(self):
                await gate.wait()
                await super().aclose()
        frames = LatestFrameSource()
        stream = SlowStream()
        frames.attach(stream)
        first = asyncio.create_task(frames.close())
        second = asyncio.create_task(frames.close())
        for _ in range(4):
            await asyncio.sleep(0)
        self.assertFalse(first.done())
        self.assertFalse(second.done())
        gate.set()
        await asyncio.gather(first, second)
        self.assertTrue(stream.closed)

    def test_camera_is_limited_to_linked_participant_and_camera_source(self):
        participant = SimpleNamespace(identity="speaker")
        camera = SimpleNamespace(source="camera")
        screen = SimpleNamespace(source="screen")
        self.assertTrue(camera_matches(participant, camera, "speaker", "camera"))
        self.assertFalse(camera_matches(participant, camera, "other", "camera"))
        self.assertFalse(camera_matches(participant, screen, "speaker", "camera"))

    def test_old_visual_evidence_is_removed_but_text_is_preserved(self):
        class Image:
            pass
        message = SimpleNamespace(content=["old words", Image()])
        tool = SimpleNamespace(output="grounded result")
        context = SimpleNamespace(items=[message, tool])
        clear_previous_images(context, Image)
        self.assertEqual(message.content, ["old words"])
        self.assertEqual(tool.output, "grounded result")


if __name__ == "__main__":
    unittest.main()

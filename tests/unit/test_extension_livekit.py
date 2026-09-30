"""Camera frame lifecycle regressions without requiring a LiveKit connection."""

import asyncio
import inspect
import pickle
import unittest
from types import SimpleNamespace

from agent.extension_livekit import EXTENSION_INSTRUCTIONS, LatestFrameSource, entrypoint


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


if __name__ == "__main__":
    unittest.main()

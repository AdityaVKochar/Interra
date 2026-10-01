"""Session cleanup must preserve playout and release jobs after disconnect."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from agent.fdb_livekit import run_session_lifecycle


class Emitter:
    def __init__(self):
        self.handlers = {}

    def on(self, name, callback):
        self.handlers.setdefault(name, []).append(callback)

    def off(self, name, callback):
        self.handlers[name].remove(callback)

    def emit(self, name, event):
        for callback in list(self.handlers.get(name, [])):
            callback(event)


class FdbLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.room = Emitter()
        self.room.name = "test-room"
        self.ctx = SimpleNamespace(room=self.room, shutdown=Mock())
        self.session = Emitter()
        self.started = asyncio.Event()

        async def start(**kwargs):
            self.started.set()

        self.session.start = AsyncMock(side_effect=start)
        self.session.drain = AsyncMock()
        self.session.aclose = AsyncMock()
        self.trace = Mock()

    async def run_lifecycle(self):
        await run_session_lifecycle(
            self.ctx, self.session, object(), object(), self.trace,
            participant_identity="recorder",
        )

    def kinds(self):
        return [call.args[0] for call in self.trace.append.call_args_list]

    def assert_cleaned(self):
        self.session.aclose.assert_awaited_once()
        self.ctx.shutdown.assert_called_once()
        self.assertFalse(any(self.room.handlers.values()))
        self.assertFalse(any(self.session.handlers.values()))
        self.assertIn("session_cleanup", self.kinds())
        self.assertFalse(any(
            task.get_name().startswith("interra-") for task in asyncio.all_tasks()
        ))

    async def test_disconnect_waits_for_pending_playout_then_cleans_up(self):
        draining = asyncio.Event()
        playout_done = asyncio.Event()

        async def drain():
            draining.set()
            await playout_done.wait()

        self.session.drain.side_effect = drain
        task = asyncio.create_task(self.run_lifecycle())
        await self.started.wait()
        self.room.emit("participant_disconnected", SimpleNamespace(identity="recorder"))
        # Duplicate disconnects must not create duplicate cleanup tasks.
        self.room.emit("participant_disconnected", SimpleNamespace(identity="recorder"))
        await draining.wait()
        self.session.aclose.assert_not_awaited()
        playout_done.set()
        await task
        self.session.drain.assert_awaited_once()
        self.assertEqual(self.kinds(), [
            "participant_disconnected", "session_drain_started",
            "session_drain_completed", "session_cleanup",
        ])
        self.assert_cleaned()

    async def test_unrelated_participant_does_not_end_session(self):
        task = asyncio.create_task(self.run_lifecycle())
        await self.started.wait()
        self.room.emit("participant_disconnected", SimpleNamespace(identity="observer"))
        self.assertFalse(task.done())
        self.assertNotIn("participant_disconnected", self.kinds())
        self.room.emit("participant_disconnected", SimpleNamespace(identity="recorder"))
        await task
        self.assert_cleaned()

    async def test_provider_failure_releases_session_without_drain(self):
        task = asyncio.create_task(self.run_lifecycle())
        await self.started.wait()
        self.session.emit("close", SimpleNamespace(reason="error", error=RuntimeError("429")))
        await task
        self.session.drain.assert_not_awaited()
        self.assertEqual(self.kinds(), ["session_closed", "session_cleanup"])
        self.assertTrue(self.trace.append.call_args_list[0].kwargs["failed"])
        self.assert_cleaned()

    async def test_drain_timeout_forces_cleanup(self):
        task = asyncio.create_task(self.run_lifecycle())
        await self.started.wait()
        self.room.emit("participant_disconnected", SimpleNamespace(identity="recorder"))

        async def timeout(awaitable, *, timeout):
            await awaitable
            raise TimeoutError

        with patch("agent.fdb_livekit.asyncio.wait_for", side_effect=timeout):
            await task
        self.assertIn("session_drain_timeout", self.kinds())
        self.assert_cleaned()

    async def test_cancel_propagates_and_cleans_owned_tasks(self):
        task = asyncio.create_task(self.run_lifecycle())
        await self.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_cleaned()

    async def test_start_failure_still_cleans_up(self):
        self.session.start.side_effect = RuntimeError("start failed")
        with self.assertRaisesRegex(RuntimeError, "start failed"):
            await self.run_lifecycle()
        self.assert_cleaned()

    async def test_provider_cooldown_finishes_before_worker_shutdown(self):
        order = []
        self.ctx.shutdown = Mock(side_effect=lambda **_: order.append("shutdown"))

        async def close_after_start(**_):
            self.started.set()
            asyncio.get_running_loop().call_soon(
                self.session.emit,
                "close",
                SimpleNamespace(reason="completed", error=None),
            )

        self.session.start.side_effect = close_after_start

        async def cooldown(seconds):
            order.append(("cooldown", seconds))

        with patch("agent.fdb_livekit.asyncio.sleep", side_effect=cooldown) as sleep:
            await run_session_lifecycle(
                self.ctx, self.session, object(), object(), self.trace,
                participant_identity="recorder", cooldown_seconds=3.0,
            )

        sleep.assert_awaited_once_with(3.0)
        self.assertEqual(order, [("cooldown", 3.0), "shutdown"])
        self.assertIn("provider_cooldown_started", self.kinds())
        self.assertIn("provider_cooldown_completed", self.kinds())
        self.assert_cleaned()

    async def test_cancellation_during_provider_cooldown_still_shuts_down(self):
        async def close_after_start(**_):
            self.started.set()
            self.session.emit(
                "close", SimpleNamespace(reason="completed", error=None)
            )

        self.session.start.side_effect = close_after_start
        sleep_started = asyncio.Event()

        async def blocked_sleep(_seconds):
            sleep_started.set()
            await asyncio.Event().wait()

        with patch("agent.fdb_livekit.asyncio.sleep", side_effect=blocked_sleep):
            task = asyncio.create_task(
                run_session_lifecycle(
                    self.ctx, self.session, object(), object(), self.trace,
                    participant_identity="recorder", cooldown_seconds=3.0,
                )
            )
            await self.started.wait()
            await sleep_started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.ctx.shutdown.assert_called_once()
        self.assertIn("session_cleanup", self.kinds())

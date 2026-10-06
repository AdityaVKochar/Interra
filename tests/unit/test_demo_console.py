"""Demo console server: keys stay server-side, recordings are validated, playback is owned."""
import asyncio
import json
import os
import tempfile
import textwrap
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from agent import demo_console

ENV = {"LIVEKIT_URL": "wss://example.livekit.cloud", "LIVEKIT_API_KEY": "key-for-tests",
       "LIVEKIT_API_SECRET": "secret-for-tests-that-is-long-enough"}

FAKE_RECORDER = textwrap.dedent("""\
    import argparse, json, os, time
    parser = argparse.ArgumentParser()
    parser.add_argument("-i"); parser.add_argument("-o"); parser.add_argument("--room")
    args = parser.parse_args()
    open(args.o, "wb").write(b"RIFF")
    with open(os.environ["INTERRA_FDB_TRACE_DIR"] + "/livekit-agent.jsonl", "a") as handle:
        handle.write(json.dumps({"room": args.room, "kind": "tool_call", "status": "completed",
                                 "call": {"function": "track_order", "args": {"order_id": "X1"}},
                                 "result": {"status": "success"}}) + "\\n")
    print("streamed", args.room)
""")


def write_wav(path: Path, seconds: float = 0.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * int(16000 * seconds))


class ConsoleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        v3 = root / "v3"
        data = v3 / "fdb_v3_data_released"
        write_wav(data / "travel_07_aaaa1111" / "input.wav", 1.5)
        write_wav(data / "shop_01_bbbb2222" / "input.wav")
        (v3 / "benchmark_data_v2.json").write_text(json.dumps({"scenarios": [
            {"id": "travel_07", "title": "Update passport", "domain": "travel", "difficulty": "easy",
             "disfluency_features": ["SELF_CORRECTION"], "state_rollback_test": True, "num_expected_calls": 1,
             "expected_tool_calls": [{"function": "update_identity_doc", "args": {"doc_number": "SECRET123"}}]},
            {"id": "shop_01", "title": "Track", "disfluency_features": [], "expected_tool_calls": []},
        ]}))
        (v3 / "livekit_inference.py").write_text(FAKE_RECORDER)
        (root / "traces").mkdir()
        self.env = patch.dict(os.environ, {**ENV, "INTERRA_FDB_V3_ROOT": str(v3),
                                           "INTERRA_FDB_DATA_ROOT": str(data),
                                           "INTERRA_FDB_TRACE_DIR": str(root / "traces")})
        self.env.start()
        self.client = TestClient(TestServer(demo_console.create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.env.stop()
        self.directory.cleanup()

    async def test_config_lists_recordings_without_expected_answers(self):
        body = await (await self.client.get("/api/config")).json()
        self.assertEqual(body["missing_credentials"], [])
        names = [row["name"] for row in body["recordings"]]
        self.assertEqual(names[0], "travel_07_aaaa1111")  # self-corrections first
        self.assertAlmostEqual(body["recordings"][0]["seconds"], 1.5, places=2)
        self.assertNotIn("SECRET123", json.dumps(body))
        self.assertNotIn("secret-for-tests", json.dumps(body))

    async def test_benchmark_session_is_a_hidden_listener(self):
        from livekit import api

        body = await (await self.client.post("/api/session", json={"mode": "benchmark"})).json()
        grants = api.TokenVerifier(ENV["LIVEKIT_API_KEY"], ENV["LIVEKIT_API_SECRET"]).verify(body["token"]).video
        self.assertTrue(body["room"].startswith("interra-demo-"))
        self.assertTrue(grants.hidden)
        self.assertFalse(grants.can_publish)

    async def test_camera_session_dispatches_the_troubleshooter(self):
        with patch.object(demo_console, "dispatch_camera_agent", AsyncMock()) as dispatch:
            body = await (await self.client.post("/api/session", json={"mode": "camera"})).json()
        dispatch.assert_awaited_once_with(body["room"])
        self.assertTrue(body["room"].startswith("interra-camera-"))

    async def test_missing_credentials_are_reported(self):
        with patch.dict(os.environ, {"LIVEKIT_API_SECRET": ""}):
            response = await self.client.post("/api/session", json={"mode": "camera"})
        self.assertEqual(response.status, 400)

    async def test_playback_runs_the_recorder_and_reports_trace_tool_calls(self):
        room = "interra-demo-test0001"
        started = await self.client.post("/api/benchmark/play", json={"room": room, "recording": "travel_07_aaaa1111"})
        self.assertEqual(started.status, 200)
        for _ in range(100):
            status = await (await self.client.get(f"/api/benchmark/status?room={room}")).json()
            if status["state"] != "playing":
                break
            await asyncio.sleep(0.05)
        self.assertEqual(status["state"], "done")
        self.assertEqual(status["tool_calls"][0]["function"], "track_order")

    async def test_recording_names_cannot_escape_the_data_folder(self):
        for name in ("../v3", "travel_07_aaaa1111/../../x", "missing_recording"):
            response = await self.client.post("/api/benchmark/play", json={"room": "interra-demo-x", "recording": name})
            self.assertEqual(response.status, 404, name)
        bad_room = await self.client.post("/api/benchmark/play", json={"room": "other", "recording": "shop_01_bbbb2222"})
        self.assertEqual(bad_room.status, 400)

    async def test_index_and_static_files_are_served(self):
        self.assertIn("Interra live console", await (await self.client.get("/")).text())
        self.assertEqual((await self.client.get("/static/app.js")).status, 200)


if __name__ == "__main__":
    unittest.main()

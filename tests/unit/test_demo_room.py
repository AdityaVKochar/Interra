"""Demo-room helper: watch links stay invisible to agents; traces are filtered by room."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import demo_room  # noqa: E402

ENV = {"LIVEKIT_URL": "wss://example.livekit.cloud", "LIVEKIT_API_KEY": "key-for-tests",
       "LIVEKIT_API_SECRET": "secret-for-tests-that-is-long-enough"}


class DemoRoomTests(unittest.TestCase):
    def grants(self, link):
        from livekit import api

        query = parse_qs(urlparse(link).query)
        self.assertEqual(query["liveKitUrl"], [ENV["LIVEKIT_URL"]])
        return api.TokenVerifier(ENV["LIVEKIT_API_KEY"], ENV["LIVEKIT_API_SECRET"]).verify(query["token"][0]).video

    def test_watch_link_is_hidden_and_cannot_publish(self):
        # The benchmark agent links to the first visible participant; a viewer must not be it.
        with patch.dict(os.environ, ENV):
            video = self.grants(demo_room.join_link("room-a", "viewer", hidden=True))
        self.assertEqual(video.room, "room-a")
        self.assertTrue(video.hidden)
        self.assertFalse(video.can_publish)
        self.assertTrue(video.can_subscribe)

    def test_camera_link_can_publish_camera_and_microphone(self):
        with patch.dict(os.environ, ENV):
            video = self.grants(demo_room.join_link("room-b", "demo-user", hidden=False))
        self.assertFalse(video.hidden)
        self.assertTrue(video.can_publish)

    def test_missing_credentials_stop_before_any_link(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            demo_room.join_link("room", "viewer", hidden=True)

    def test_folder_names_map_to_scenarios(self):
        self.assertEqual(demo_room.scenario_id("travel_07_5ff07b5ee7a1d23e719e421e"), "travel_07")

    def test_tool_calls_are_read_for_one_room_only(self):
        with tempfile.TemporaryDirectory() as directory:
            events = [
                {"room": "a", "kind": "tool_call", "call": {"function": "track_order", "args": {"order_id": "X1"}}},
                {"room": "b", "kind": "tool_call", "call": {"function": "search_flights", "args": {}}},
                {"room": "a", "kind": "transcript", "transcript": "hi"},
            ]
            Path(directory, "livekit-agent.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            with patch.dict(os.environ, {"INTERRA_FDB_TRACE_DIR": directory}):
                calls = demo_room.tool_calls_for("a")
        self.assertEqual(calls, [{"function": "track_order", "args": {"order_id": "X1"}}])


if __name__ == "__main__":
    unittest.main()

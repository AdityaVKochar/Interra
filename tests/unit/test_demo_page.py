"""The judge page shows the gate decision and does not invent a score."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from agent.demo_page import (
    CAMERA_AGENT,
    VOICE_AGENT,
    mint_token,
    page_html,
    read_trace_since,
)
from agent.fdb_livekit import benchmark_dispatch_name, register_benchmark_session


class DemoPageTests(unittest.TestCase):
    def test_page_states_the_scored_run_and_the_gate(self):
        page = page_html().lower()
        self.assertIn("70/100 strict", page_html())
        self.assertIn("100/100 turn-take", page_html())
        self.assertIn("4.452 s average", page_html())
        self.assertIn("organizer llm judge off", page)
        self.assertIn("29 of 100 re-recorded", page)
        self.assertIn("dropped before it is logged", page)
        self.assertIn("interra-benchmark", page)
        self.assertIn("interra-camera-troubleshooter", page)

    def test_voice_and_camera_tokens_name_different_workers(self):
        environment = {
            "LIVEKIT_URL": "wss://example.livekit.cloud",
            "LIVEKIT_API_KEY": "devkey",
            "LIVEKIT_API_SECRET": "secret",
        }
        with patch.dict(os.environ, environment, clear=False):
            voice = _payload(mint_token("voice", "demo-voice-abc123"))
            camera = _payload(mint_token("camera", "demo-camera-abc123"))
        self.assertEqual(voice["video"]["room"], "demo-voice-abc123")
        self.assertEqual(camera["video"]["room"], "demo-camera-abc123")
        self.assertEqual(voice["roomConfig"]["agents"][0]["agentName"], VOICE_AGENT)
        self.assertEqual(camera["roomConfig"]["agents"][0]["agentName"], CAMERA_AGENT)
        self.assertNotIn("secret", json.dumps(voice))

    def test_token_rejects_a_room_that_does_not_match_the_mode(self):
        with patch.dict(os.environ, {"LIVEKIT_URL": "wss://x", "LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s"}):
            with self.assertRaises(ValueError):
                mint_token("voice", "demo-camera-abc123")

    def test_trace_reader_keeps_one_room_and_an_unfinished_line(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "livekit-agent.jsonl"
            path.write_text(
                '{"room":"other","kind":"tool_call"}\n'
                '{"room":"demo-voice-abc123","kind":"tool_call_dropped","call":{"function":"search_flights"}}\n',
                encoding="utf-8",
            )
            found, offset = read_trace_since(path, "demo-voice-abc123", 0)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["kind"], "tool_call_dropped")
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"room":"demo-voice-abc123","kind":"transcript","transcript":"Aug')
            again, stuck = read_trace_since(path, "demo-voice-abc123", offset)
            self.assertEqual(again, [])
            self.assertEqual(stuck, offset)

    def test_unnamed_benchmark_worker_stays_auto_dispatched(self):
        server = Mock()
        with patch.dict(os.environ, {"INTERRA_FDB_AGENT_NAME": ""}, clear=False):
            self.assertEqual(benchmark_dispatch_name(), "")
            register_benchmark_session(server)
        server.rtc_session.assert_called_once()
        self.assertEqual(server.rtc_session.call_args.kwargs["agent_name"], "")

    def test_named_benchmark_worker_is_explicit(self):
        server = Mock()
        with patch.dict(os.environ, {"INTERRA_FDB_AGENT_NAME": "interra-benchmark"}, clear=False):
            register_benchmark_session(server)
        self.assertEqual(server.rtc_session.call_args.kwargs["agent_name"], "interra-benchmark")


def _payload(token: str) -> dict:
    import base64
    body = token.split(".")[1]
    body += "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body))


if __name__ == "__main__":
    unittest.main()

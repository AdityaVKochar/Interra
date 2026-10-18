import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.demo import run_hero_demo
from agent.replay import load_records, render_page, render_replay


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_trace_replay_includes_state_and_rejection(self):
        demo = await run_hero_demo()
        replay = render_replay([e.model_dump(mode='json') for e in demo.trace])
        for phrase in ['RECORDED TRACE', 'Mumbai', 'STALE_RESULT_DISCARDED',
                       'cancellation_max=0.0', 'duplicate_operation_dispatches=0']:
            self.assertIn(phrase, replay)

    def test_external_replay_escapes_control_characters(self):
        output = render_replay([{'t_ms': 10, 'kind': 'action', 'action': 'filler_speech',
                                'payload': {'text': 'hello\x1b[2J'}}])
        self.assertNotIn('\x1b', output)
        self.assertIn('0.010', output)

    def test_page_labels_executed_and_dropped_calls_and_escapes_text(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "livekit-agent.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({"kind": "tool_call", "room": "a", "call": {"function": "track_order", "args": {"id": "1"}}}),
                    json.dumps({"kind": "tool_call_dropped", "room": "a", "call": {"function": "schedule_check", "args": {}}, "reason": "user continued"}),
                    json.dumps({"kind": "transcript", "room": "a", "transcript": "<script>"}),
                ]),
                encoding="utf-8",
            )
            page = render_page(load_records(path))
        self.assertIn("Executed", page)
        self.assertIn("Dropped", page)
        self.assertIn("track_order", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)

import unittest
from agent.replay import render_replay
from agent.demo import run_hero_demo


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

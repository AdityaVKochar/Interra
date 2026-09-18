import unittest

from agent.demo import run_hero_demo


class DemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_hero_demo_uses_runtime_and_exposes_stale_rejection(self):
        result = await run_hero_demo()
        kinds = [entry.kind for entry in result.trace]

        self.assertEqual(result.state.slots["destination"], "Mumbai")
        self.assertIn("CALL_INVALIDATED", kinds)
        self.assertIn("STALE_RESULT_DISCARDED", kinds)
        self.assertIn("FINAL", result.rendered)
        self.assertIn("destination=Mumbai", result.rendered)
        self.assertIn("STALE_RESULT_DISCARDED", result.rendered)
        self.assertEqual(result.metrics.duplicate_operation_dispatches, 0)

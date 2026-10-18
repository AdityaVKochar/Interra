"""The camera correction can be shown without a LiveKit room."""
import unittest

from agent.extension_demo import walkthrough


class ExtensionDemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_friday_is_dropped_and_saturday_is_stored(self):
        visits, events = await walkthrough()
        self.assertEqual([visit["day"] for visit in visits], ["Saturday"])
        kinds = [event["kind"] for event in events]
        self.assertIn("tool_call_dropped", kinds)
        self.assertEqual(kinds.count("tool_call"), 3)

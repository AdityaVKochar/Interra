import asyncio
import json
import unittest
from pydantic import ValidationError
from agent.models import Action, Event, State, Proposal
from agent.protocol import LocalProtocol
from agent.clock import VirtualClock
from agent.trace import IDs, TraceRecorder
from agent.tools.manifest import normalize_manifest


class DomainTests(unittest.TestCase):
    def test_event_roundtrip(self):
        event = Event(event_id="e", session_id="s", timestamp=1.0, type="TEXT_CHUNK",
                      payload={"text": "hello", "end_of_turn": True})
        self.assertEqual(LocalProtocol().decode(event.model_dump_json()), event)

    def test_invalid_envelope(self):
        for timestamp in (-1, float("nan"), float("inf"), "1"):
            with self.assertRaises(ValidationError):
                Event(event_id="e", session_id="s", timestamp=timestamp, type="INTERRUPTION", payload={})

    def test_invalid_payload(self):
        with self.assertRaises(Exception):
            LocalProtocol().decode(dict(event_id="e", session_id="s", timestamp=0.,
                                        type="TEXT_CHUNK", payload={"text": "x", "end_of_turn": "true"}))

    def test_final_snapshot(self):
        state = State(session_id="s", intent="lookup", slots={"x": 1})
        action = Action(action_id="a", session_id="s", timestamp=0., type="FINAL",
                        payload={"text": "found", "state_snapshot": {"intent": state.intent, "slots": state.slots}})
        self.assertEqual(json.loads(LocalProtocol().encode(action))["payload"]["state_snapshot"]["slots"], {"x": 1})

    def test_ids_and_trace_isolation(self):
        ids = IDs("s")
        self.assertEqual(len({ids.new("a") for _ in range(100)}), 100)
        trace = TraceRecorder("s", VirtualClock(), ids)
        data = {"nested": [1]}
        trace.record("INPUT", value=data)
        data["nested"].append(2)
        self.assertEqual(trace.entries[0].data["value"]["nested"], [1])

    def test_manifest_normalization(self):
        spec = dict(name="novel", description="test", argument_schema={"type": "object"}, effect_type="READ_ONLY")
        self.assertEqual(normalize_manifest([spec])["novel"].effect_type, "READ_ONLY")
        with self.assertRaises(ValueError):
            normalize_manifest([spec, spec])
        with self.assertRaises(ValueError):
            normalize_manifest([{**spec, "effect_type": "guess"}])

    def test_invalid_proposal(self):
        with self.assertRaises(ValueError):
            Proposal.model_validate({"clarification": "which?", "final_response": "done"})


class ClockTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_and_cleanup(self):
        clock, order = VirtualClock(), []
        async def wait(n):
            await clock.sleep(1)
            order.append(n)
        tasks = [asyncio.create_task(wait(n)) for n in range(3)]
        await asyncio.sleep(0)
        tasks[2].cancel()
        await asyncio.gather(tasks[2], return_exceptions=True)
        clock.advance_to(1.)
        await asyncio.gather(*tasks[:2])
        self.assertEqual(order, [0, 1])
        self.assertEqual(clock.pending, 0)
        with self.assertRaises(ValueError):
            clock.advance_to(0.)

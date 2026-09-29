import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from agent.samsung import ParticipantAgent, SamsungProtocol, argument_schema
from agent.kit_media import KitMediaLoader
from agent.models import Action
from tests.helpers import ScriptedPlanner
from tests.scenarios.test_audio import wav_ref
from vendor.samsung_theme05.harness.protocol import validate_action
from vendor.samsung_theme05.harness.mock_env import TOOL_REGISTRY


class SamsungTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tasks = []

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def start(self, provider, **kwargs):
        agent = ParticipantAgent(asyncio.Queue(), asyncio.Queue(), provider=provider, **kwargs)
        await agent.setup()
        self.tasks.append(asyncio.create_task(agent.run()))
        return agent

    async def send(self, agent, kind, payload, timestamp=0):
        await agent.in_q.put(dict(timestamp_ms=timestamp, event_type=kind, payload=payload))
        await agent.in_q.join()
        await agent.runtime.input.join()

    async def action(self, agent, kind):
        async with asyncio.timeout(3):
            while True:
                action = await agent.out_q.get()
                self.assertEqual(validate_action(action), [])
                if action['action'] == kind:
                    return action

    def test_manifest_conversion_covers_official_nested_and_array_shapes(self):
        p = SamsungProtocol('s')
        e = p.decode(dict(timestamp_ms=0, event_type='tool_manifest', payload={'tools': TOOL_REGISTRY}))
        from agent.tools.registry import ToolRegistry
        registry = ToolRegistry()
        registry.replace(e.payload['tools'])
        schemas = {t.name: t for t in registry.specs}
        self.assertEqual(schemas['lookup_manual'].argument_schema['properties']['image_embedding']['items'], {'type': 'number'})
        self.assertEqual(schemas['create_support_ticket'].argument_schema['properties']['issue']['required'], ['summary', 'severity'])
        self.assertEqual(schemas['book_flight'].max_retries, 0)
        self.assertEqual(argument_schema({'x': {'type': 'array', 'items': {'type': 'object', 'properties': {'y': {'type': 'boolean', 'required': True}}}}})['properties']['x']['items']['required'], ['y'])

    async def test_interruption_text_replans_and_tail_result_completes(self):
        def plan(city):
            return dict(state_patch={'intent': 'travel', 'set_slots': {'destination': city}},
                tool_requests=[dict(tool_name='flight_search', arguments={'destination': city}, bindings={'destination': 'destination'})])
        provider = ScriptedPlanner(plan('A'), plan('B'), {'final_response': 'Current result received.'})
        a = await self.start(provider)
        await self.send(a, 'tool_manifest', {'tools': TOOL_REGISTRY})
        await self.send(a, 'user_speech_chunk', {'text': 'Search A', 'end_of_turn': True})
        old = await self.action(a, 'tool_call')
        await self.send(a, 'interruption', {'text': 'Change to B'}, 10)
        cancel = await self.action(a, 'cancel_tool')
        self.assertEqual(cancel['payload']['call_id'], old['payload']['call_id'])
        new = await self.action(a, 'tool_call')
        self.assertEqual(provider.contexts[1].input['text'], 'Change to B')
        await self.send(a, 'scenario_end', {}, 20)
        for action in (old, new):
            await self.send(a, 'tool_result', {'call_id': action['payload']['call_id'], 'status': 'success', 'result': {'value': 'found'}}, 30)
        final = await self.action(a, 'final_response')
        self.assertEqual(final['state_snapshot']['slots']['destination'], 'B')
        kinds = [e.kind for e in a.runtime.trace.entries]
        self.assertIn('STALE_RESULT_DISCARDED', kinds)
        self.assertIn('SCENARIO_INPUT_ENDED', kinds)
        self.tasks[0].cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.assertFalse(a.runtime.tasks)

    async def test_frame_survives_following_question_and_does_not_plan_alone(self):
        from tests.scenarios.test_vision import png_ref
        import base64
        class Vision:
            async def understand_png(self, data):
                return {'summary': 'A socket', 'facts': {'shape': 'round'}}
        planner = ScriptedPlanner({'final_response': 'A round socket is visible.'})
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'frame.png').write_bytes(base64.b64decode(png_ref()[7:]))
            a = await self.start(planner, vision_provider=Vision(), media_root=directory)
            await self.send(a, 'video_frame', {'frame_id': 'f', 'image_ref': 'frame.png'})
            self.assertTrue(a.out_q.empty())  # A passive frame is context, not a turn.
            # Drain perception completion without depending on wall-clock timing.
            await asyncio.gather(*a.runtime.perception.tasks.values())
            await a.runtime.input.join()
            self.assertEqual(planner.contexts, [])
            await self.send(a, 'user_speech_chunk', {'text': 'What is this?', 'end_of_turn': True}, 5)
            await self.action(a, 'final_response')
            self.assertEqual(planner.contexts[-1].input['observations']['vision']['facts'], {'shape': 'round'})
            self.assertIn('FRAME_CONTEXT_RETAINED', [e.kind for e in a.runtime.trace.entries])

    async def test_partial_audio_is_accumulated_before_planning(self):
        import base64
        class Audio:
            async def understand_wav(self, data):
                return {'transcript': 'Corrected request'}
        planner = ScriptedPlanner({'final_response': 'Understood.'})
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'clip.wav').write_bytes(base64.b64decode(wav_ref()[7:]))
            a = await self.start(planner, audio_provider=Audio(), media_root=directory)
            await self.send(a, 'user_audio_chunk', {'audio_ref': 'clip.wav', 'end_of_turn': False})
            await asyncio.gather(*a.runtime.perception.tasks.values())
            await a.runtime.input.join()
            self.assertEqual(planner.contexts, [])
            await self.send(a, 'user_audio_chunk', {'audio_ref': 'clip.wav', 'end_of_turn': True}, 5)
            await self.action(a, 'final_response')
            self.assertEqual(len(planner.contexts), 1)
            self.assertIn('OBSERVATION_ACCEPTED', [e.kind for e in a.runtime.trace.entries])

    async def test_missing_media_clarifies_and_rejects_path_escape(self):
        class Vision:
            async def understand_png(self, data):
                raise AssertionError('missing media must not reach provider')
        with tempfile.TemporaryDirectory() as directory:
            a = await self.start(ScriptedPlanner(), vision_provider=Vision(), media_root=directory)
            await self.send(a, 'video_frame', {'frame_id': 'f', 'image_ref': 'missing.png'})
            await self.action(a, 'clarification_request')
            self.assertIn('PERCEPTION_FAILED', [e.kind for e in a.runtime.trace.entries])
            with self.assertRaises(ValueError):
                KitMediaLoader(directory).read('../escape.png')

    async def test_goal_switch_can_finish_without_obsolete_tool_evidence(self):
        provider = ScriptedPlanner(
            {'state_patch': {'intent': 'search', 'set_slots': {'destination': 'A'}},
             'tool_requests': [{'tool_name': 'flight_search', 'arguments': {'destination': 'A'}}]},
            {'state_patch': {'intent': 'conversation'}, 'final_response': 'Hello.'})
        a = await self.start(provider)
        await self.send(a, 'tool_manifest', {'tools': TOOL_REGISTRY})
        await self.send(a, 'user_speech_chunk', {'text': 'Search A', 'end_of_turn': True})
        await self.action(a, 'tool_call')
        await self.send(a, 'interruption', {'text': 'Forget that, just say hello.'}, 10)
        await self.action(a, 'cancel_tool')
        final = await self.action(a, 'final_response')
        self.assertEqual(final['state_snapshot']['intent'], 'conversation')
        self.assertNotIn('FINAL_BLOCKED_NO_EVIDENCE', [e.kind for e in a.runtime.trace.entries])

    async def test_pending_frame_finishes_after_text_but_is_rejected_after_interruption(self):
        from tests.scenarios.test_vision import png_ref
        from agent.multimodal.fusion import PerceptionResult
        from agent.multimodal.vision import VisualObservation
        import base64
        pending = asyncio.get_running_loop().create_future()
        class Vision:
            async def understand_png(self, data):
                return await pending
        planner = ScriptedPlanner({'final_response': 'Premature'}, {'final_response': 'Now grounded.'},
                                  {'state_patch': {'intent': 'new'}, 'final_response': 'Switched.'})
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'frame.png').write_bytes(base64.b64decode(png_ref()[7:]))
            a = await self.start(planner, vision_provider=Vision(), media_root=directory)
            await self.send(a, 'video_frame', {'frame_id': 'f', 'image_ref': 'frame.png', 'device_hint': 'GENERIC'})
            source_id = a.runtime.perception.latest['vision']
            epoch = a.runtime.epoch
            await self.send(a, 'user_speech_chunk', {'text': 'What is this?', 'end_of_turn': True}, 5)
            await a.runtime.planner_task
            await a.runtime.input.join()
            self.assertIn('FINAL_DEFERRED_PERCEPTION', [e.kind for e in a.runtime.trace.entries])
            pending.set_result({'summary': 'A socket'})
            await self.action(a, 'final_response')
            self.assertEqual(planner.contexts[-1].input['frame_context']['device_hint'], 'GENERIC')
            await self.send(a, 'interruption', {'text': 'New topic'}, 10)
            await self.action(a, 'final_response')
            await a.runtime.input.put(PerceptionResult(source_id, 0., epoch, 'vision', VisualObservation(summary='old')))
            await a.runtime.input.join()
            self.assertIn('STALE_PERCEPTION_DISCARDED', [e.kind for e in a.runtime.trace.entries])

    def test_malformed_inputs_and_all_outgoing_actions(self):
        p = SamsungProtocol('s')
        with self.assertRaises(ValueError):
            p.decode({'timestamp_ms': float('nan'), 'payload': {}, 'event_type': 'scenario_end'})
        for kind, payload in [('SPEAK', {'text': 'Checking.'}), ('CLARIFY', {'question': 'Which item?'}),
            ('TOOL_CALL', {'call_id': 'c', 'tool_name': 'new_tool', 'arguments': {}}),
            ('CANCEL_TOOL_CALL', {'call_id': 'c'}),
            ('FINAL', {'text': 'Done.', 'state_snapshot': {'intent': 'test', 'slots': {}}})]:
            action = Action(action_id='a', session_id='s', timestamp=0., type=kind, payload=payload)
            self.assertEqual(validate_action(p.encode(action)), [])

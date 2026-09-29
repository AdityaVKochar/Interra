import asyncio
import unittest

from agent.samsung import SamsungProtocol
from tests.helpers import Harness, ScriptedPlanner, plan, spec
from tests.scenarios.test_audio import AudioMock, wav_ref


class ReadinessRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_acknowledgment_is_after_end_of_turn(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(pending), self.id()) as h:
            await h.send('TEXT_CHUNK', text='find ', end_of_turn=False)
            self.assertTrue(h.runtime.output.empty())
            await h.advance(1.2)
            await h.text('options')
            ack = await h.action('SPEAK')
            self.assertEqual(ack.timestamp, 1.2)
            self.assertEqual([e.data['source_timestamp'] for e in h.runtime.trace.entries
                              if e.kind == 'FIRST_RESPONSE_LATENCY'], [1.2])

    async def test_audio_chunks_coalesce_and_turn_fillers_do_not_repeat(self):
        planner = ScriptedPlanner({'final_response': 'One'}, {'final_response': 'Two'})
        async with Harness(planner, self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock({'transcript': 'hello'})
            for _ in range(3):
                await h.send('AUDIO_CLIP', mime_type='audio/wav', data_ref=wav_ref(), end_of_turn=False)
            self.assertTrue(h.runtime.output.empty())
            await h.send('AUDIO_CLIP', mime_type='audio/wav', data_ref=wav_ref(), end_of_turn=True)
            await h.action('FINAL')
            await h.text('hello again')
            await h.action('FINAL')
            fillers = [e.data['action']['payload']['text'] for e in h.runtime.trace.entries
                       if e.kind == 'ACTION_EMITTED' and e.data['action']['type'] == 'SPEAK']
            self.assertEqual(len(fillers), 2)
            self.assertEqual(len(set(fillers)), 2)

    async def test_corrected_snapshot_exported_on_tool_call(self):
        async with Harness(ScriptedPlanner(plan(), plan('Mumbai')), self.id()) as h:
            await h.send('TOOL_MANIFEST', tools=[spec()])
            await h.text('Delhi')
            await h.action('TOOL_CALL')
            await h.send('INTERRUPTION', reason='correction', text='Mumbai instead')
            action = await h.action('TOOL_CALL')
            external = SamsungProtocol.encode(action)
            self.assertEqual(external['state_snapshot']['slots']['destination'], 'Mumbai')
            self.assertNotIn('state_snapshot', external['payload'])
            corrected = [e.data['action']['payload']['state_snapshot'] for e in h.runtime.trace.entries
                         if e.kind == 'ACTION_EMITTED' and e.data['action']['type'] == 'SPEAK']
            self.assertEqual(corrected[-1]['slots']['destination'], 'Mumbai')

    async def test_ambiguous_question_survives_short_answer(self):
        planner = ScriptedPlanner({'state_patch': {'intent': 'lookup', 'set_slots': {'destination': 'Boston'}},
                                   'final_response': 'Understood Boston.'})
        async with Harness(planner, self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock({'transcript': 'Find a flight to unclear',
                'ambiguous': True, 'question': 'Austin or Boston?'})
            await h.send('AUDIO_CLIP', mime_type='audio/wav', data_ref=wav_ref())
            await h.action('CLARIFY')
            self.assertNotIn('destination', h.runtime.state.snapshot.slots)
            await h.text('Boston')
            await h.action('FINAL')
            context = planner.contexts[0]
            self.assertEqual(context.clarification['question'], 'Austin or Boston?')
            self.assertIn('Find a flight', str(context.clarification))
            self.assertIsNone(h.runtime.state.snapshot.pending_clarification)

    async def test_failed_call_details_available_on_next_turn(self):
        planner = ScriptedPlanner(plan(), {'clarification': 'Try another destination?'})
        async with Harness(planner, self.id()) as h:
            await h.send('TOOL_MANIFEST', tools=[spec()])
            await h.text('Delhi')
            call = await h.action('TOOL_CALL')
            await h.send('TOOL_RESULT', call_id=call.payload['call_id'], ok=False,
                         result={'error': 'not_found'}, error='not_found')
            await h.action('CLARIFY')
            await h.text('What went wrong?')
            await h.action('CLARIFY')
            self.assertEqual(planner.contexts[-1].calls[call.payload['call_id']]['error'], 'not_found')

    async def test_goal_switch_clears_pending_clarification(self):
        planner = ScriptedPlanner({'clarification': 'Which city?'},
            {'state_patch': {'intent': 'greeting'}, 'final_response': 'Hello.'})
        async with Harness(planner, self.id()) as h:
            await h.text('Find a flight')
            await h.action('CLARIFY')
            await h.send('INTERRUPTION', reason='switch', text='Forget travel; hello')
            await h.action('FINAL')
            self.assertEqual(h.runtime.clarification_context, {})
            self.assertIsNone(h.runtime.state.snapshot.pending_clarification)

    async def test_retained_uncertain_frame_resolved_by_subsequent_answer(self):
        from tests.scenarios.test_vision import VisionMock, png_ref
        planner = ScriptedPlanner({'resolves_clarification': True,
            'state_patch': {'set_slots': {'port': 'USB-C'}}, 'final_response': 'USB-C, understood.'})
        async with Harness(planner, self.id()) as h:
            h.runtime.retain_frame_context = True
            h.runtime.perception.vision_provider = VisionMock({'summary': 'unclear port',
                'ambiguous': True, 'question': 'What is the port label?'})
            await h.send('VIDEO_FRAME', mime_type='image/png', data_ref=png_ref(), frame_id='f')
            await h.action('CLARIFY')
            self.assertTrue(h.runtime.perception.unresolved)
            await h.text('USB-C')
            await h.action('FINAL')
            self.assertFalse(h.runtime.perception.unresolved)
            self.assertEqual(h.runtime.state.snapshot.slots, {'port': 'USB-C'})

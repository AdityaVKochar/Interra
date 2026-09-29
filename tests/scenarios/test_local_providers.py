import asyncio
import json
import threading
import unittest
from unittest.mock import patch

import httpx
from agent.providers.native import NativeWorker
from agent.providers.local_vision import LocalVisionProvider
from agent.providers.local_audio import LocalAudioProvider
from agent.providers.ollama import OllamaProvider
from agent.models import ToolRequest
from tests.helpers import Harness, ScriptedPlanner


class LocalProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_cancellation_joins_work_without_blocking_loop(self):
        entered, release = threading.Event(), threading.Event()
        worker = NativeWorker()
        def blocking():
            entered.set()
            release.wait(3)
            return 'obsolete'
        task = asyncio.create_task(worker.run(blocking))
        try:
            await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            marker = asyncio.Event()
            asyncio.get_running_loop().call_soon(marker.set)
            await asyncio.wait_for(marker.wait(), 1)
            self.assertFalse(task.done())  # Running native work still has an owner.
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            await worker.aclose()
        self.assertFalse(worker.pending)

    async def test_vision_is_schema_validated_and_cached_per_instance(self):
        requests = []
        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertNotIn('image_embedding', body['format']['properties'])
            return httpx.Response(200, json={'message': {'content': '{"summary":"A round port"}'}})
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(respond)) as client:
            llm = OllamaProvider('test', client=client)
            vision = LocalVisionProvider(llm, 'unused')
            try:
                with patch.object(vision, 'embed', return_value=[0.1] * 512):
                    a = await vision.understand_png(b'frame')
                    a['image_embedding'][0] = 100.
                    b = await vision.understand_png(b'frame')
                self.assertEqual(b['image_embedding'][0], 0.1)
                self.assertEqual(len(requests), 1)
            finally:
                await vision.aclose()

    async def test_audio_iterator_runs_on_worker_and_marks_uncertainty(self):
        from types import SimpleNamespace
        loop_thread = threading.get_ident()
        class Model:
            def transcribe(self, *args, **kwargs):
                def segments():
                    self_thread = threading.get_ident()
                    if self_thread == loop_thread:
                        raise AssertionError('native iterator blocked event loop')
                    yield SimpleNamespace(text='to unclear', avg_logprob=-0.5,
                                          words=[SimpleNamespace(word='unclear', probability=0.2)])
                return segments(), None
        audio = LocalAudioProvider('unused')
        try:
            with patch('agent.providers.local_audio.load_whisper', return_value=(Model(), threading.Lock())):
                result = await audio.understand_wav(b'wav')
            self.assertTrue(result['ambiguous'])
            self.assertIn('unclear', result['question'])
        finally:
            await audio.aclose()

    async def test_embedding_resolution_rejects_forged_or_stale_vectors(self):
        async with Harness(ScriptedPlanner(), self.id()) as h:
            h.runtime.perception.accepted['vision'] = {'source_event_id': 'frame-1',
                'observation': {'image_embedding': [0.1] * 512}}
            req = ToolRequest(tool_name='dynamic', arguments={'query': 'socket'},
                              embedding_refs={'image_embedding': 'frame-1'})
            resolved = h.runtime.resolve_embeddings(req)
            self.assertEqual(len(resolved.arguments['image_embedding']), 512)
            self.assertNotIn('image_embedding', req.arguments)
            for bad in [ToolRequest(tool_name='dynamic', arguments={'image_embedding': [1.]}),
                        req.model_copy(update={'embedding_refs': {'image_embedding': 'old'}})]:
                with self.assertRaises(ValueError):
                    h.runtime.resolve_embeddings(bad)

    async def test_generation_is_bounded_and_truncation_rejected(self):
        def respond(request):
            body = json.loads(request.content)
            self.assertEqual(body['options']['num_ctx'], 4096)
            self.assertEqual(body['options']['num_predict'], 512)
            self.assertFalse(body['think'])
            return httpx.Response(200, json={'done_reason': 'length', 'message': {'content': '{}'}})
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(ValueError, 'token limit'):
                await OllamaProvider('test', client=client).generate([], {})

    async def test_context_compaction_preserves_schema_and_evidence(self):
        from agent.models import State, ToolSpec
        from agent.providers.base import PlanningContext
        from tests.helpers import spec
        observation = {'summary': 'label C', 'facts': {'label': 'C'}}
        context = PlanningContext(state=State(session_id='s'), tools=[ToolSpec(**spec())],
            input={'text': 'question label C', 'text_input': {'text': 'question'},
                   'observation': observation, 'observations': {'vision': observation}},
            results={'call': {'result': {'manual': 'Use port C'}}})
        def respond(request):
            body = json.loads(request.content)
            payload = json.loads(body['messages'][-1]['content'])
            self.assertEqual(payload['tools'][0]['argument_schema'], spec()['argument_schema'])
            self.assertEqual(payload['input']['observations']['vision'], observation)
            self.assertEqual(payload['results'], context.results)
            self.assertNotIn('observation', payload['input'])
            self.assertEqual(body['format']['$defs']['ToolRequest']['properties']['tool_name']['enum'], ['lookup'])
            return httpx.Response(200, json={'message': {'content': '{"final_response":"Port C"}'}})
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(respond)) as client:
            provider = OllamaProvider('test', client=client)
            await provider.plan(context)
            with self.assertRaisesRegex(ValueError, 'context budget'):
                await provider.plan(context.model_copy(update={'input': {'text': 'x' * 11000}}))

    async def test_ollama_misrouted_json_requires_complete_valid_object(self):
        from agent.models import Proposal
        for value, valid in [('{"final_response":"Hello"}', True),
                             ('Thinking: {"final_response":"Hello"}', False),
                             ('{"unrecognized":"value"}', False), ('', False)]:
            with self.subTest(value=value):
                def respond(request):
                    return httpx.Response(200, json={'done_reason': 'stop',
                        'message': {'content': '', 'thinking': value}})
                async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(respond)) as client:
                    provider = OllamaProvider('test', client=client)
                    if valid:
                        self.assertEqual(await provider.generate([], Proposal.model_json_schema()), value)
                    else:
                        with self.assertRaises(Exception):
                            await provider.generate([], Proposal.model_json_schema())

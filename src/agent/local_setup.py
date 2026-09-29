"""Explicit model download and a measured local readiness check; never reads scenarios."""
import argparse
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import time

import httpx


def download(root, endpoint, model, perception_only=False):
    from huggingface_hub import HfApi, snapshot_download
    from fastembed import ImageEmbedding
    from .providers.local_vision import EMBEDDING_MODEL
    root.mkdir(parents=True, exist_ok=True)
    manifest = {'ollama_model': model, 'models': {}}
    for repo, folder in [('Systran/faster-whisper-base', 'whisper-base')]:
        revision = HfApi().model_info(repo).sha
        snapshot_download(repo, revision=revision, local_dir=root / folder)
        manifest['models'][repo] = revision
    revision = HfApi().model_info(EMBEDDING_MODEL).sha
    # FastEmbed manages its own ONNX cache. Record revision and actual file checksums below.
    ImageEmbedding(EMBEDDING_MODEL, cache_dir=str(root / 'fastembed'), threads=2)
    manifest['models'][EMBEDDING_MODEL] = revision
    if not perception_only:
        pull_ollama(endpoint, model, manifest)
    import hashlib
    manifest['files'] = {}
    for path in root.rglob('*'):
        if (path.is_file() and path.suffix in {'.onnx', '.bin', '.json'}
                and '.cache' not in path.parts and path.name != 'model-manifest.json'):
            with path.open('rb') as stream:
                manifest['files'][str(path.relative_to(root))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (root / 'model-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def pull_ollama(endpoint, model, manifest):
    with httpx.Client(base_url=endpoint, timeout=None) as client:
        with client.stream('POST', '/api/pull', json={'model': model}) as response:
            response.raise_for_status()
            previous = None
            for line in response.iter_lines():
                row = json.loads(line)
                if row.get('error'):
                    raise RuntimeError(row['error'])
                percent = int(100 * row.get('completed', 0) / max(row.get('total', 1), 1)) // 10 * 10
                progress = (row.get('status'), percent)
                if progress != previous:
                    print(progress, flush=True)
                    previous = progress
        response = client.get('/api/tags'); response.raise_for_status()
        manifest['ollama_tags'] = response.json()


async def probe(args):
    import psutil
    from .models import State
    from .providers.base import PlanningContext
    from .planner import propose
    from .samsung import ParticipantAgent
    from .kit_media import KitMediaLoader
    from .models import Event
    from .multimodal.audio import decode_media
    report = {'python': platform.python_version(), 'platform': platform.platform(),
        'memory_available_bytes': psutil.virtual_memory().available,
        'ffmpeg': shutil.which('ffmpeg'), 'checks': [], 'ready': False,
        'dependencies': {name: importlib.metadata.version(name)
                         for name in ('httpx', 'pydantic', 'faster-whisper', 'fastembed')}}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    agent = ParticipantAgent(asyncio.Queue(), asyncio.Queue(), media_root=args.media_root)
    async def measure(name, operation):
        start = time.perf_counter()
        try:
            async with asyncio.timeout(300 if name == 'setup' else 60):
                result = await operation()
            row = {'name': name, 'ok': True, 'seconds': time.perf_counter() - start, 'result': result}
        except Exception as exc:
            row = {'name': name, 'ok': False, 'seconds': time.perf_counter() - start,
                   'error': f'{type(exc).__name__}: {exc}'}
        report['checks'].append(row); save(); print(json.dumps(row), flush=True)
        return row['ok']
    try:
        if not await measure('setup', agent.setup):
            return report
        context = PlanningContext(state=State(session_id='readiness'),
            input={'text': 'Say hello in one short sentence.'}, tools=[])
        async def text_request():
            from .tools.registry import ToolRegistry
            result = await propose(agent.provider, context)
            registry = ToolRegistry()
            for request in result.tool_requests:
                registry.validate(request, context.state)
            if not result.final_response:
                raise ValueError('greeting probe did not produce a final response')
            return result.model_dump(exclude_none=True, exclude_defaults=True)
        await measure('text', text_request)
        if args.audio:
            async def audio():
                event = Event(session_id='readiness', event_id='audio', timestamp=0., type='AUDIO_CLIP',
                    payload={'data_ref': 'kit:' + json.dumps([args.audio])})
                data = decode_media(await KitMediaLoader(args.media_root)(event))
                return await agent.audio_provider.understand_wav(data)
            await measure('audio', audio)
        if args.image:
            async def vision():
                data = KitMediaLoader(args.media_root).read(args.image)
                observation = await agent.vision_provider.understand_png(data)
                vector = observation.pop('image_embedding', None)
                observation['embedding_dimensions'] = len(vector) if vector else 0
                return observation
            await measure('vision', vision)
        report['ready'] = all(row['ok'] for row in report['checks'])
        report['meets_six_second_single_stage_budget'] = report['ready'] and all(
            row['seconds'] <= 6 for row in report['checks'] if row['name'] != 'setup')
        report['note'] = 'Readiness is not task completion. Run the unmodified evaluator at time_scale=1.'
        return report
    finally:
        for client in reversed(agent.owned_clients):
            await client.aclose()
        agent.owned_clients.clear()
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['download', 'probe'])
    parser.add_argument('--model-root', type=Path, default=Path(os.environ.get('INTERRA_MODEL_ROOT', '.models')))
    parser.add_argument('--model', default=os.environ.get('INTERRA_MODEL', 'qwen3-vl:2b'))
    parser.add_argument('--perception-only', action='store_true', help='Download ASR and CLIP before Ollama is available')
    parser.add_argument('--endpoint', default=os.environ.get('INTERRA_OLLAMA_URL', 'http://localhost:11434'))
    parser.add_argument('--media-root', type=Path, default=Path(os.environ.get('INTERRA_MEDIA_ROOT', 'vendor/samsung_theme05')))
    parser.add_argument('--audio')
    parser.add_argument('--image')
    parser.add_argument('--output', type=Path, default=Path('artifacts/local-readiness.json'))
    args = parser.parse_args()
    if args.command == 'download':
        download(args.model_root.resolve(), args.endpoint, args.model, args.perception_only)
    else:
        os.environ.update(INTERRA_PROFILE='local', INTERRA_MODEL=args.model,
            INTERRA_OLLAMA_URL=args.endpoint, INTERRA_MODEL_ROOT=str(args.model_root.resolve()))
        report = asyncio.run(probe(args))
        raise SystemExit(0 if report['ready'] else 1)


if __name__ == '__main__':
    main()

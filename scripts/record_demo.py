"""Build the historical queue-runtime replay; this is not the FDB-v3 demo."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import textwrap

from agent.demo import run_hero_demo


def main():
    root = Path.cwd()
    build = root / 'artifacts/video'
    build.mkdir(parents=True, exist_ok=True)
    output = root / 'output/submission/Interra-legacy-queue-runtime-replay.mp4'
    output.parent.mkdir(parents=True, exist_ok=True)
    font = Path('C:/Windows/Fonts/consola.ttf')
    if not font.exists():
        raise RuntimeError('Set a locally available monospace font in this recording script')
    shutil.copyfile(font, build / 'font.ttf')
    demo = asyncio.run(run_hero_demo())
    (root / 'artifacts/demo-trace.jsonl').write_text(''.join(
        json.dumps(e.model_dump(mode='json')) + '\n' for e in demo.trace), encoding='utf-8')
    pages = [('Interra / Theme 05', 'Recorded execution of the real SessionRuntime.\n\nThe correction example uses scripted reasoning and a virtual clock. Provider measurements later in this video use actual local models.\n\nPlayback holds each event for readability; displayed source timestamps are unchanged.')]
    for e in demo.trace:
        if e.kind == 'INPUT_RECEIVED' and e.data['event']['type'] in {'TEXT_CHUNK', 'INTERRUPTION'}:
            event = e.data['event']
            pages.append((f"{e.timestamp:.2f}s / USER {event['type']}", json.dumps(event['payload'], indent=2)))
        elif e.kind == 'STATE_UPDATED':
            pages.append((f'{e.timestamp:.2f}s / STATE UPDATED', json.dumps(e.data['after'], indent=2)))
        elif e.kind == 'ACTION_EMITTED' and e.data['action']['type'] in {'TOOL_CALL', 'CANCEL_TOOL_CALL', 'FINAL'}:
            a = e.data['action']
            pages.append((f"{e.timestamp:.2f}s / {a['type']}", json.dumps(a['payload'], indent=2)))
        elif e.kind in {'STALE_RESULT_DISCARDED', 'RESULT_ACCEPTED'}:
            pages.append((f'{e.timestamp:.2f}s / {e.kind}', json.dumps(e.data, indent=2)))
    pages.append(('Coordination evidence', f'Stale results discarded: {demo.metrics.stale_results_discarded}\nDuplicate operation dispatches: {demo.metrics.duplicate_operation_dispatches}\n\nThese are deterministic runtime measurements. Zero virtual response delay is not a live-model latency claim.'))
    for filename, title in [('asr-readiness.json', 'Actual local audio probe'),
                            ('embedding-readiness.json', 'Actual local image encoder')]:
        path = root / 'artifacts' / filename
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, list):
                data = data[-1]  # Most recent full audio turn; show its actual uncertainty.
            pages.append((title, json.dumps(data, indent=2)))
    evaluation = root / 'artifacts/samsung-local-evaluation.json'
    if evaluation.exists():
        report = json.loads(evaluation.read_text())
        pages.append(('Actual public evaluation', json.dumps({'repetitions': report['reps'],
            'time_scale': report['time_scale'], 'summary': report['summary']}, indent=2)))
    readiness = root / 'artifacts/local-readiness.json'
    if readiness.exists():
        data = json.loads(readiness.read_text())
        rows = [f"{r['name']}: {'pass' if r['ok'] else 'FAIL'}, {r['seconds']:.2f}s" for r in data['checks']]
        pages.append(('Actual combined model readiness', '\n'.join(rows) +
            '\n\nThese measurements do not establish successful task completion.\nFull failure details accompany the release evidence.'))
    pages.append(('Limits and reproduction', 'Small local models can mishear noisy speech.\nInference must fit the scenario timing windows.\n\nReproduce with scripts/local.ps1 Probe and Evaluate.\nInspect original traces with python -m agent.demo --replay.\n\nTeam details, disclosure and final submission require team review.'))
    clips = []
    for i, (title, body) in enumerate(pages):
        prefix = f'page-{i:02}'
        (build / f'{prefix}-title.txt').write_text(title, encoding='utf-8', newline='\n')
        lines = []
        for line in body.splitlines():
            lines.extend(textwrap.wrap(line, width=77, replace_whitespace=False) or [''])
        # Keep original evidence intact in JSON; avoid tiny text in the recording.
        if len(lines) > 16:
            lines = lines[:15] + ['... full evidence in the accompanying JSON trace']
        filters = [f'drawtext=fontfile=font.ttf:textfile={prefix}-title.txt:expansion=none:fontcolor=0x6CE4CE:fontsize=32:x=55:y=55']
        for row, line in enumerate(lines):
            if not line:
                continue
            filename = f'{prefix}-line-{row:02}.txt'
            (build / filename).write_text(line, encoding='utf-8')
            filters.append(f'drawtext=fontfile=font.ttf:textfile={filename}:expansion=none:fontcolor=white:fontsize=23:x=55:y={135 + row * 32}')
        clip = f'{prefix}.mp4'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0x0A2032:s=1280x720:r=15',
            '-t', '9', '-vf', ','.join(filters), '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-pix_fmt', 'yuv420p', clip], cwd=build, check=True)
        clips.append(clip)
    (build / 'concat.txt').write_text(''.join(f"file '{clip}'\n" for clip in clips), encoding='utf-8')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', 'concat.txt',
                    '-c', 'copy', '-movflags', '+faststart', str(output)], cwd=build, check=True)
    print(f'{output} ({len(pages)*9} seconds; captioned evidence replay, no synthetic success claims)')


if __name__ == '__main__':
    main()

"""Read recorded runtime JSONL or official harness JSON without rerunning the agent."""
import json
from pathlib import Path

from .metrics import analyze_trace
from .models import TraceEntry


def load_trace(path, scenario=None):
    path = Path(path)
    if path.suffix == '.jsonl':
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    value = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(value, list):
        return value
    if 'trace' in value:
        return value['trace']
    runs = value.get('runs', [])
    matches = [row for row in runs if scenario is None or row.get('scenario_id') == scenario]
    if len(matches) != 1:
        raise ValueError('Select one --scenario from: ' + ', '.join(r['scenario_id'] for r in runs))
    return matches[0]['trace']


def render_replay(rows):
    lines = ['RECORDED TRACE REPLAY - original timestamps; no new inference', 'SECONDS  EVENT / ACTION']
    local = bool(rows and 'timestamp' in rows[0])
    for row in rows:
        timestamp = row.get('timestamp', row.get('t_ms', 0) / 1000)
        kind = row['kind']
        if local:
            data = row.get('data', {})
            if kind == 'INPUT_RECEIVED':
                event = data['event']
                detail = {'type': event['type'], 'payload': event['payload']}
                if 'data_ref' in detail['payload']:
                    detail = {'type': event['type'], 'event_id': event['event_id']}
            elif kind == 'ACTION_EMITTED':
                detail = data['action']
            elif kind in {'STATE_UPDATED', 'CLARIFICATION_UPDATED', 'OBSERVATION_ACCEPTED',
                          'CALL_DISPATCHED', 'CALL_INVALIDATED', 'STALE_RESULT_DISCARDED',
                          'STALE_PLAN_DISCARDED', 'RESULT_ACCEPTED', 'DUPLICATE_WRITE_BLOCKED',
                          'FIRST_RESPONSE_LATENCY', 'CANCEL_EMISSION_LATENCY', 'PLANNER_FAILED',
                          'PERCEPTION_FAILED', 'SESSION_CLOSED'}:
                detail = data
            else:
                continue
        else:
            detail = {k: v for k, v in row.items() if k not in ('kind', 't_ms')}
        serialized = json.dumps(detail, ensure_ascii=True, separators=(',', ':'))
        lines.append(f'{timestamp:7.3f}  {kind} {serialized[:700]}')
    if local:
        metrics = analyze_trace(TraceEntry.model_validate(r) for r in rows)
        lines.extend(['METRICS (seconds)',
            f'first_response_max={metrics.max_first_response_latency}',
            f'cancellation_max={metrics.max_cancellation_latency}',
            f'stale_results_discarded={metrics.stale_results_discarded}',
            f'duplicate_operation_dispatches={metrics.duplicate_operation_dispatches}'])
    return '\n'.join(lines)

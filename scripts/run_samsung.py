"""Run the unmodified public harness and save its complete traces.

From the repository root: python scripts/run_samsung.py --allow-unconfigured
Without that explicit flag, missing reasoning configuration is an error.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from interra_submission import ParticipantAgent
from vendor.samsung_theme05.harness.runner import run_scenario
from vendor.samsung_theme05.harness.scorer import score_scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-unconfigured', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/samsung-public-traces.json')
    args = parser.parse_args()
    if not os.environ.get('INTERRA_MODEL') and not args.allow_unconfigured:
        parser.error('Set INTERRA_MODEL for live evaluation, or explicitly use --allow-unconfigured for a pipeline check.')
    kit = ROOT / 'vendor/samsung_theme05'
    os.environ.setdefault('INTERRA_MEDIA_ROOT', str(kit))
    rows = []
    for path in sorted((kit / 'scenarios').glob('*.json')):
        scenario = json.loads(path.read_text(encoding='utf-8'))
        trace = run_scenario(scenario, ParticipantAgent, time_scale=1, verbose=False)
        errors = [e for e in trace if e['kind'] in {'agent_crash', 'protocol_error'} or
                  (e['kind'] == 'agent_setup' and 'error' in e)]
        rows.append({'scenario_id': scenario['scenario_id'], 'trace': trace,
                     'score': score_scenario(scenario, trace), 'integration_errors': errors})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'model_configured': bool(os.environ.get('INTERRA_MODEL')),
            'time_scale': 1, 'runs': rows}, indent=2), encoding='utf-8')
        print(f"{scenario['scenario_id']}: {len(errors)} integration errors", flush=True)
    if any(row['integration_errors'] for row in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

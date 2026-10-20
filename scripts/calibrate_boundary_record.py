"""Exercise local boundary storage with two public documentation calls, no model."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from native_boundary_record import snapshot_boundary, verify_boundary
from run_context_comparison import Bridge, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--record-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.record_id.startswith('P11_BOUNDARY_') or not args.record_id.replace('_', '').isalnum():
        raise ValueError('expected a new bounded calibration record')
    storage = args.storage_root
    out = storage / 'records/boundary_controls' / args.record_id
    out.mkdir(parents=True, exist_ok=False)
    appworld = storage / '.runtime/appworld/r18_probe_01'
    experiment = appworld / 'experiments/outputs' / args.record_id
    if experiment.exists():
        raise FileExistsError('refusing an existing environment')
    task = '07b42fd_1'  # Previously exposed development scenario only.
    bridge = Bridge(storage / '.runtime/appworld/venv/bin/python', appworld, out)
    records, verifies = [], []
    started = time.monotonic()
    try:
        result = bridge.request({'op': 'init', 'task_id': task,
                                 'experiment': args.record_id, 'seed': 42})
        if not result['ok'] or result['result']['ground_truth_loaded']:
            raise RuntimeError('cannot initialize without ground truth')
        write_json(out / 'public_task.json', result['result'])
        for index in range(3):
            if index:
                request = {'op': 'call', 'call': {'app': 'api_docs',
                           'api': 'show_app_descriptions', 'args': {}}}
                result = bridge.request(request)
                write_json(out / f'operation_{index}.json', {'request': request, 'response': result})
                if not result['ok'] or result['result']['observation'].startswith('Execution failed.'):
                    raise RuntimeError('public documentation request failed')
            dbs = experiment / 'tasks' / task / 'dbs'
            files = {'dbs/' + p.name: p for p in dbs.iterdir()}
            files['harness/public_task.json'] = out / 'public_task.json'
            cid = 'initial' if index == 0 else f'call_{index:03d}'
            records.append(snapshot_boundary(out / 'boundaries', cid, files,
                                             {'public_documentation_calls': index}))
            verifies.append(verify_boundary(out / 'boundaries', cid))
        bridge.close()
        # Verify the first record after the process and its mutable in-memory DBs close.
        verifies.append(verify_boundary(out / 'boundaries', 'initial'))
    finally:
        if bridge.process.poll() is None:
            bridge.close()
    report = {'record_id': args.record_id, 'source_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'model_calls': 0, 'public_documentation_calls': 2, 'final_evaluations': 0,
              'ground_truth_loaded': False, 'boundary_records': records,
              'verifications': verifies, 'wall_seconds': time.monotonic() - started,
              'scope': 'Actual API-boundary DB file capture and post-close byte verification. '
                       'No restore, resumed action equivalence, or full process checkpoint claim.'}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'boundaries': len(records), 'verified': len(verifies),
                      'model_calls': 0, 'public_documentation_calls': 2}))


if __name__ == '__main__':
    main()

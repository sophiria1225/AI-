"""Publish Pro development measurements without model reasoning or private tests."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

from audit_p2 import audit_run
from audit_p3 import audit_protocol
from analyze_p3_timeline import describe_timeline
from summarize_p3 import summarize_observations

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def collect(storage, run):
    summary = read(run / 'summary.json')
    if 'execution_status' not in summary:
        return {'record': str(run.relative_to(storage)), 'status': 'running',
                'recorded_calls': len(summary['calls']),
                'recorded_tokens': summary['total_recorded_tokens']}
    audit = audit_run(run, root=storage)
    audit['errors'] += audit_protocol(run)
    config, plan = read(run / 'config.json'), read(run / 'plan.json')
    expected_config = plan['config_sha256'][plan['config']]
    if hashlib.sha256((run / 'config.json').read_bytes()).hexdigest() != expected_config:
        audit['errors'].append('Saved config differs from the frozen plan')
    if hashlib.sha256((run / 'plan.json').read_bytes()).hexdigest() != summary['plan_sha256']:
        audit['errors'].append('Saved plan differs from the started plan')
    if summary['calls']:
        request = read(run / summary['calls'][0]['path'] / 'request.json')
        user_text = '\n'.join(m.get('content') or '' for m in request['messages'] if m['role'] == 'user')
        task = read(run / 'public_task.json')
        if not all(task[k] in user_text for k in ('problem_statement', 'requirements', 'interface')):
            audit['errors'].append('A public instruction field was missing from the first request')
    events = [read(p) for p in sorted((run/'artifact_versions').glob('*/turn.json'))]
    observations = summarize_observations(summary, events)
    timeline = None
    timeline_error = None
    try:
        initial = (run/'artifact_versions/initial/final.patch').read_bytes()
        timeline = describe_timeline(summary, events, hashlib.sha256(initial).hexdigest())
    except ValueError as error:
        timeline_error = str(error)
    # --numstat parses the candidate only; it does not apply it to any checkout.
    stats = subprocess.run(['git', 'apply', '--numstat', '-z', str(run/'final.patch')],
                           capture_output=True, check=False)
    files = []
    if stats.returncode == 0:
        for row in filter(None, stats.stdout.split(b'\0')):
            fields = row.decode(errors='replace').split('\t', 2)
            if len(fields) == 3:
                files.append({'added': fields[0], 'deleted': fields[1], 'path': fields[2]})
    return {'record': str(run.relative_to(storage)), 'status': summary['execution_status'],
            'plan_sha256': summary['plan_sha256'], 'summary_sha256': hashlib.sha256((run/'summary.json').read_bytes()).hexdigest(),
            'config': {k: config[k] for k in ('model', 'max_calls', 'max_total_tokens', 'max_wall_seconds', 'num_ctx')},
            'measurements': audit, 'observations': observations, 'timeline': timeline,
            'timeline_error': timeline_error, 'changed_files': files,
            'diff_stat_exit': stats.returncode}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    rows = [collect(storage, p.parent) for p in sorted((storage/'records/pro_pilot').glob('*/summary.json'))]
    report = {
        'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'Previously exposed Pro development observations; no comparative quality or reorganization claim',
        'runs': rows,
        'analysis_source_sha256': {name: hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                                  for name in ('summarize_pro_pilot.py', 'analyze_p3_timeline.py', 'summarize_p3.py',
                                               'audit_p2.py', 'audit_p3.py')},
        'limitations': [
            'Changed files, repeated commands and later calls do not establish causal task dependency or unnecessary work.',
            'Existing public tests passing is not proof of requirement completion.',
            'Final artifact timing is retrospective and is not an available online stopping oracle.',
            'New task, larger budget and runtime differ from P3; do not attribute cross-phase differences to orchestration.',
        ],
    }
    (ROOT/'reports/P4_pro_measurements.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'runs': len(rows), 'running': sum(r['status']=='running' for r in rows),
                      'audit_errors': sum(len(r.get('measurements', {}).get('errors', [])) for r in rows)}))


if __name__ == '__main__':
    main()

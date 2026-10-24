"""Close only the eight new P88 cells and their server cost ledger using saved records, without running experiments."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def inspect(storage):
    folder = storage / 'records/context_pilot/P88_pipeline_v01'
    state, server = (read(folder / name) for name in ('status.json', 'server_final.json'))
    report = read(ROOT / 'reports/P88_comparison.json')
    if (state['status'] not in ('complete', 'stopped') or not state['server_stopped']
            or server['status'] != 'stopped' or state['server_supervisor_pid'] != server['supervisor_pid']
            or report['audit_errors'] or len(report['rows']) != 8):
        raise ValueError('closed, owned server and audited comparison required')
    # Do not infer cleanup from a stale status record alone, and never kill a PID.
    for field in ('pid', 'supervisor_pid'):
        result = subprocess.run(['ps', '-p', str(server[field]), '-o', 'command='],
                                capture_output=True, text=True, timeout=10)
        if result.returncode != 1 or result.stdout.strip():
            raise ValueError('recorded process still exists; inspect its identity before closing')
    record = Path(server['record_directory'])
    if not record.is_absolute(): record = storage / record
    if read(record / 'summary.json') != server:
        raise ValueError('final server summary differs from pipeline copy')
    memory = [json.loads(line) for line in (record / 'memory.jsonl').read_text().splitlines()]
    keys = ('status', 'stop_reason', 'started_at', 'wall_seconds', 'load_wall_seconds',
            'sampled_peak_rss_bytes', 'peak_system_swap_bytes', 'exit_code', 'model_revision',
            'runtime', 'ctx_size', 'cache_type_k', 'cache_type_v', 'memory_note')
    out = {k: server[k] for k in keys}
    out.update(phase='P88', checked_at=datetime.now(timezone.utc).isoformat(),
        owned_processes_absent=True, baseline_system_swap_bytes=memory[0]['swap_used_bytes'],
        source_sha256=sha(record / 'summary.json'), memory_source_sha256=sha(record / 'memory.jsonl'),
        pipeline_source_sha256=sha(folder / 'status.json'), inspector_sha256=sha(Path(__file__)),
        audit_source_sha256=sha(ROOT / 'reports/P88_comparison.json'),
        scope='P88 new eight-cell server session only. Earlier P82/P87 sessions are excluded. Load, preflight, task initialization, work, evaluation, cleanup and idle gaps are included.',
        evaluation_wall_seconds=None,
        evaluation_time_note='Per-evaluation subprocess wall measurements are included in batch/server time; do not add them again.',
        pipeline_wall_seconds=state['wall_seconds'], stages=state['stages'],
        additional_model_calls=0, additional_api_requests=0, additional_evaluator_calls=0)
    batch = next((s for s in state['stages'] if s['mode'] == 'batch'), None)
    rows = report['rows']
    measured = read(storage / 'records/context_pilot/P88_batch_v01/status.json')
    out['evaluation_wall_seconds'] = sum(r.get('evaluation_wall_seconds', 0) for r in measured['rows'])
    out['evaluations_completed'] = len(measured['completed'])
    out['evaluation_attempts_measured'] = sum('evaluation_wall_seconds' in r for r in measured['rows'])
    out['cell_full_wall_seconds'] = sum(r.get('full_wall_seconds', 0) for r in rows)
    out['idle_recovery_seconds'] = sum(r.get('idle_recovery', {}).get('wall_seconds', 0) for r in measured['rows'])
    out['batch_other_wall_seconds'] = (batch['wall_seconds'] - out['cell_full_wall_seconds']
        - out['idle_recovery_seconds']) if batch else None
    out['batch_other_time_note'] = 'Includes evaluation, parent process overhead and record writing; not isolated evaluation time.'
    if out['batch_other_wall_seconds'] is not None and out['batch_other_wall_seconds'] < 0:
        raise ValueError('cell timing exceeds batch duration')
    out['overlap_note'] = 'Cell full time includes setup, work and cleanup; notification construction, input counting and feedback are inside work. Do not sum overlapping measures.'
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    args = p.parse_args(); target = ROOT / 'reports/P88_server_session.json'
    if target.exists(): raise FileExistsError('preserve prior session inspection')
    result = inspect(args.storage_root); write_json(target, result)
    print({k: result[k] for k in ('status', 'wall_seconds', 'cell_full_wall_seconds', 'batch_other_wall_seconds')})

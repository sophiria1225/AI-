"""Close only the four new P137 cells and their server cost ledger using saved records, without running experiments."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess

from whole_task_remaining_late_obligations_p137 import cell_id, run_order, SEEDS
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def cell_time_totals(rows):
    """Unstarted cells cost zero; started cells without measurements stay unknown."""
    known, unknown = 0.0, 0
    for row in rows:
        value = row.get('full_wall_seconds')
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            known += value
        elif row['record_status'] != 'not_run':
            unknown += 1
    return dict(known_cell_full_wall_seconds=known,
                unknown_cell_full_wall_count=unknown,
                cell_full_wall_seconds=known if unknown == 0 else None)


def attempt_time_totals(rows, kind):
    """Persisted starts distinguish unattempted from killed/missing timing."""
    if kind not in ('evaluation', 'idle_recovery'):
        raise ValueError('bounded_P137_attempt_kind_required')
    known, unknown, attempts = 0.0, 0, 0
    for row in rows:
        started = kind + '_started_at' in row
        value = (row.get('evaluation_wall_seconds') if kind == 'evaluation'
                 else row.get('idle_recovery', {}).get('wall_seconds'))
        if value is not None or started:
            attempts += 1
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                known += value
            else:
                unknown += 1
    return dict(known_subtotal=known, unknown_attempts=unknown, attempts=attempts,
                exact_total=known if unknown == 0 else None)


def inspect(storage, root=ROOT):
    storage, root = Path(storage), Path(root)
    folder = storage / 'records/context_pilot/P137_pipeline_v01'
    state, server = (read(folder / name) for name in ('status.json', 'server_final.json'))
    report = read(root / 'reports/P137_comparison.json')
    if (state['status'] not in ('complete', 'stopped') or not state['server_stopped']
            or server['status'] != 'stopped' or state['server_supervisor_pid'] != server['supervisor_pid']
            or report.get('phase') != 'P137' or type(report['audit_errors']) is not list or len(report['rows']) != len(run_order())
            or report.get('owned_processes_absent') is not True
            or report['pipeline_status_sha256'] != sha(folder / 'status.json')
            or report['server_final_sha256'] != sha(folder / 'server_final.json')):
        raise ValueError('closed, owned server and audited comparison required')
    expected = [(cell_id(rep, number, mode), rep, SEEDS[rep - 1], mode)
                for rep, number, mode in run_order()]
    if (not all(type(r.get('replication')) is int and type(r.get('model_seed')) is int
                and r.get('checkpoint_policy') == 'rolling_separate'
                for r in report['rows'])
            or [(r.get('run_id'), r.get('replication'), r.get('model_seed'), r.get('obligation_mode'))
                for r in report['rows']] != expected):
        raise ValueError('all_four_fixed_remaining_cells_required')
    # Do not infer cleanup from a stale status record alone, and never kill a PID.
    for field in ('pid', 'supervisor_pid'):
        if type(server.get(field)) is not int or server[field] <= 0:
            raise ValueError('positive_owned_server_PID_required')
        result = subprocess.run(['ps', '-p', str(server[field]), '-o', 'command='],
                                capture_output=True, text=True, timeout=10)
        if result.returncode != 1 or result.stdout.strip():
            raise ValueError('recorded process still exists; inspect its identity before closing')
    record = Path(server['record_directory'])
    if not record.is_absolute(): record = storage / record
    if not record.resolve().is_relative_to((storage/'records/p2_servers').resolve()):
        raise ValueError('owned_server_record_root_required')
    if read(record / 'summary.json') != server:
        raise ValueError('final server summary differs from pipeline copy')
    memory = [json.loads(line) for line in (record / 'memory.jsonl').read_text().splitlines()]
    for sample in memory:
        for name in ('rss_bytes', 'swap_used_bytes'):
            value=sample.get(name)
            if value is not None and not (type(value) in (int,float) and math.isfinite(value) and value>=0):
                raise ValueError('invalid_memory_sample')
    keys = ('status', 'stop_reason', 'started_at', 'wall_seconds', 'load_wall_seconds',
            'sampled_peak_rss_bytes', 'peak_system_swap_bytes', 'exit_code', 'model_revision',
            'runtime', 'ctx_size', 'cache_type_k', 'cache_type_v', 'memory_note')
    out = {k: server[k] for k in keys}
    out.update(phase='P137', checked_at=datetime.now(timezone.utc).isoformat(),
        owned_processes_absent=True, baseline_system_swap_bytes=memory[0].get('swap_used_bytes') if memory else None,
        memory_sample_count=len(memory),
        missing_rss_samples=sum(m.get('rss_bytes') is None for m in memory),
        missing_swap_samples=sum(m.get('swap_used_bytes') is None for m in memory),
        observed_rss_peak_or_null=max((m['rss_bytes'] for m in memory if m.get('rss_bytes') is not None),default=None),
        observed_swap_peak_or_null=max((m['swap_used_bytes'] for m in memory if m.get('swap_used_bytes') is not None),default=None),
        source_sha256=sha(record / 'summary.json'), memory_source_sha256=sha(record / 'memory.jsonl'),
        pipeline_source_sha256=sha(folder / 'status.json'), inspector_sha256=sha(Path(__file__)),
        audit_source_sha256=sha(root / 'reports/P137_comparison.json'),
        cell_audit_error_count=len(report['audit_errors']),
        scope='P137 new four-cell server session only; seed57 is unpaired, seed157 is descriptive. All earlier sessions are excluded. Load, preflight, task initialization, work, evaluation, cleanup and idle gaps are included.',
        evaluation_wall_seconds=None,
        evaluation_time_note='Per-evaluation subprocess wall measurements are included in batch/server time; do not add them again.',
        pipeline_wall_seconds=state['wall_seconds'], stages=state['stages'],
        additional_model_calls=0, additional_api_requests=0, additional_evaluator_calls=0)
    batch = next((s for s in state['stages'] if s['mode'] == 'batch'), None)
    rows = report['rows']
    measured = read(storage / 'records/context_pilot/P137_batch_v01/status.json')
    evaluations = attempt_time_totals(measured['rows'], 'evaluation')
    idle = attempt_time_totals(measured['rows'], 'idle_recovery')
    out['evaluation_wall_seconds'] = evaluations['exact_total']
    out['known_evaluation_wall_seconds'] = evaluations['known_subtotal']
    out['unknown_evaluation_wall_count'] = evaluations['unknown_attempts']
    out['evaluations_completed'] = len(measured['completed'])
    out['evaluation_attempts_measured'] = sum('evaluation_wall_seconds' in r for r in measured['rows'])
    out.update(cell_time_totals(rows))
    out['idle_recovery_seconds'] = idle['exact_total']
    out['known_idle_recovery_seconds'] = idle['known_subtotal']
    out['unknown_idle_recovery_count'] = idle['unknown_attempts']
    out['batch_other_wall_seconds'] = (batch['wall_seconds'] - out['cell_full_wall_seconds']
        - out['idle_recovery_seconds']) if batch and out['cell_full_wall_seconds'] is not None and idle['exact_total'] is not None else None
    out['batch_other_time_note'] = 'Includes evaluation, parent process overhead and record writing; not isolated evaluation time.'
    if out['batch_other_wall_seconds'] is not None and out['batch_other_wall_seconds'] < 0:
        raise ValueError('cell timing exceeds batch duration')
    out['overlap_note'] = 'Cell full time includes setup, work and cleanup; obligation evidence tracking, notification construction, summary generation, input counting and feedback are inside work. Do not sum overlapping measures.'
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    args = p.parse_args(); target = args.repo_root / 'reports/P137_server_session.json'
    if target.exists(): raise FileExistsError('preserve prior session inspection')
    result = inspect(args.storage_root, args.repo_root); write_json(target, result)
    print({k: result[k] for k in ('status', 'wall_seconds', 'cell_full_wall_seconds', 'batch_other_wall_seconds')})

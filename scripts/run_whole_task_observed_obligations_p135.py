"""Finite P135 comparison: original P123 anchor and common-capability disclosure pair."""
import argparse
import datetime as dt
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition, task_snapshot
from whole_task_observed_obligations_p135 import MODES, SEEDS
from whole_task_observed_obligations_p135 import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation, tools_for)
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from fixed_budget_local_llama import count_input as count_summary_input, payload_for as summary_payload
from rolling_checkpoint_history import SUMMARY_PROMPT
from obligation_server_identity_p135 import live_identity, wait_idle
from residual_output_budget import admission
from run_whole_task_observed_obligations_cell_p135 import run_cell
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P135_whole_task_observed_obligations_v01.json'
PREFLIGHT = 'reports/P135_initial_checks.json'
ACTIVATION = 'reports/P135_activation_v01.json'


def sources(storage, root):
    if root.resolve() != ROOT.resolve():
        raise ValueError('executing_P135_repository_must_match')
    plan = read(root / PLAN); validate_plan(plan)
    for rel, expected in plan['source_sha256'].items():
        if sha(root / rel) != expected:
            raise ValueError('fixed_source_changed:' + rel)
    from run_whole_task_tool_choice import sources as original_sources
    previous, original, tools, prepared = original_sources(storage, root)
    selected = [t for t in previous['known_tasks'] if t['source_run'] == 'P29_04_CODE']
    prepared = [t for t in prepared if t['source_run'] == 'P29_04_CODE']
    if (len(selected) != 1 or len(prepared) != 1 or plan['known_tasks'] != selected
            or any(plan[k] != previous[k] for k in ('source_plan', 'world_seed'))
            or original['api_budget_by_task'][selected[0]['task_id']] != 80):
        raise ValueError('same_known_P123_CSV_task_and_API80_required')
    if predecessor_closed(storage, root) != plan['predecessor_closure']:
        raise ValueError('P135_predecessor_closure_changed')
    return plan, original, tools, prepared


def predecessor_closed(storage, root):
    """The successful ordinary P123 control remains a separate historical cohort."""
    folder = storage / 'records/context_pilot/P123_pipeline_v01'
    state, final = read(folder / 'status.json'), read(folder / 'server_final.json')
    report, session = root / 'reports/P123_comparison.json', root / 'reports/P123_server_session.json'
    audit, accounting = read(report), read(session)
    if (state.get('status') not in ('complete', 'stopped') or state.get('server_stopped') is not True
            or final.get('status') != 'stopped' or final.get('supervisor_pid') != state.get('server_supervisor_pid')
            or audit.get('phase') != 'P123' or len(audit.get('rows', [])) != 12
            or audit.get('audit_errors') or audit.get('owned_processes_absent') is not True
            or accounting.get('phase') != 'P123' or accounting.get('status') != 'stopped'
            or accounting.get('owned_processes_absent') is not True
            or audit.get('pipeline_status_sha256') != sha(folder / 'status.json')
            or audit.get('server_final_sha256') != sha(folder / 'server_final.json')
            or accounting.get('audit_source_sha256') != sha(report)):
        raise ValueError('closed_audited_P123_required')
    return {str(p.relative_to(root)): sha(p) for p in (report, session)}


def launch_predecessor_closed(storage):
    """Consume the separate P133 data-only recovery and P134 unstarted failure.

    No scientific outcome filters the next cohort. The original reporting and
    queue failures remain required evidence; this function launches nothing.
    """
    from whole_task_checkpoint_payback import cell_id as prior_id, run_order as prior_order
    storage = Path(storage).resolve()
    for phase in ('P133', 'P134', 'P135'):
        if (storage / f'.runtime/{phase}.stop').exists():
            raise InterruptedError('explicit_' + phase + '_stop_prevents_next_cohort')
    paths = []
    def load(path):
        paths.append(path)
        return read(path)
    def fixed_hash(path, expected):
        if (not isinstance(expected, str) or len(expected) != 64
                or any(c not in '0123456789abcdef' for c in expected)
                or path.is_symlink() or not path.is_file() or sha(path) != expected):
            raise ValueError('P133_recovery_source_or_artifact_changed')
        paths.append(path)
    def relative(root, name):
        value = Path(name)
        if (not isinstance(name, str) or not name or value.is_absolute()
                or '..' in value.parts or '\\' in name):
            raise ValueError('P133_recovery_relative_path_required')
        result = root / value
        if result.is_symlink() or not result.resolve().is_relative_to(root.resolve()):
            raise ValueError('P133_recovery_source_path_escape')
        return result
    marker = load(storage / '.runtime/P133_reporting_recovery_v01_complete.json')
    prior_head = '66d9eb71a1e6b8ee10b377be3bf52dca82d06cca'
    prior_plan_sha = '357c59a73ed9637e9171d6729f8f4210533fef90d598ec667fa1d7154d09d986'
    recovery = storage / '.runtime/worktrees/p133-results-recovery'
    if (marker.get('status') != 'complete' or marker.get('original_head') != prior_head
            or marker.get('original_plan_sha256') != prior_plan_sha
            or type(marker.get('completed_conditions')) is not int or marker['completed_conditions'] != 4
            or marker.get('owned_processes_absent') is not True
            or marker.get('recovery_root') != str(recovery)
            or any(type(marker.get(k)) is not int or marker[k] != 0 for k in
                ('additional_model_calls','additional_API_requests','additional_evaluations','additional_tokenizer_calls',
                 'original_audit_exit_code','original_session_exit_code'))):
        raise ValueError('complete_zero_call_P133_reporting_recovery_required')
    head = marker.get('source_head')
    if (not isinstance(head, str) or len(head) != 40 or any(c not in '0123456789abcdef' for c in head)
            or subprocess.check_output(['git','rev-parse','HEAD'], cwd=recovery, text=True).strip() != head):
        raise ValueError('P133_recovery_head_changed')
    if marker.get('original_failure_path') != '.runtime/P133_report_once_end.json':
        raise ValueError('original_P133_report_failure_required')
    fixed_hash(storage / marker['original_failure_path'], marker['original_failure_sha256'])
    fixed_hash(storage / '.runtime/P133_report_once.log', marker['original_report_log_sha256'])
    for stage, expected in (('audit',0),('session',0),('report',1)):
        original = load(storage / f'.runtime/P133_{stage}_once_end.json')
        if type(original.get('exit_code')) is not int or original['exit_code'] != expected:
            raise ValueError('original_P133_stage_failure_changed')
    source_map = marker.get('recovery_source_sha256')
    if type(source_map) is not dict or not source_map:
        raise ValueError('recovery_source_binding_required')
    for rel, wanted in source_map.items():
        fixed_hash(relative(recovery,rel), wanted)
    wanted_paths = dict(audit_path='reports/P133_comparison.json', session_path='reports/P133_server_session.json',
        recovery_manifest_path='materials/20261027_p133_results_recovery_v01/build_manifest.json')
    for key, rel in wanted_paths.items():
        if marker.get(key) != rel:
            raise ValueError('fixed_P133_recovery_report_paths_required')
    run = storage / '.runtime/worktrees/p133-run'
    for key, report_key in (('audit_path','audit_sha256'),('session_path','session_sha256')):
        fixed_hash(relative(recovery,marker[key]), marker[report_key])
        fixed_hash(relative(run,marker[key]), marker[report_key])
    manifest_path = relative(recovery,marker['recovery_manifest_path'])
    fixed_hash(manifest_path, marker['recovery_manifest_sha256'])
    manifest = load(manifest_path)
    for name, base in (('source_sha256',recovery),('artifact_sha256',manifest_path.parent)):
        mapping = manifest.get(name)
        if type(mapping) is not dict or not mapping:
            raise ValueError('recovery_manifest_bindings_required')
        for rel, wanted in mapping.items():
            fixed_hash(relative(base,rel), wanted)
    folder = storage / 'records/context_pilot/P133_pipeline_v01'
    state = load(folder / 'status.json'); final = load(folder / 'server_final.json')
    batch = load(storage / 'records/context_pilot/P133_batch_v01/status.json')
    started = load(storage / '.runtime/P133_pipeline_once_start.json')
    fixed_hash(run / 'configs/P133_whole_task_checkpoint_payback_v01.json', prior_plan_sha)
    if (state.get('phase') != 'P133_pipeline' or state.get('status') not in ('complete','stopped')
            or state.get('git_commit') != prior_head or state.get('server_stopped') is not True
            or final.get('status') != 'stopped' or final.get('supervisor_pid') != state.get('server_supervisor_pid')
            or batch.get('phase') != 'P133' or batch.get('status') not in ('complete','stopped')
            or batch.get('planned') != [prior_id(*row) for row in prior_order()]
            or started.get('source_head') != prior_head or started.get('plan_sha256') != prior_plan_sha):
        raise ValueError('original_P133_closed_pipeline_required')
    audit = load(recovery / marker['audit_path']); session = load(recovery / marker['session_path'])
    expected = [(prior_id(rep,num,mode),rep,57 if rep == 1 else 157,mode) for rep,num,mode in prior_order()]
    rows = audit.get('rows')
    if (audit.get('phase') != 'P133' or type(rows) is not list or len(rows) != 4
            or [(row.get('run_id'),row.get('replication'),row.get('model_seed'),row.get('payback_mode')) for row in rows] != expected
            or any(type(row.get('replication')) is not int or type(row.get('model_seed')) is not int for row in rows)
            or audit.get('audit_errors') != [] or audit.get('owned_processes_absent') is not True
            or session.get('phase') != 'P133' or session.get('status') != 'stopped'
            or session.get('owned_processes_absent') is not True or session.get('audit_source_sha256') != marker['audit_sha256']
            or audit.get('pipeline_status_sha256') != sha(folder/'status.json')
            or audit.get('server_final_sha256') != sha(folder/'server_final.json')):
        raise ValueError('exact_closed_audited_P133_rows_required')
    for pid in (final.get('pid'),final.get('supervisor_pid')):
        if type(pid) is not int or pid <= 0:
            raise ValueError('positive_owned_P133_pid_required')
        process = subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=10)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('previous_owned_P133_process_present')
    # P134 never reached a server, preflight or task. Preserve the failed queue,
    # rather than silently restarting its fixed namespace.
    queue_end = load(storage / '.runtime/P134_queue_after_P133_once_end.json')
    queue_start = load(storage / '.runtime/P134_queue_after_P133_once_start.json')
    queue_head = 'dda97636b88ad3126647e101af9e720f745e5ec7'
    queue_sha = '888377b8c7392cfcd8664bd3ccc4c81c59b0a52d7952fc990bf68412bb216c4b'
    if (queue_end.get('status') != 'failed_no_retry' or queue_end.get('child_started') is not False
            or queue_end.get('source_head') != queue_head or queue_end.get('queue_source_sha256') != queue_sha
            or queue_start.get('source_head') != queue_head or queue_start.get('queue_source_sha256') != queue_sha
            or type(queue_start.get('queue_pid')) is not int or queue_start['queue_pid'] <= 0):
        raise ValueError('P134_failed_unstarted_queue_required')
    fixed_hash(storage / '.runtime/queue_p134_after_p133_once_20261027.py', queue_sha)
    process = subprocess.run(['ps','-p',str(queue_start['queue_pid']),'-o','command='],capture_output=True,text=True,timeout=10)
    if process.returncode != 1 or process.stdout.strip():
        raise ValueError('P134_queue_still_present')
    forbidden = [storage / rel for rel in ('.runtime/P134_pipeline_once_start.json',
        '.runtime/P134_pipeline_child_once.json','.runtime/P134_queue_after_P133_once_child.json',
        '.runtime/P134_pipeline_once_end.json','.runtime/P134_pipeline_once.log',
        '.runtime/P134_report_collector_once_start.json','.runtime/P134_report_collector_once_end.json',
        'records/context_pilot/P134_pipeline_v01','records/context_pilot/P134_preflight_v01',
        'records/context_pilot/P134_batch_v01')]
    if any(path.exists() or path.is_symlink() for path in forbidden) or list((storage/'records/context_pilot').glob('BOC_P134_R*_01_*')):
        raise ValueError('P134_model0_unstarted_evidence_contradicted')
    return {str(path.relative_to(storage)):sha(path) for path in sorted(set(paths))}



def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P135_whole_task_observed_obligations.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def validate_preflight(storage, root, pre, plan, original, prepared):
    """Validate saved counts/identities without recounting or generating anything."""
    validate_plan(plan)
    required = dict(phase='P135_preflight', status='complete', all_six_inputs_checked=True,
        input_count_requests=6, summary_input_count_requests=2, failed_input_count_requests=0,
        model_generations=0, environment_api_requests=0, evaluator_calls=0, reserved_scenarios_read=0)
    if (type(pre) is not dict or any(type(pre.get(k)) is not type(v) or pre[k] != v
            for k, v in required.items()) or pre.get('source_hashes') != frozen_hashes(root)
            or pre.get('research_resume') != check_resume(storage)
            or pre.get('launch_predecessor_closure') != launch_predecessor_closed(storage)):
        raise ValueError('P135_preparation_incomplete_or_stale')
    if (type(pre.get('rows')) is not list or len(pre['rows']) != 2
            or len(prepared) != 1 or any(prepared[i]['task_id'] != task['task_id']
                or prepared[i]['source_run'] != task['source_run']
                for i, task in enumerate(plan['known_tasks']))):
        raise ValueError('one_known_P135_CSV_preflight_identity_required')
    folder = storage / 'records/context_pilot/P135_preflight_v01'
    def count_record(value):
        return (type(value) is dict and type(value.get('input_tokens')) is int
                and value['input_tokens'] > 0 and type(value.get('wall_seconds')) in (int, float)
                and math.isfinite(value['wall_seconds']) and value['wall_seconds'] >= 0)
    for (replication, item), row in zip([(rep, item) for rep in (1, 2) for item in prepared], pre['rows'], strict=True):
        if (type(row) is not dict or type(row.get('replication')) is not int
                or type(row.get('model_seed')) is not int
                or row.get('replication') != replication or row.get('model_seed') != SEEDS[replication - 1]
                or row.get('source_run') != item['source_run']
                or row.get('task_id') != item['task_id'] or type(row.get('conditions')) is not dict
                or set(row['conditions']) != set(MODES)):
            raise ValueError('exact_P135_pair_identity_required')
        pair = []
        for policy in MODES:
            entry = row['conditions'][policy]
            config = config_for(original, plan, item['task_id'], policy, replication)
            base, formatting = initial_conversation(original, item['public_task'], policy).for_model()
            if any(formatting.get(k) != 0 for k in ('text_fallback_turns', 'paged_spans')):
                raise ValueError('unexpected_initial_formatting')
            state = task_snapshot(config, [], 0, 0)
            supplied, visible = make_notification(base, state, policy, wall_limit=plan['max_wall_seconds'])
            cfg = {**config['model'], 'temperature': original['agent_temperature'],
                'seed': config['seed'], 'num_predict': original['max_output_tokens'], 'cache_prompt': False}
            message_path = folder / (f'R{replication:02d}_' + item['source_run'] + '_' + policy + '_private.json')
            request_path = folder / (f'R{replication:02d}_' + item['source_run'] + '_' + policy + '_request_private.json')
            if (not count_record(entry) or entry.get('reasoning_budget_tokens') != -1
                    or type(entry.get('reasoning_budget_tokens')) is not int
                    or entry.get('tool_choice') != 'auto'
                    or entry.get('base_messages_sha256') != digest(base)
                    or entry.get('model_messages_sha256') != digest(supplied)
                    or digest(entry.get('measured_state')) != digest(state)
                    or digest(entry.get('visible_state')) != digest(visible)
                    or entry.get('input_sha256') != sha(message_path)
                    or digest(read(message_path)) != digest(supplied)
                    or entry.get('count_request_sha256') != sha(request_path)
                    or digest(read(request_path)) != digest(payload_for(cfg, supplied, tools_for(policy)))):
                raise ValueError('P135_count_input_request_or_usage_changed')
            expected_admission = admission(plan['max_total_tokens'], entry['input_tokens'],
                cfg['num_predict'], cfg['num_ctx'], 'residual')
            if digest(entry.get('admission')) != digest(expected_admission) or not expected_admission['admitted']:
                raise ValueError('P135_initial_admission_changed')
            pair.append((entry['input_tokens'], supplied, visible, read(request_path)))
        if pair[1] != pair[2]:
            raise ValueError('primary_pair_initial_inputs_must_match')
    sample = [{'role': 'system', 'content': SUMMARY_PROMPT}, {'role': 'user',
        'content': '{"original_instructions_and_task":[],"older_history":[],"recent_context":[]}'}]
    if type(pre.get('summary_transport')) is not dict or set(pre['summary_transport']) != {'57', '157'}:
        raise ValueError('both_fixed_seed_summary_transports_required')
    for seed in SEEDS:
        cfg = {**config['model'], 'temperature': config['draft_temperature'],
               'seed': seed, 'num_predict': config['max_output_tokens'], 'cache_prompt': True}
        path = folder / f'summary_transport_seed{seed}_request_private.json'
        counted = pre['summary_transport'][str(seed)]
        if (not count_record(counted) or counted.get('request_sha256') != sha(path)
                or digest(read(path)) != digest(summary_payload(cfg, sample, []))):
            raise ValueError('P135_summary_count_transport_or_usage_changed')


def validate_activation(storage, root, freeze):
    if (freeze.get('phase') != 'P135'
            or freeze.get('all_six_conditions_frozen_before_generation') is not True
            or freeze.get('source_hashes') != frozen_hashes(root)
            or freeze.get('preflight_sha256') != sha(root / PREFLIGHT)
            or freeze.get('research_resume') != check_resume(storage)):
        raise ValueError('frozen_P135_sources_or_resumption_changed')


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P135_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P135_preflight_attempts')
    plan, original, _, prepared = sources(storage, root)
    preceding_session = launch_predecessor_closed(storage)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 480)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P135_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'launch_predecessor_closure': preceding_session,
        'input_count_requests': 0, 'summary_input_count_requests': 0, 'failed_input_count_requests': 0,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_six_inputs_checked': False}
    try:
        for replication, item in [(rep, item) for rep in (1, 2) for item in prepared]:
            row = {'replication': replication, 'model_seed': SEEDS[replication - 1],
                   'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in MODES:
                if (storage / '.runtime/P135.stop').exists():
                    raise InterruptedError('explicit_P135_stop')
                remaining = 420 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P135_preflight_deadline')
                config = config_for(original, plan, item['task_id'], arm, replication)
                base, formatting = initial_conversation(original, item['public_task'], arm).for_model()
                if any(formatting.get(k) != 0 for k in ('text_fallback_turns', 'paged_spans')):
                    raise ValueError('unexpected_initial_formatting')
                state = task_snapshot(config, [], 0, 0)
                supplied, visible = make_notification(base, state, arm, wall_limit=plan["max_wall_seconds"])
                path = folder / (f'R{replication:02d}_' + item['source_run'] + '_' + arm + '_private.json')
                write_json(path, supplied)
                entry = {'base_messages_sha256': digest(base), 'model_messages_sha256': digest(supplied),
                         'input_sha256': sha(path), 'measured_state': state, 'visible_state': visible}
                row['conditions'][arm] = entry
                cfg = {**config['model'], 'temperature': original['agent_temperature'],
                       'seed': config['seed'], 'num_predict': original['max_output_tokens'],
                       'cache_prompt': False}
                request_path = folder / (f'R{replication:02d}_' + item['source_run'] + '_' + arm + '_request_private.json')
                write_json(request_path, payload_for(cfg, supplied, tools_for(arm)))
                entry['count_request_sha256'] = sha(request_path)
                entry['reasoning_budget_tokens'] = cfg['reasoning_budget_tokens']
                entry['tool_choice'] = cfg['tool_choice']
                result['input_count_requests'] += 1
                try:
                    entry.update(count_input(cfg, supplied, tools_for(arm), timeout=min(30, remaining)))
                except Exception:
                    result['failed_input_count_requests'] += 1
                    raise
                entry['admission'] = admission(plan['max_total_tokens'], entry['input_tokens'],
                                               cfg['num_predict'], cfg['num_ctx'], 'residual')
                if not entry['admission']['admitted']:
                    raise ValueError('initial_request_does_not_fit')
                write_json(folder / 'status.json', result)
            entries = [row['conditions'][arm] for arm in ('counts_only','entity_fields')]
            if any(e['model_messages_sha256'] != entries[0]['model_messages_sha256']
                   or e['base_messages_sha256'] != entries[0]['base_messages_sha256']
                   or e['visible_state'] != entries[0]['visible_state']
                   or e['input_tokens'] != entries[0]['input_tokens'] for e in entries):
                raise ValueError('primary_pair_initial_inputs_must_match')
            requests = [read(folder / (f'R{replication:02d}_' + item['source_run'] + '_' + arm + '_request_private.json')) for arm in ('counts_only','entity_fields')]
            if any(request != requests[0] for request in requests) or requests[0]['tool_choice'] != 'auto':
                raise ValueError('same_primary_request_and_auto_tool_choice_required')
            if 'wall_seconds_at_snapshot' in entries[0]['visible_state']['remaining']:
                raise ValueError('hidden_time_was_exposed')
        # A separate vocabulary-only text transport check; no summary is generated.
        sample = [{'role': 'system', 'content': SUMMARY_PROMPT}, {'role': 'user',
            'content': '{"original_instructions_and_task":[],"older_history":[],"recent_context":[]}'}]
        result['summary_transport'] = {}
        for seed in SEEDS:
            cfg = {**config['model'], 'temperature': config['draft_temperature'],
                   'seed': seed, 'num_predict': config['max_output_tokens'], 'cache_prompt': True}
            path = folder / f'summary_transport_seed{seed}_request_private.json'
            request = summary_payload(cfg, sample, [])
            if 'tools' in request or 'tool_choice' in request or request['reasoning_budget_tokens'] != -1:
                raise ValueError('text_only_summary_transport_changed')
            write_json(path, request)
            result['summary_input_count_requests'] += 1
            try:
                result['summary_transport'][str(seed)] = count_summary_input(cfg, sample, [], timeout=30)
            except Exception:
                result['failed_input_count_requests'] += 1
                raise
            result['summary_transport'][str(seed)]['request_sha256'] = sha(path)
        result.update(status='complete', all_six_inputs_checked=True)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - started
        write_json(folder / 'status.json', result)
        write_json(target, result)
    return result


def activate(storage, root):
    if (root / ACTIVATION).exists():
        raise FileExistsError('preserve_P135_activation')
    if (storage / '.runtime/P135.stop').exists():
        raise InterruptedError('explicit_P135_stop_before_activation')
    plan, original, _, prepared = sources(storage, root)
    pre = read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    write_json(root / ACTIVATION, {'phase': 'P135', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_six_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def bounded_cell(storage, root, plan, replication, number, arm, rid, folder):
    command = [sys.executable, str(root / 'scripts/run_whole_task_observed_obligations_p135.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm, '--replication', str(replication)]
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        try:
            code = child.wait(timeout=plan['max_setup_seconds'] + plan['max_wall_seconds'] +
                              plan['max_cleanup_seconds'])
            if code:
                raise RuntimeError('P135_cell_worker_failed_no_retry')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
    return read(storage / 'records/context_pilot' / rid / 'summary.json')


def run_worker(storage, root, replication, number, arm):
    """Recheck frozen preparation and the owned live runtime before any cell."""
    rid = cell_id(replication, number, arm)
    if (storage / '.runtime/P135.stop').exists():
        raise InterruptedError('explicit_P135_stop')
    plan, original, tools, prepared = sources(storage, root)
    frozen, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    validate_activation(storage, root, frozen)
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, _ = live_identity(storage, original, max_cell)
    if identity != pre.get('model_identity'):
        raise ValueError('prepared_model_identity_changed')
    return run_cell(storage, root, plan, original, tools, prepared[number - 1],
                    ERROR_POLICY, rid, obligation_mode=arm, replication=replication)


def run(storage, root):
    plan, original, _, prepared = sources(storage, root)
    freeze, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    validate_activation(storage, root, freeze)
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, end = live_identity(storage, original, plan['max_cells'] * max_cell)
    if identity != pre['model_identity']:
        raise ValueError('prepared_model_identity_changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    for name, value in (('plan', plan), ('activation', freeze), ('preflight', pre)):
        write_json(folder / (name + '.json'), value)
    state = {'phase': 'P135', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
        'planned': [cell_id(rep, n, arm) for rep, n, arm in run_order()], 'model_identity': identity,
        'server_lease_end': end, 'reserved_scenarios_read': 0,
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
    def save():
        state['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(folder / 'status.json', state)
    try:
        save()
        for replication, number, arm in run_order():
            if (storage / '.runtime/P135.stop').exists():
                raise InterruptedError('explicit_P135_stop')
            current, _ = live_identity(storage, original, max_cell)
            if current != identity:
                raise ValueError('same_idle_inference_runtime_required')
            rid = cell_id(replication, number, arm)
            state['active'] = rid; save()
            result = bounded_cell(storage, root, plan, replication, number, arm, rid, folder)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'replication', 'model_seed', 'obligation_mode', 'time_visibility', 'checkpoint_policy', 'reasoning_budget_tokens', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'wall_seconds',
                'full_wall_seconds', 'cleanup_confirmed')}
            row['disposition'] = disposition(result)
            state['rows'].append(row); save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('P135_initialization_API_or_runtime_failure')
            row['idle_recovery_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            if (storage / '.runtime/P135.stop').exists():
                raise InterruptedError('explicit_P135_stop')
            evaluation_started = time.monotonic()
            row['evaluation_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
            try:
                evaluated = subprocess.run([str(storage / '.runtime/appworld/venv/bin/python'),
                    str(root / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                    str(storage / '.runtime/appworld/r18_probe_01'), '--trial',
                    str(storage / 'records/context_pilot' / rid)], capture_output=True, text=True,
                    timeout=plan['max_evaluation_seconds'])
            finally:
                row['evaluation_wall_seconds'] = time.monotonic() - evaluation_started
                save()
            (folder / (rid + '_evaluation.log')).write_text(evaluated.stdout + evaluated.stderr)
            if evaluated.returncode:
                raise ValueError('independent_P135_evaluation_failed')
            row['success'] = read(storage / 'records/context_pilot' / rid / 'evaluation.json')['official_success']
            state['completed'].append(rid); save()
            print({k: row[k] for k in ('run_id', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')}, flush=True)
        state.update(status='complete', active=None,
                     known_usage_complete=all(r['unknown_usage_calls'] == 0 for r in state['rows']))
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        state['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        state['not_run'] = [rid for rid in state['planned']
            if rid not in {r['run_id'] for r in state['rows']} and rid != state['active']]
        state['unevaluated'] = [r['run_id'] for r in state['rows'] if r['run_id'] not in state['completed']]
        save()
    return 0 if state['status'] == 'complete' else 1


def interrupt(*_):
    raise InterruptedError('bounded_P135_execution_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--activate', action='store_true')
    modes.add_argument('--cell', type=int, choices=(1,))
    parser.add_argument('--arm', choices=MODES)
    parser.add_argument('--replication', type=int, choices=(1, 2))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGINT, interrupt)
    if args.cell is not None:
        if args.arm is None or args.replication is None:
            parser.error('--cell requires --arm and --replication')
        run_worker(args.storage_root, args.repo_root, args.replication, args.cell, args.arm)
    elif args.preflight:
        result = preflight(args.storage_root, args.repo_root)
        print({k: result[k] for k in ('status', 'input_count_requests', 'failed_input_count_requests')})
    elif args.activate:
        activate(args.storage_root, args.repo_root)
    else:
        raise SystemExit(run(args.storage_root, args.repo_root))

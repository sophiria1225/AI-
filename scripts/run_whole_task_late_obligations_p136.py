"""Finite P136 comparison: original P123 anchor and common-capability disclosure pair."""
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
from whole_task_late_obligations_p136 import MODES, SEEDS
from whole_task_late_obligations_p136 import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation, tools_for)
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from fixed_budget_local_llama import count_input as count_summary_input, payload_for as summary_payload
from rolling_checkpoint_history import SUMMARY_PROMPT
from late_obligation_server_identity_p136 import live_identity, wait_idle
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P136_whole_task_late_obligations_v01.json'
PREFLIGHT = 'reports/P136_initial_checks.json'
ACTIVATION = 'reports/P136_activation_v01.json'


def sources(storage, root):
    if root.resolve() != ROOT.resolve():
        raise ValueError('executing_P136_repository_must_match')
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
        raise ValueError('P136_predecessor_closure_changed')
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


P135_HEAD = 'd87880f474c05541d8d0cde0ec318fd262d9fa0e'
P135_PLAN_SHA256 = '5a5b5338773f4a5b80ab61f9ccae9a3591c4f42ef8f458f2c38e4bc8894d8a2e'
P135_SOURCE_COUNT = 1498
P135_MARKER_SHA256 = {
    'P135_report_collector_once_end.json': '52a1d2bf48a3967bd3d211197408e753876274827f8468b8adfea093661da783',
    'P135_closure_once_end.json': 'ccdbc7733129a3248c44be94d8835111074baf22ec1b2166447c8fb3aefea8b8',
    'P135_closed_review_wait_once_end.json': 'ab5b7a9dda0c54086910ca2e3ba1a649bb46ff130d5afa7f7d502a559b335f67',
    'P135_figure_wait_once_end.json': 'a90a585c96268bf79dbcdc7d41aeb43e0d8d8a5a46ef7e17090d39e55100d47c',
    'P135_pipeline_once_start.json': 'da8397935efa2c268e35b843619a7ee28e42afadcd63d25d960fb3333dffae3c',
}
P135_PRIVATE_SHA256 = {
    'AI_P135_closed_independent_review_20261027.py': '93a9804228cc03f0abd9919eac6f0bdcb5c58cab94b485142ca6dc42055f39ce',
    'AI_P135_closed_independent_review_20261027.json': '52742c28f2a2e816f8b5f5768b9076348816e13de7b9da0c537901eeeb8c48ec',
    'wait_p135_closed_review_once_20261027.py': '13c9b859e0491767eebdee23443b3e0c710dbba3cda5e155d0f591444abb96ce',
    'wait_p135_figures_once_20261027.py': 'd39244f93c2c4bc5c5feb3f101a2ae13d6073dc5e70194f002b903875c42a13a',
    'draw_p135_results_20261027.py': '536bd31cb48f796d1dea2a0f834e187a3e445f72e5c6aa4d2d3874297d40d107',
    'AI_P135_actual_figures_20261027_v01/output_manifest.json': '6ef5c97f9ec7ddde64cf0a8802fe8e794041814c5a64f991bc12734a0e759309',
    'AI_P135_actual_figures_20261027_v01/figure_data.json': '4cb849b93754b6b872b0f19e3968d93a41c26042592425b07fc4913a5b066944',
}
PRIVATE_EVIDENCE_ROOT = Path('/private/tmp')


def launch_predecessor_closed(storage):
    """Read the immutable P135 closure; never rerun it or select by its quality."""
    from whole_task_observed_obligations_p135 import cell_id as prior_id, run_order as prior_order
    storage = Path(storage).resolve()
    for phase in ('P135', 'P136'):
        if (storage / f'.runtime/{phase}.stop').exists():
            raise InterruptedError('explicit_' + phase + '_stop_prevents_next_cohort')
    hashes = {}
    def bound(path, expected):
        if (type(expected) is not str or len(expected) != 64
                or any(c not in '0123456789abcdef' for c in expected)
                or path.is_symlink() or not path.is_file() or sha(path) != expected):
            raise ValueError('P135_predecessor_evidence_changed')
        if path.is_relative_to(storage): hashes[str(path.relative_to(storage))] = expected
        return path
    def relative(base, name):
        if (type(name) is not str or not name or '\\' in name or Path(name).is_absolute()
                or '..' in Path(name).parts or str(Path(name)) != name):
            raise ValueError('P135_safe_relative_source_required')
        p = base / name
        if p.is_symlink() or not p.resolve().is_relative_to(base.resolve()):
            raise ValueError('P135_predecessor_path_escape')
        return p
    # This is the first outcome-adjacent read. Missing/incomplete closure cannot
    # be replaced by partial reports or by a successful subset.
    collector_path = storage / '.runtime/P135_report_collector_once_end.json'
    bound(collector_path, P135_MARKER_SHA256[collector_path.name])
    collector = read(collector_path)
    if (collector.get('status') != 'complete'
            or any(type(collector.get(k)) is not int or collector[k] != 6
                   for k in ('planned_conditions','evaluated_conditions'))
            or collector.get('audit_passed') is not True
            or type(collector.get('audit_errors')) is not int or collector['audit_errors'] != 0):
        raise ValueError('all_six_closed_P135_required')
    markers = {collector_path.name: collector}
    for name, wanted in P135_MARKER_SHA256.items():
        if name != collector_path.name:
            markers[name] = read(bound(storage / '.runtime' / name, wanted))
    closure = markers['P135_closure_once_end.json']
    stages = closure.get('stages')
    if (type(stages) is not list or [x.get('stage') for x in stages] != ['audit','session','report']
            or any(type(x.get('exit_code')) is not int or x['exit_code'] != 0 for x in stages)
            or type(closure.get('pipeline_exit')) is not int or closure['pipeline_exit'] != 0):
        raise ValueError('P135_original_audit_session_report_000_required')
    review_end = markers['P135_closed_review_wait_once_end.json']
    figure_end = markers['P135_figure_wait_once_end.json']
    for d, code, started in ((review_end,'review_exit_code','review_started'),
                             (figure_end,'renderer_exit_code','renderer_started')):
        if (d.get('status') != 'complete' or d.get(started) is not True
                or type(d.get(code)) is not int or d[code] != 0
                or d.get('source_head') != P135_HEAD
                or d.get('collector_end_sha256') != sha(collector_path)):
            raise ValueError('P135_independent_review_and_figures_complete_required')
    for name,wanted in P135_PRIVATE_SHA256.items():
        bound(relative(PRIVATE_EVIDENCE_ROOT,name), wanted)
    review_name = 'AI_P135_closed_independent_review_20261027.json'
    review = read(PRIVATE_EVIDENCE_ROOT / review_name)
    if (review.get('status') != 'pass' or review.get('phase') != 'P135'
            or review.get('fixed_head') != P135_HEAD or review.get('plan_sha256') != P135_PLAN_SHA256
            or review.get('collector_complete_seen_before_trial_read') is not True
            or review.get('collector_end_sha256') != sha(collector_path)
            or review_end.get('reviewer_output_sha256') != P135_PRIVATE_SHA256[review_name]
            or figure_end.get('independent_review_sha256') != P135_PRIVATE_SHA256[review_name]
            or figure_end.get('figure_manifest_sha256') != P135_PRIVATE_SHA256['AI_P135_actual_figures_20261027_v01/output_manifest.json']):
        raise ValueError('P135_review_figure_chain_changed')
    started = markers['P135_pipeline_once_start.json']
    if (started.get('source_head') != P135_HEAD or started.get('plan_sha256') != P135_PLAN_SHA256
            or started.get('reserved_snapshot_sha256') != '52cfe1ecc0ca4aa004ed3965c10041d0346144b0d382fab2339399a895aaf0fb'
            or len(started.get('ledger_names_snapshot',[])) != 190):
        raise ValueError('P135_original_190_ledger_snapshot_required')
    run = storage / '.runtime/worktrees/p135-run'
    prep = storage / '.runtime/worktrees/p135-prep'
    plan_rel = 'configs/P135_whole_task_observed_obligations_v01.json'
    for tree in (run,prep):
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=tree,text=True).strip() != P135_HEAD:
            raise ValueError('P135_frozen_head_changed')
        bound(tree / plan_rel,P135_PLAN_SHA256)
    plan = read(run / plan_rel)
    mapping = plan.get('source_sha256')
    if type(mapping) is not dict or len(mapping) != P135_SOURCE_COUNT:
        raise ValueError('P135_original_source_scope_required')
    for rel,wanted in mapping.items():
        for tree in (run,prep): bound(relative(tree,rel),wanted)
    copies = collector.get('copied_source_sha256')
    expected_reports = {'reports/P135_initial_checks.json','reports/P135_activation_v01.json',
        'reports/P135_comparison.json','reports/P135_server_session.json',
        'materials/20261027_p135_results/README.md','materials/20261027_p135_results/conditions.csv',
        'materials/20261027_p135_results/summary.json','materials/20261027_p135_results/build_manifest.json'}
    if type(copies) is not dict or set(copies) != expected_reports:
        raise ValueError('all_original_P135_collector_artifacts_required')
    for rel,wanted in copies.items():
        for tree in (run,prep):bound(relative(tree,rel),wanted)
    for key,rel in [('audit_sha256','reports/P135_comparison.json'),
                    ('session_sha256','reports/P135_server_session.json'),
                    ('report_manifest_sha256','materials/20261027_p135_results/build_manifest.json')]:
        if closure.get(key) != copies[rel]: raise ValueError('P135_closure_report_binding_changed')
    folder = storage / 'records/context_pilot/P135_pipeline_v01'
    state, final = read(folder / 'status.json'), read(folder / 'server_final.json')
    audit = read(run / 'reports/P135_comparison.json')
    session = read(run / 'reports/P135_server_session.json')
    batch = read(storage / 'records/context_pilot/P135_batch_v01/status.json')
    expected = [(prior_id(rep,num,mode),rep,57 if rep==1 else 157,mode) for rep,num,mode in prior_order()]
    rows = audit.get('rows')
    if (state.get('phase') != 'P135_pipeline' or state.get('status') != 'complete'
            or state.get('git_commit') != P135_HEAD or state.get('server_stopped') is not True
            or final.get('status') != 'stopped' or type(final.get('supervisor_pid')) is not int
            or final['supervisor_pid'] != state.get('server_supervisor_pid')
            or audit.get('phase') != 'P135' or type(rows) is not list or len(rows) != 6
            or [(r.get('run_id'),r.get('replication'),r.get('model_seed'),r.get('obligation_mode')) for r in rows] != expected
            or any(type(r.get('replication')) is not int or type(r.get('model_seed')) is not int
                   or r.get('record_status') != 'evaluated' or type(r.get('success')) is not bool for r in rows)
            or audit.get('audit_errors') != [] or audit.get('owned_processes_absent') is not True
            or audit.get('pipeline_status_sha256') != sha(folder/'status.json')
            or audit.get('server_final_sha256') != sha(folder/'server_final.json')
            or session.get('phase') != 'P135' or session.get('status') != 'stopped'
            or session.get('owned_processes_absent') is not True
            or session.get('audit_source_sha256') != copies['reports/P135_comparison.json']
            or batch.get('status') != 'complete' or batch.get('planned') != [x[0] for x in expected]
            or batch.get('completed') != [x[0] for x in expected]):
        raise ValueError('P135_all_six_original_closed_records_required')
    for p in (folder/'status.json', folder/'server_final.json', storage/'records/context_pilot/P135_batch_v01/status.json'):
        hashes[str(p.relative_to(storage))] = sha(p)
    for pid in {started.get('wrapper_pid'),state.get('stage_pid'),final.get('pid'),final.get('supervisor_pid')}:
        if type(pid) is not int or pid <= 0: raise ValueError('positive_owned_P135_PID_required')
        process = subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=10)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('previous_owned_P135_process_present')
    return dict(storage_sha256=hashes, private_evidence_sha256=dict(P135_PRIVATE_SHA256),
                original_head=P135_HEAD, original_plan_sha256=P135_PLAN_SHA256,
                all_six_closed=True, outcomes_used_to_filter_conditions=False)



def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P136_whole_task_late_obligations.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def validate_preflight(storage, root, pre, plan, original, prepared):
    """Validate saved counts/identities without recounting or generating anything."""
    validate_plan(plan)
    required = dict(phase='P136_preflight', status='complete', all_six_inputs_checked=True,
        input_count_requests=6, summary_input_count_requests=2, failed_input_count_requests=0,
        model_generations=0, environment_api_requests=0, evaluator_calls=0, reserved_scenarios_read=0)
    if (type(pre) is not dict or any(type(pre.get(k)) is not type(v) or pre[k] != v
            for k, v in required.items()) or pre.get('source_hashes') != frozen_hashes(root)
            or pre.get('research_resume') != check_resume(storage)
            or pre.get('launch_predecessor_closure') != launch_predecessor_closed(storage)):
        raise ValueError('P136_preparation_incomplete_or_stale')
    if (type(pre.get('rows')) is not list or len(pre['rows']) != 2
            or len(prepared) != 1 or any(prepared[i]['task_id'] != task['task_id']
                or prepared[i]['source_run'] != task['source_run']
                for i, task in enumerate(plan['known_tasks']))):
        raise ValueError('one_known_P136_CSV_preflight_identity_required')
    folder = storage / 'records/context_pilot/P136_preflight_v01'
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
            raise ValueError('exact_P136_pair_identity_required')
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
                raise ValueError('P136_count_input_request_or_usage_changed')
            expected_admission = admission(plan['max_total_tokens'], entry['input_tokens'],
                cfg['num_predict'], cfg['num_ctx'], 'residual')
            if digest(entry.get('admission')) != digest(expected_admission) or not expected_admission['admitted']:
                raise ValueError('P136_initial_admission_changed')
            pair.append((entry['input_tokens'], supplied, visible, read(request_path)))
        if any(entry != pair[0] for entry in pair[1:]):
            raise ValueError('all_three_initial_inputs_must_match')
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
            raise ValueError('P136_summary_count_transport_or_usage_changed')


def validate_activation(storage, root, freeze):
    if (freeze.get('phase') != 'P136'
            or freeze.get('all_six_conditions_frozen_before_generation') is not True
            or freeze.get('source_hashes') != frozen_hashes(root)
            or freeze.get('preflight_sha256') != sha(root / PREFLIGHT)
            or freeze.get('research_resume') != check_resume(storage)):
        raise ValueError('frozen_P136_sources_or_resumption_changed')


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P136_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P136_preflight_attempts')
    plan, original, _, prepared = sources(storage, root)
    preceding_session = launch_predecessor_closed(storage)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 480)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P136_preflight', 'status': 'running', 'rows': [],
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
                if (storage / '.runtime/P136.stop').exists():
                    raise InterruptedError('explicit_P136_stop')
                remaining = 420 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P136_preflight_deadline')
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
            entries = [row['conditions'][arm] for arm in MODES]
            if any(e['model_messages_sha256'] != entries[0]['model_messages_sha256']
                   or e['base_messages_sha256'] != entries[0]['base_messages_sha256']
                   or e['visible_state'] != entries[0]['visible_state']
                   or e['input_tokens'] != entries[0]['input_tokens'] for e in entries):
                raise ValueError('all_three_initial_inputs_must_match')
            requests = [read(folder / (f'R{replication:02d}_' + item['source_run'] + '_' + arm + '_request_private.json')) for arm in MODES]
            if any(request != requests[0] for request in requests) or requests[0]['tool_choice'] != 'auto':
                raise ValueError('same_all_arm_request_and_auto_tool_choice_required')
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
        raise FileExistsError('preserve_P136_activation')
    if (storage / '.runtime/P136.stop').exists():
        raise InterruptedError('explicit_P136_stop_before_activation')
    plan, original, _, prepared = sources(storage, root)
    pre = read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    write_json(root / ACTIVATION, {'phase': 'P136', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_six_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def bounded_cell(storage, root, plan, replication, number, arm, rid, folder):
    command = [sys.executable, str(root / 'scripts/run_whole_task_late_obligations_p136.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm, '--replication', str(replication)]
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        try:
            code = child.wait(timeout=plan['max_setup_seconds'] + plan['max_wall_seconds'] +
                              plan['max_cleanup_seconds'])
            if code:
                raise RuntimeError('P136_cell_worker_failed_no_retry')
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
    if (storage / '.runtime/P136.stop').exists():
        raise InterruptedError('explicit_P136_stop')
    plan, original, tools, prepared = sources(storage, root)
    frozen, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    validate_activation(storage, root, frozen)
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, _ = live_identity(storage, original, max_cell)
    if identity != pre.get('model_identity'):
        raise ValueError('prepared_model_identity_changed')
    from run_whole_task_late_obligations_cell_p136 import run_cell
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
    state = {'phase': 'P136', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
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
            if (storage / '.runtime/P136.stop').exists():
                raise InterruptedError('explicit_P136_stop')
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
                raise ValueError('P136_initialization_API_or_runtime_failure')
            row['idle_recovery_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            if (storage / '.runtime/P136.stop').exists():
                raise InterruptedError('explicit_P136_stop')
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
                raise ValueError('independent_P136_evaluation_failed')
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
    raise InterruptedError('bounded_P136_execution_interrupted')


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

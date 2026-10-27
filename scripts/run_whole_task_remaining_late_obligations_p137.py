"""Finite P137 comparison: original P123 anchor and common-capability disclosure pair."""
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
from whole_task_remaining_late_obligations_p137 import MODES, SEEDS, modes_for_replication
from whole_task_remaining_late_obligations_p137 import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation, tools_for)
from budget_signal import digest
from container_data_python import docker_command
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from fixed_budget_local_llama import count_input as count_summary_input, payload_for as summary_payload
from rolling_checkpoint_history import SUMMARY_PROMPT
from remaining_late_obligation_server_identity_p137 import live_identity, wait_idle
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P137_remaining_late_obligations_v01.json'
PREFLIGHT = 'reports/P137_initial_checks.json'
ACTIVATION = 'reports/P137_activation_v01.json'


def sources(storage, root):
    if root.resolve() != ROOT.resolve():
        raise ValueError('executing_P137_repository_must_match')
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
        raise ValueError('P137_predecessor_closure_changed')
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


P136_HEAD = 'e65fa22d32bd63e80005e7bf807b2c91624e6824'
P136_PLAN_SHA256 = 'ff442f59f9012af6932974469fc5b2fbcb08afc3e8dd9cba4a480a9cc5f36f6a'
P136_PROVENANCE = 'reports/P136_results_provenance_20261027.json'
P136_PROVENANCE_SHA256 = '40e628cbf65afc00ead126fc834889eac4f47a66ec7c86566fabdbeebc6865aa'
P136_MARKER_SHA256 = {'.runtime/P136_pipeline_once_start.json': 'd6e3ab7c9c917ffd88e47753e9c962c7a0b11e55fd1e36db5556ba8ba3458795', '.runtime/P136_pipeline_once_end.json': 'f9bed53a3fc480a4b361999d41bb7d1e09898fd33d45b14694bbf1b6b4aa514f', '.runtime/P136_closure_once_end.json': 'b4ee3e42efc4d4bb38ee4239dcf471a741884d9c15da2a2ee6fafbad17207949', '.runtime/P136_report_collector_once_start.json': '47fbaaf6bf36ddafea41ef1ff058c43acf1fa163043345ba7f669c23cb597e29', '.runtime/P136_report_collector_once_end.json': 'e35a6edb95401bc63a1dfdb094bc45b623e11ff870ca9df0373c6956e7c6235a', '.runtime/P136_closed_review_wait_once_end.json': '433c32d172e23132718c9350a363cbf9b91a95d2e62980eddf4340960d15f92f', '.runtime/P136_figure_wait_once_end.json': 'ddfa0b4f403cde83a0cf763c0fc7cffb30186484164b89031368adbd5990f4f5', '.runtime/P136_reserved_ledger_snapshot_20261027.json': '12a6f8f9c5677ec9c09d4dd61a18e0fed7276d7ceabdf45df998ee0c3058a707', '.runtime/P136_incomplete_worker_container_cleanup_20261027.json': 'b76f6edd8669e37139b3275641a4968e7eddf2f80e617ea1f04730467ba918f9', '.runtime/P136_incomplete_worker_container_absence_20261027.json': '3b463202b407773fadbe7888c35ceba4e59c9c05bf5f17de9754b72fe61d8158'}
P136_PRIVATE_SHA256 = {'AI_P136_closed_independent_review_20261027.py': 'c6581939766317f47671b9948f2c36b463e35a4b01415b3fc8e5fd811f4c3fc8', 'AI_P136_closed_independent_review_20261027.json': '531018f4be5732ea298b9410b4503fa55cf7f2ab3fed9c3cb59ec2f93b6f0bfb', 'wait_p136_closed_review_once_20261027.py': '225053d65b6b5ebb148cd40d8df21ccbea1fba4143b41856cf44168ae4172583', 'draw_p136_results_20261027.py': '36a6102b0c43ec750f5f7174c0bc086222d5f6a7024800ca25746dc1875c5a62', 'wait_p136_figures_once_20261027.py': '5c02a3856889f52d540c2aefd7e03cad4ac9dfb9b9bb68977fe604de10e70225', 'AI_P136_actual_figures_20261027_v01/output_manifest.json': 'b27ed886ce68866b411a94163da312934df293b8fd6de3099da26572a6c2bd30'}
PRIVATE_EVIDENCE_ROOT = Path('/private/tmp')


def launch_predecessor_closed(storage):
    """Preserve P136's closed failure, incomplete accounting and four unrun slots.

    This never demands that all six executed, never reruns an audit and never
    repairs missing values. The bound sidecar proves a later separate container
    removal; live checks only test absence of the exact original owners.
    """
    storage = Path(storage).resolve()
    for phase in ('P136', 'P137'):
        if (storage / f'.runtime/{phase}.stop').exists():
            raise InterruptedError('explicit_' + phase + '_stop_prevents_next_cohort')
    bindings = {}; public_bindings = {}
    def safe(base, name):
        if (type(name) is not str or not name or Path(name).is_absolute()
                or '..' in Path(name).parts or '\\' in name or str(Path(name)) != name):
            raise ValueError('safe_P136_relative_path_required')
        p = base / name
        if p.is_symlink() or not p.resolve().is_relative_to(base.resolve()):
            raise ValueError('P136_evidence_path_escape')
        return p
    def bound(base, name, expected):
        p=safe(base,name)
        if not p.is_file() or type(expected) is not str or len(expected)!=64 or sha(p)!=expected:
            raise ValueError('P136_closed_evidence_changed')
        if base.resolve() == ROOT.resolve():public_bindings[name]=expected
        elif p.is_relative_to(storage):bindings[str(p.relative_to(storage))]=expected
        return p
    # First outcome-adjacent read requires the exact completed original collector.
    name='.runtime/P136_report_collector_once_end.json'
    collector=read(bound(storage,name,P136_MARKER_SHA256[name]))
    if (collector.get('status')!='complete' or type(collector.get('planned_conditions'))is not int
            or collector['planned_conditions']!=6 or type(collector.get('evaluated_conditions'))is not int
            or collector['evaluated_conditions']!=1 or collector.get('audit_passed')is not True
            or type(collector.get('audit_errors'))is not int or collector['audit_errors']!=0
            or collector.get('exact_total_tokens')is not None or collector.get('development_gate_met')is not False
            or collector.get('known_token_subtotal')!=332588 or collector.get('unknown_usage_count_missing_conditions')!=5):
        raise ValueError('closed_P136_original_missing_slots_required')
    markers={n:read(bound(storage,n,h)) for n,h in P136_MARKER_SHA256.items()}
    closure=markers['.runtime/P136_closure_once_end.json'];stages=closure.get('stages')
    if (type(stages)is not list or [(x.get('stage'),x.get('exit_code'))for x in stages]!=[('audit',0),('session',0),('report',0)]
            or any(type(x.get('exit_code'))is not int for x in stages)
            or type(closure.get('pipeline_exit'))is not int or closure['pipeline_exit']!=1
            or markers['.runtime/P136_pipeline_once_end.json'].get('exit_code')!=1):
        raise ValueError('P136_failed_pipeline_and_closed_000_required')
    started=markers['.runtime/P136_pipeline_once_start.json']
    registry=started.get('ledger_registry_text_snapshot')
    if (started.get('source_head')!=P136_HEAD or started.get('plan_sha256')!=P136_PLAN_SHA256
            or started.get('reserved_snapshot_sha256')!=P136_MARKER_SHA256['.runtime/P136_reserved_ledger_snapshot_20261027.json']
            or type(registry)is not str or digest_registry(registry)!=started.get('ledger_registry_sha256')
            or json_registry(registry)!=started.get('ledger_names_snapshot') or len(started['ledger_names_snapshot'])!=194
            or collector.get('prior_ledgers_unchanged')!=194 or collector.get('prior_bindings_unchanged')!=2389):
        raise ValueError('P136_original_194_snapshot_required')
    for n,h in P136_PRIVATE_SHA256.items():bound(PRIVATE_EVIDENCE_ROOT,n,h)
    reviewed=read(PRIVATE_EVIDENCE_ROOT/'AI_P136_closed_independent_review_20261027.json')
    for rel in ('.runtime/run_close_p136_once_20261027.py','.runtime/collect_p136_closed_independent_20261027_once.py'):
        bound(storage,rel,reviewed['source_sha256'][str(storage/rel)])
    rend=markers['.runtime/P136_closed_review_wait_once_end.json'];fend=markers['.runtime/P136_figure_wait_once_end.json']
    if (reviewed.get('status')!='pass' or reviewed.get('fixed_head')!=P136_HEAD
            or reviewed.get('plan_sha256')!=P136_PLAN_SHA256
            or reviewed.get('collector_complete_seen_before_trial_read')is not True
            or reviewed.get('collector_end_sha256')!=P136_MARKER_SHA256[name]
            or rend.get('reviewer_output_sha256')!=P136_PRIVATE_SHA256['AI_P136_closed_independent_review_20261027.json']
            or fend.get('independent_review_sha256')!=rend.get('reviewer_output_sha256')
            or fend.get('figure_manifest_sha256')!=P136_PRIVATE_SHA256['AI_P136_actual_figures_20261027_v01/output_manifest.json']):
        raise ValueError('P136_fixed_review_and_figure_chain_required')
    for marker,code,flag in ((rend,'review_exit_code','review_started'),(fend,'renderer_exit_code','renderer_started')):
        if (marker.get('status')!='complete' or marker.get(flag)is not True
                or type(marker.get(code))is not int or marker[code]!=0 or marker.get('source_head')!=P136_HEAD
                or marker.get('collector_end_sha256')!=P136_MARKER_SHA256[name]):
            raise ValueError('P136_postclosure_processes_not_complete')
    run=storage/'.runtime/worktrees/p136-run';prep=storage/'.runtime/worktrees/p136-prep'
    rel='configs/P136_whole_task_late_obligations_v01.json'
    for tree in (run,prep):
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=tree,text=True).strip()!=P136_HEAD:
            raise ValueError('P136_original_frozen_head_changed')
        bound(tree,rel,P136_PLAN_SHA256)
    original_plan=read(run/rel);mapping=original_plan.get('source_sha256')
    if type(mapping)is not dict or len(mapping)!=1527:raise ValueError('P136_original_1527_sources_required')
    for rel,h in mapping.items():
        for tree in (run,prep):bound(tree,rel,h)
    provenance=read(bound(ROOT,P136_PROVENANCE,P136_PROVENANCE_SHA256))
    if (provenance.get('original_execution_head')!=P136_HEAD or provenance.get('original_plan_sha256')!=P136_PLAN_SHA256
            or provenance.get('planned_conditions')!=6 or provenance.get('evaluated_conditions')!=1
            or provenance.get('incomplete_worker_conditions')!=1 or provenance.get('not_run_conditions')!=4
            or provenance.get('development_gate_met')is not False or provenance.get('whole_job_exact_total_tokens')is not None
            or type(provenance.get('source_sha256'))is not dict or len(provenance['source_sha256'])!=32):
        raise ValueError('P136_public_all_six_failure_provenance_required')
    for rel,h in provenance['source_sha256'].items():bound(ROOT,rel,h)
    copies=collector.get('copied_source_sha256')
    expected={'reports/P136_initial_checks.json','reports/P136_activation_v01.json','reports/P136_comparison.json','reports/P136_server_session.json',
              'materials/20261027_p136_results/README.md','materials/20261027_p136_results/conditions.csv','materials/20261027_p136_results/summary.json','materials/20261027_p136_results/build_manifest.json'}
    if type(copies)is not dict or set(copies)!=expected:raise ValueError('all_eight_P136_collector_artifacts_required')
    for rel,h in copies.items():
        for tree in (ROOT,run,prep):bound(tree,rel,h)
    for key,rel in [('audit_sha256','reports/P136_comparison.json'),('session_sha256','reports/P136_server_session.json'),('report_manifest_sha256','materials/20261027_p136_results/build_manifest.json')]:
        if closure.get(key)!=copies[rel]:raise ValueError('P136_closure_report_hash_changed')
    audit=read(run/'reports/P136_comparison.json');session=read(run/'reports/P136_server_session.json')
    from whole_task_late_obligations_p136 import run_order as old_order,cell_id as old_id,SEEDS as old_seeds
    expected_ids=[(old_id(rep,n,m),rep,old_seeds[rep-1],m)for rep,n,m in old_order()]
    rows=audit.get('rows');statuses=['evaluated','incomplete_worker']+['not_run']*4
    if (type(rows)is not list or [(r.get('run_id'),r.get('replication'),r.get('model_seed'),r.get('obligation_mode'))for r in rows]!=expected_ids
            or [r.get('record_status')for r in rows]!=statuses or rows[0].get('success')is not True
            or rows[0].get('known_total_tokens')!=332588 or rows[0].get('unknown_usage_calls')!=0
            or any(r.get(k)is not None for r in rows[1:] for k in ('success','known_total_tokens','unknown_usage_calls'))
            or audit.get('development_gate_met')is not False or audit.get('batch_status')!='stopped'
            or audit.get('audit_errors')!=[] or audit.get('owned_processes_absent')is not True
            or session.get('owned_processes_absent')is not True or session.get('audit_source_sha256')!=copies['reports/P136_comparison.json']):
        raise ValueError('P136_original_row_values_and_unknown_must_remain')
    state_path='records/context_pilot/P136_pipeline_v01/status.json';server_path='records/context_pilot/P136_pipeline_v01/server_final.json'
    state=read(bound(storage,state_path,audit['pipeline_status_sha256']));server=read(bound(storage,server_path,audit['server_final_sha256']))
    if (state.get('status')!='stopped' or state.get('server_stopped')is not True or server.get('status')!='stopped'
            or server.get('supervisor_pid')!=state.get('server_supervisor_pid')):
        raise ValueError('P136_original_owned_server_must_be_stopped')
    batch_path='records/context_pilot/P136_batch_v01/status.json';batch=read(bound(storage,batch_path,reviewed['source_sha256'][str(storage/batch_path)]))
    old_ids=[x[0]for x in expected_ids]
    if (batch.get('status')!='stopped' or batch.get('planned')!=old_ids or batch.get('completed')!=old_ids[:1]
            or batch.get('active')!=old_ids[1] or batch.get('not_run')!=old_ids[2:]):
        raise ValueError('P136_four_originally_unrun_slots_required')
    for pid in {started.get('wrapper_pid'),state.get('stage_pid'),server.get('pid'),server.get('supervisor_pid')}:
        if type(pid)is not int or pid<=0:raise ValueError('P136_positive_owned_pid_required')
        proc=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=10)
        if proc.returncode!=1 or proc.stdout.strip():raise ValueError('P136_owned_process_present')
    cleanup=markers['.runtime/P136_incomplete_worker_container_cleanup_20261027.json']
    absent=markers['.runtime/P136_incomplete_worker_container_absence_20261027.json']
    if (absent.get('prior_record_sha256')!=P136_MARKER_SHA256['.runtime/P136_incomplete_worker_container_cleanup_20261027.json']
            or type(absent.get('list_exit_code'))is not int or absent['list_exit_code']!=0
            or absent.get('owned_container_absent')is not True or absent.get('matching_ids')!=[]
            or absent.get('original_session_record_unchanged')is not True or absent.get('additional_removal_attempts')!=0
            or cleanup.get('removal_exit_code')!=0 or cleanup.get('does_not_repair_original_cleanup_record')is not True):
        raise ValueError('separate_P136_owned_container_absence_proof_required')
    sid='records/context_pilot/'+old_ids[1]+'/python_session/session_private.json'
    stored=read(bound(storage,sid,cleanup['session_source_sha256']))
    if stored.get('container_removed')is not False:raise ValueError('original_P136_missing_cleanup_record_changed')
    container=cleanup.get('container')
    if type(container)is not str or len(container)!=64 or any(c not in '0123456789abcdef'for c in container):
        raise ValueError('exact_P136_owned_container_id_required')
    proc=subprocess.run(docker_command(storage)+['ps','-a','--no-trunc','--filter','id='+container,'--format','{{.ID}}'],capture_output=True,text=True,timeout=15)
    if proc.returncode!=0 or proc.stdout.strip():raise ValueError('original_P136_container_not_confirmed_absent')
    return dict(storage_sha256=bindings,public_source_sha256=public_bindings,private_evidence_sha256=dict(P136_PRIVATE_SHA256),
        original_head=P136_HEAD,original_plan_sha256=P136_PLAN_SHA256,original_start_ledgers=194,original_start_bindings=2389,
        original_pipeline_exit=1,original_audit_session_report_000=True,all_six_slots_preserved=True,
        evaluated_conditions=1,incomplete_conditions=1,not_run_conditions=4,original_gate_false=True,
        original_results_replaced=False,prior_results_pooled=False,owned_processes_absent=True,
        separate_container_absence_confirmed=True,original_cleanup_record_repaired=False)


def digest_registry(value):
    import hashlib
    return hashlib.sha256(value.encode()).hexdigest()


def json_registry(value):
    import json
    return json.loads(value)



def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P137_remaining_late_obligations.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def validate_preflight(storage, root, pre, plan, original, prepared):
    """Validate saved counts/identities without recounting or generating anything."""
    validate_plan(plan)
    required = dict(phase='P137_preflight', status='complete', all_four_inputs_checked=True,
        input_count_requests=4, summary_input_count_requests=2, failed_input_count_requests=0,
        model_generations=0, environment_api_requests=0, evaluator_calls=0, reserved_scenarios_read=0)
    if (type(pre) is not dict or any(type(pre.get(k)) is not type(v) or pre[k] != v
            for k, v in required.items()) or pre.get('source_hashes') != frozen_hashes(root)
            or pre.get('research_resume') != check_resume(storage)
            or pre.get('launch_predecessor_closure') != plan.get('launch_predecessor_closure_at_preparation')
            or pre.get('launch_predecessor_closure') != launch_predecessor_closed(storage)):
        raise ValueError('P137_preparation_incomplete_or_stale')
    if (type(pre.get('rows')) is not list or len(pre['rows']) != 2
            or len(prepared) != 1 or any(prepared[i]['task_id'] != task['task_id']
                or prepared[i]['source_run'] != task['source_run']
                for i, task in enumerate(plan['known_tasks']))):
        raise ValueError('one_known_P137_CSV_preflight_identity_required')
    folder = storage / 'records/context_pilot/P137_preflight_v01'
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
                or set(row['conditions']) != set(modes_for_replication(replication))):
            raise ValueError('exact_P137_pair_identity_required')
        pair = []
        for policy in modes_for_replication(replication):
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
                raise ValueError('P137_count_input_request_or_usage_changed')
            expected_admission = admission(plan['max_total_tokens'], entry['input_tokens'],
                cfg['num_predict'], cfg['num_ctx'], 'residual')
            if digest(entry.get('admission')) != digest(expected_admission) or not expected_admission['admitted']:
                raise ValueError('P137_initial_admission_changed')
            pair.append((entry['input_tokens'], supplied, visible, read(request_path)))
        if any(entry != pair[0] for entry in pair[1:]):
            raise ValueError('all_available_same_seed_initial_inputs_must_match')
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
            raise ValueError('P137_summary_count_transport_or_usage_changed')


def validate_activation(storage, root, freeze):
    if (freeze.get('phase') != 'P137'
            or freeze.get('all_four_conditions_frozen_before_generation') is not True
            or freeze.get('source_hashes') != frozen_hashes(root)
            or freeze.get('preflight_sha256') != sha(root / PREFLIGHT)
            or freeze.get('research_resume') != check_resume(storage)):
        raise ValueError('frozen_P137_sources_or_resumption_changed')


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P137_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P137_preflight_attempts')
    plan, original, _, prepared = sources(storage, root)
    preceding_session = launch_predecessor_closed(storage)
    if preceding_session != plan.get('launch_predecessor_closure_at_preparation'):
        raise ValueError('P137_launch_predecessor_changed_since_plan_preparation')
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 480)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P137_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'launch_predecessor_closure': preceding_session,
        'input_count_requests': 0, 'summary_input_count_requests': 0, 'failed_input_count_requests': 0,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_four_inputs_checked': False}
    try:
        for replication, item in [(rep, item) for rep in (1, 2) for item in prepared]:
            row = {'replication': replication, 'model_seed': SEEDS[replication - 1],
                   'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in modes_for_replication(replication):
                if (storage / '.runtime/P137.stop').exists():
                    raise InterruptedError('explicit_P137_stop')
                remaining = 420 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P137_preflight_deadline')
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
            entries = [row['conditions'][arm] for arm in modes_for_replication(replication)]
            if any(e['model_messages_sha256'] != entries[0]['model_messages_sha256']
                   or e['base_messages_sha256'] != entries[0]['base_messages_sha256']
                   or e['visible_state'] != entries[0]['visible_state']
                   or e['input_tokens'] != entries[0]['input_tokens'] for e in entries):
                raise ValueError('all_available_same_seed_initial_inputs_must_match')
            requests = [read(folder / (f'R{replication:02d}_' + item['source_run'] + '_' + arm + '_request_private.json')) for arm in modes_for_replication(replication)]
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
        result.update(status='complete', all_four_inputs_checked=True)
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
        raise FileExistsError('preserve_P137_activation')
    if (storage / '.runtime/P137.stop').exists():
        raise InterruptedError('explicit_P137_stop_before_activation')
    plan, original, _, prepared = sources(storage, root)
    pre = read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    write_json(root / ACTIVATION, {'phase': 'P137', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_four_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def bounded_cell(storage, root, plan, replication, number, arm, rid, folder):
    command = [sys.executable, str(root / 'scripts/run_whole_task_remaining_late_obligations_p137.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm, '--replication', str(replication)]
    exit_path = folder / (rid + '_worker_exit.json')
    if exit_path.exists():
        raise FileExistsError('preserve_P137_worker_exit_record')
    record = dict(run_id=rid, status='starting', returncode=None, pid=None,
        wait_timeout_seconds=plan['max_setup_seconds']+plan['max_wall_seconds']+plan['max_cleanup_seconds'],
        timed_out=False, forced_group_kill=False, started_at=dt.datetime.now(dt.timezone.utc).isoformat())
    write_json(exit_path, record)
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        record.update(pid=child.pid, status='running'); write_json(exit_path, record)
        try:
            code = child.wait(timeout=record['wait_timeout_seconds'])
            record['returncode'] = code
            if code:
                raise RuntimeError('P137_cell_worker_failed_no_retry')
        except BaseException as error:
            record.update(error_type=type(error).__name__, timed_out=isinstance(error,subprocess.TimeoutExpired))
            raise
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    record['forced_group_kill'] = True
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
            record.update(status='exited', returncode=child.poll(),
                ended_at=dt.datetime.now(dt.timezone.utc).isoformat())
            write_json(exit_path, record)
    return read(storage / 'records/context_pilot' / rid / 'summary.json')


def run_worker(storage, root, replication, number, arm):
    """Recheck frozen preparation and the owned live runtime before any cell."""
    rid = cell_id(replication, number, arm)
    if (storage / '.runtime/P137.stop').exists():
        raise InterruptedError('explicit_P137_stop')
    plan, original, tools, prepared = sources(storage, root)
    frozen, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    validate_activation(storage, root, frozen)
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, _ = live_identity(storage, original, max_cell)
    if identity != pre.get('model_identity'):
        raise ValueError('prepared_model_identity_changed')
    from run_whole_task_remaining_late_obligations_cell_p137 import run_cell
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
    state = {'phase': 'P137', 'status': 'running', 'rows': [], 'completed': [], 'active': None, 'worker_exit_records': {},
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
            if (storage / '.runtime/P137.stop').exists():
                raise InterruptedError('explicit_P137_stop')
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
                raise ValueError('P137_initialization_API_or_runtime_failure')
            row['idle_recovery_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            if (storage / '.runtime/P137.stop').exists():
                raise InterruptedError('explicit_P137_stop')
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
                raise ValueError('independent_P137_evaluation_failed')
            row['success'] = read(storage / 'records/context_pilot' / rid / 'evaluation.json')['official_success']
            state['completed'].append(rid); save()
            print({k: row[k] for k in ('run_id', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')}, flush=True)
        state.update(status='complete', active=None,
                     known_usage_complete=all(r['unknown_usage_calls'] == 0 for r in state['rows']))
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        state['worker_exit_records'] = {rid:read(folder/(rid+'_worker_exit.json'))
            for rid in state['planned'] if (folder/(rid+'_worker_exit.json')).exists()}
        state['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        state['not_run'] = [rid for rid in state['planned']
            if rid not in {r['run_id'] for r in state['rows']} and rid != state['active']]
        state['unevaluated'] = [r['run_id'] for r in state['rows'] if r['run_id'] not in state['completed']]
        save()
    return 0 if state['status'] == 'complete' else 1


def interrupt(*_):
    raise InterruptedError('bounded_P137_execution_interrupted')


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

"""P97 three-notice accounting and source-history audit; no generation or API dispatch."""
import argparse
from collections import Counter
from pathlib import Path
import subprocess

from api_error_comparison import disposition
from recovery_notice_comparison import initial_conversation
from budget_observation import notification
from recovery_notices import RecoveryMonitor
from budget_observation_worker import attempt_usage
from recovery_notice_comparison import ERROR_POLICY, cell_id, config_for, run_order, summarize
from types import SimpleNamespace
from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission
from budget_signal import digest
from inference_cache_control import cache_measurement
from fixed_budget_local_llama import parse_response, payload_for
from public_display import CODE_TOOLS
from run_recovery_notice_comparison import ACTIVATION, PREFLIGHT, frozen_hashes, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit_cell(folder, root, plan, original, item, arm, pre, evaluated):
    summary, usage, events, spans = [read(folder / (name + '.json'))
                                    for name in ('summary', 'usage', 'events', 'spans')]
    config = config_for(original, plan, item['task_id'], arm)
    if (read(folder / 'plan.json') != config or read(folder / 'comparison_plan.json') != plan
            or read(folder / 'public_task.json') != item['public_task']
            or summary['arm'] != ERROR_POLICY or summary['time_visibility'] != 'not_exposed'
            or summary['notice_policy'] != arm
            or summary['reasoning_budget_tokens'] != config['model']['reasoning_budget_tokens'] or summary['task_id'] != item['task_id']
            or summary['run_id'] != folder.name or summary['prefix_api_requests'] != 0):
        raise ValueError('executed_condition_differs')
    before, total = budget_before_calls(usage, events, 0, config)
    if (summary['model_calls'] != len(usage)
            or summary['known_total_tokens'] != total['known_total_tokens']
            or summary['unknown_usage_calls'] != total['unknown_usage_calls']
            or summary['api_requests'] != total['suffix_api_requests']
            or len(usage) > plan['max_calls'] or total['known_total_tokens'] > plan['max_total_tokens']
            or summary['api_requests'] > config['max_api_requests']):
        raise ValueError('accounting_or_budget_mismatch')
    ids = [e['span_id'] for e in events]
    if (len(ids) != len(set(ids)) or set(ids) != set(spans)
            or sum(e['effects_unknown'] for e in events if e['api_request_sent']) != summary['unknown_effect_requests']):
        raise ValueError('event_archive_mismatch')
    receipts = [e['api_execution'] for e in events if 'api_execution' in e]
    if receipts != summary['api_execution_receipts']:
        raise ValueError('invocation_receipt_mismatch')
    for event in events:
        if event['api_request_sent']:
            receipt = event.get('api_execution')
            if not receipt or not receipt['bridge_request_sent'] or receipt['automatic_retries']:
                raise ValueError('sent_API_requires_one_typed_receipt')
            if receipt['status'] == 'raised':
                observation = spans[event['span_id']]['observation']
                if event['new_tools'] or (ERROR_POLICY == 'error_exception') != ('api_error' in observation):
                    raise ValueError('failure_presentation_or_schema_policy_differs')
        elif event['stage'] == 'model_tool' and 'api_execution' in event:
            raise ValueError('outer_tool_cannot_dispatch_typed_API')
    if evaluated and disposition(summary) == 'stop_batch':
        raise ValueError('evaluation_after_invalid_cell')
    signals = read(folder / 'budget_observations.json') if (folder / 'budget_observations.json').exists() else []
    terminal = read(folder / 'terminal_usage.json')
    if attempt_usage(SimpleNamespace(calls=terminal, snapshots=signals)) != usage:
        raise ValueError('dispatch_and_terminal_accounting_disagree')
    views = read(folder / 'protocol_reference_views.json') if (folder / 'protocol_reference_views.json').exists() else []
    if len(views) != len(signals):
        raise ValueError('reference_and_budget_view_counts_differ')
    admissions = read(folder / 'admissions.json') if (folder / 'admissions.json').exists() else []
    attempts = [s for s in signals if s['model_attempted']]
    admitted = [a for a in admissions if a['model_attempted']]
    if ([s['next_call_id'] for s in attempts] != [c['id'] for c in usage]
            or [a['next_call_id'] for a in admitted] != [c['id'] for c in usage]
            or len(signals) - len(attempts) not in (0, 1)
            or len(admissions) - len(admitted) not in (0, 1)):
        raise ValueError('model_notification_admission_correspondence_differs')
    monitor = RecoveryMonitor(arm)
    recorded_monitor = read(folder / 'recovery_observations.json')
    completed_boundaries = {c['call_id'] for c in recorded_monitor['model_boundaries']}
    conversation = initial_conversation(original, item['public_task'])
    initial, _ = conversation.for_model(config['observation_page_characters'])
    if digest(initial) != pre['base_messages_sha256']:
        raise ValueError('initial_input_differs_from_preflight')
    last_wall = config['max_wall_seconds']
    checks = []
    for index, (call, signal, entry, budget) in enumerate(zip(usage, attempts, admitted, before, strict=True)):
        base, _ = conversation.for_model(config['observation_page_characters'])
        state = signal['measured_state']; remaining = state['remaining']
        expected_used = {'api_calls': config['max_api_requests'] - budget['remaining_api_before'],
                         'model_calls': index, 'logical_input_plus_output_tokens': budget['known_tokens_before']}
        if (state['used'] != expected_used or remaining['api_calls'] != budget['remaining_api_before']
                or remaining['model_calls'] != budget['remaining_calls_before']
                or remaining['logical_input_plus_output_tokens'] != budget['remaining_tokens_before']
                or not 0 <= remaining['wall_seconds_at_snapshot'] <= last_wall
                or state['max_output_tokens_per_call'] != config['max_output_tokens']
                or state['context_limit_per_call'] != config['model']['num_ctx']):
            raise ValueError('whole_task_budget_notice_differs')
        last_wall = remaining['wall_seconds_at_snapshot']
        raw_base = conversation.messages()
        effective = 'not_exposed'
        supplied, visible = notification(base, state, effective)
        if signal['before_recovery_messages_sha256'] != digest(supplied):
            raise ValueError('before_recovery_input_mismatch')
        supplied, offer = monitor.supply(supplied, call['id'])
        if offer is not None:
            offer['model_attempted'] = True
        if (signal['recovery_notice_policy'] != arm
                or signal['recovery_notice_supplied'] != (offer is not None)):
            raise ValueError('recovery_notice_dispatch_mismatch')
        if (signal['effective_time_visibility'] != effective
                or signal['original_wall_limit_seconds'] != config['max_wall_seconds']):
            raise ValueError('effective_time_policy_or_original_deadline_differs')
        if signal['visible_state'] != visible or signal['time_visibility'] != 'not_exposed':
            raise ValueError('visible_budget_policy_differs')
        view = views[index]
        if (view['next_call_id'] != call['id'] or view['original_messages_sha256'] != digest(raw_base)
                or view['canonical_messages_sha256'] != digest(base)
                or view['policy'] != 'source_protocol_fields_before_rendering'):
            raise ValueError('protocol_reference_normalization_differs')
        if (signal['base_messages_sha256'] != digest(base)
                or signal['model_messages_sha256'] != digest(supplied)
                or signal['cache_prompt'] != (index > 0)):
            raise ValueError('rendered_history_or_cache_policy_differs')
        choice = validate_admission(entry, budget['remaining_tokens_before'], config)
        if not choice['admitted'] or not entry.get('model_request_started'):
            raise ValueError('generation_after_rejection')
        cfg = {**config['model'], 'temperature': config['agent_temperature'], 'seed': config['seed'] + index,
               'num_predict': choice['selected_output_cap'], 'cache_prompt': index > 0}
        request_path = folder / call['id'] / 'request.json'
        response_path = folder / call['id'] / 'response.json'
        request = read(request_path) if request_path.exists() else None
        response = read(response_path) if response_path.exists() else None
        missing_terminal = call.get('error_kind') == 'dispatched_without_terminal_usage'
        if request is not None and request != payload_for(cfg, supplied, CODE_TOOLS):
            raise ValueError('actual_request_differs')
        if not missing_terminal and (request is None or response is None
                or call['predicted_input_tokens'] != choice['input_tokens']
                or call['output_cap'] != choice['selected_output_cap']):
            raise ValueError('terminal_request_or_reservation_differs')
        if missing_terminal and (response is not None or signal['terminal_usage_recorded']
                or call.get('server_receipt_confirmed') is not False):
            raise ValueError('missing_terminal_cannot_fabricate_server_receipt')
        if call['status'] == 'ok':
            parsed = parse_response(read(folder / call['id'] / 'raw_response.json'))
            if any(parsed[k] != response[k] for k in parsed):
                raise ValueError('raw_terminal_normalization_differs')
            for key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
                if response.get(key) != call.get(key):
                    raise ValueError('terminal_usage_differs')
            if (response['input_tokens'] != choice['input_tokens']
                    or response['output_tokens'] > choice['selected_output_cap']):
                raise ValueError('terminal_usage_exceeds_reservation')
            if index == 0:
                cache = cache_measurement('cold_1', response, response['input_tokens'])
                if not cache['state_confirmed'] or signal.get('first_input_measurement') != cache:
                    raise ValueError('first_request_not_cold')
            current = [e for e in events if e['call'] == call['id']]
            if call['id'] in completed_boundaries or recorded_monitor['active_incomplete_boundary'] == call['id']:
                monitor.begin(call['id'])
                for event in current:
                    monitor.observe({**spans[event['span_id']],
                        'api_request_sent':event['api_request_sent'],
                        'effects_unknown':event['effects_unknown'],
                        **({'api_execution':event['api_execution']} if 'api_execution' in event else {})})
                if call['id'] in completed_boundaries:
                    monitor.finish()
            elif current:
                raise ValueError('executed_events_missing_from_recovery_monitor')
            outer = [spans[e['span_id']] for e in events if e['call'] == call['id'] and e['stage'] == 'model_tool']
            if outer:
                conversation.append(response['message'], outer)
            elif not (index == len(usage) - 1 and summary['stop_reason'] in (
                    'runtime_error', 'wall_limit', 'api_request_limit', 'user_stop', 'cleanup_error')
                    and not any(e['call'] == call['id'] for e in events)):
                raise ValueError('successful_response_without_execution_record')
        else:
            if index != len(usage) - 1 or any(e['call'] == call['id'] for e in events):
                raise ValueError('unknown_response_executed_or_retried')
            if any(call[k] is not None or (response is not None and response[k] is not None)
                   for k in ('input_tokens', 'output_tokens')):
                raise ValueError('unknown_usage_imputed')
        checks.append({'call_id': call['id'], 'status': call['status'],
                       'request_sha256': sha(request_path) if request_path.exists() else None,
                       'response_sha256': sha(response_path) if response_path.exists() else None,
                       'terminal_usage_recorded': not missing_terminal})
    # A final rejected/count-only input can consume the one-shot offer without
    # dispatching a model request. Do not label it a delivered intervention.
    if len(signals) > len(attempts):
        signal = signals[-1]
        if signal['model_attempted']:
            raise ValueError('nonattempted_notice_must_be_final')
        base, _ = conversation.for_model(config['observation_page_characters'])
        supplied, _ = notification(base, signal['measured_state'], 'not_exposed')
        if signal['before_recovery_messages_sha256'] != digest(supplied):
            raise ValueError('before_recovery_rejected_input_mismatch')
        supplied, offer = monitor.supply(supplied, signal['next_call_id'])
        if (signal['model_messages_sha256'] != digest(supplied)
                or signal['recovery_notice_supplied'] != (offer is not None)):
            raise ValueError('rejected_input_notice_mismatch')
    replay = monitor.report()
    if any(replay[k] != recorded_monitor[k] for k in replay if k != 'controller_wall_seconds'):
        raise ValueError('recovery_observation_replay_differs')
    if (type(recorded_monitor['controller_wall_seconds']) not in (int, float)
            or not 0 <= recorded_monitor['controller_wall_seconds'] <= summary['wall_seconds']
            or summary['recovery_monitor'] != {k:v for k,v in recorded_monitor.items()
                                              if k not in ('requests','model_boundaries')}):
        raise ValueError('controller_accounting_differs')
    success = None
    if evaluated:
        evaluation = read(folder / 'evaluation.json')
        if (evaluation['execution_summary_sha256'] != sha(folder / 'summary.json')
                or evaluation['evaluation_returned_to_model'] or type(evaluation['official_success']) is not bool
                or evaluation['evaluation_script_sha256'] != sha(root / 'scripts/evaluate_context_trial.py')):
            raise ValueError('independent_evaluation_link_differs')
        dbs = folder.parents[2] / '.runtime/appworld/r18_probe_01/experiments/outputs' / folder.name / 'tasks' / item['task_id'] / 'dbs'
        hashes = {str(p.relative_to(dbs)): sha(p) for p in sorted(dbs.rglob('*')) if p.is_file()}
        if not hashes or hashes != evaluation['frozen_database_hashes']:
            raise ValueError('evaluated_database_file_hashes_changed')
        success = evaluation['official_success']
    known = [c for c in usage if c['status'] == 'ok']
    return {'run_id': folder.name, 'task_id': item['task_id'], 'time_visibility': 'not_exposed', 'notice_policy': arm,
        'record_status': 'evaluated' if evaluated else 'unevaluated', 'success': success,
        **{k: summary[k] for k in ('stop_reason', 'model_calls', 'known_total_tokens', 'unknown_usage_calls',
                                  'api_requests', 'wall_seconds', 'full_wall_seconds', 'cleanup_wall_seconds')},
        'input_tokens': sum(c['input_tokens'] for c in known),
        'output_tokens': sum(c['output_tokens'] for c in known),
        'cached_input_tokens': sum(c['cached_input_tokens'] for c in known)
            if all(type(c.get('cached_input_tokens')) is int for c in known) else None,
        'invocation_exceptions': sum(r['status'] == 'raised' for r in receipts),
        'invocation_status_counts': dict(Counter(r['status'] for r in receipts)),
        'setup_wall_seconds': summary['setup']['wall_seconds'], 'request_checks': checks,
        'recovery_monitor': summary['recovery_monitor'],
        'dispatched_notice_inputs': [{'call_id':s['next_call_id'],
            'before_recovery_messages_sha256':s['before_recovery_messages_sha256']}
            for s in signals if s['model_attempted'] and s['recovery_notice_supplied']],
        'recovery_observations_sha256': sha(folder / 'recovery_observations.json'),
        'summary_sha256': sha(folder / 'summary.json'), 'usage_sha256': sha(folder / 'usage.json'),
        'evaluation_sha256': sha(folder / 'evaluation.json') if evaluated else None}


def run(storage, root):
    target = root / 'reports/P97_comparison.json'
    if target.exists():
        raise FileExistsError('preserve_all_P97_audit_attempts')
    plan, original, _, prepared = sources(storage, root)
    pipeline_dir = storage / 'records/context_pilot/P97_pipeline_v01'
    pipeline, server = read(pipeline_dir / 'status.json'), read(pipeline_dir / 'server_final.json')
    if (pipeline['status'] not in ('complete', 'stopped') or not pipeline.get('server_stopped')
            or server['status'] != 'stopped'
            or server['supervisor_pid'] != pipeline['server_supervisor_pid']):
        raise ValueError('owned_P97_pipeline_must_be_closed_before_audit')
    for key in ('pid', 'supervisor_pid'):
        process = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='],
                                 capture_output=True, text=True, timeout=10)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('owned_P97_process_still_exists')
    activation, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if (activation['source_hashes'] != frozen_hashes(root)
            or activation['preflight_sha256'] != sha(root / PREFLIGHT)):
        raise ValueError('P97_frozen_sources_changed')
    batch = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    if batch['status'] not in ('complete', 'stopped'):
        raise ValueError('wait_until_budget_batch_closes')
    rows, errors = [], []
    for number, policy in run_order():
        item = prepared[number - 1]; rid = cell_id(number, policy)
        folder = storage / 'records/context_pilot' / rid
        row = {'run_id': rid, 'task_id': item['task_id'], 'time_visibility': 'not_exposed', 'notice_policy': policy,
               'record_status': 'not_run', 'success': None, 'known_total_tokens': None,
               'unknown_usage_calls': None}
        if (folder / 'summary.json').exists():
            try:
                row = audit_cell(folder, root, plan, original, item, policy,
                    pre['rows'][number - 1]['conditions'][policy], rid in batch['completed'])
                if read(folder / 'summary.json')['phase'] != 'P97':
                    raise ValueError('wrong_budget_worker')
            except Exception as error:
                row.update(record_status='audit_error', success=None,
                           known_total_tokens=None, unknown_usage_calls=None)
                errors.append({'run_id': rid, 'type': type(error).__name__, 'reason': str(error)})
        elif folder.exists():
            row['record_status'] = 'incomplete_worker'
        rows.append(row)
    result = {'phase': 'P97', 'batch_status': batch['status'], 'rows': rows, 'audit_errors': errors,
        **summarize(rows, errors),
        'pipeline_status_sha256': sha(pipeline_dir / 'status.json'),
        'server_final_sha256': sha(pipeline_dir / 'server_final.json'),
        'owned_processes_absent': True,
        'plan_sha256': sha(root / 'configs/P97_recovery_notice_comparison_v01.json'),
        'activation_sha256': sha(root / ACTIVATION), 'auditor_sha256': sha(Path(__file__)),
        'additional_model_calls': 0, 'additional_api_calls': 0, 'additional_evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'private_reasoning_inspected_semantically': False,
        'database_contents_inspected': False}
    write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'audit_errors', 'factual_notice_benefit_gate_met')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root)

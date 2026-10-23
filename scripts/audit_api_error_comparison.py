"""P78 full-cohort accounting and request audit; no generation or API dispatch."""
import argparse
from collections import Counter
from pathlib import Path

from api_error_comparison import (ARMS, add_notification, cell_id, config_for, disposition,
                                  initial_conversation, run_order)
from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission
from budget_signal import digest
from inference_cache_control import cache_measurement
from local_llama import parse_response, payload_for
from public_display import CODE_TOOLS
from run_api_error_comparison import ACTIVATION, PREFLIGHT, frozen_hashes, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def development_gate(rows, audit_errors):
    if len({(r['task_id'], r['arm']) for r in rows}) != len(rows):
        raise ValueError('duplicate_task_condition')
    pairs = []
    for task in dict.fromkeys(r['task_id'] for r in rows):
        cells = {r['arm']: r for r in rows if r['task_id'] == task}
        if set(cells) != set(ARMS):
            raise ValueError('missing_planned_condition')
        a, b = [cells[arm] for arm in ARMS]
        evaluated = all(r['record_status'] == 'evaluated' for r in (a, b))
        known = evaluated and all(r['unknown_usage_calls'] == 0 for r in (a, b))
        if evaluated and any(type(r['success']) is not bool for r in (a, b)):
            raise ValueError('evaluated_result_must_be_boolean')
        pairs.append({'task_id': task, 'both_evaluated': evaluated, 'both_usage_known': known,
            'value_success': a['success'], 'exception_success': b['success'],
            'success_lost': a['success'] and not b['success'] if evaluated else None,
            'success_gained': b['success'] and not a['success'] if evaluated else None,
            'both_successful': a['success'] and b['success'] if evaluated else None,
            'exception_minus_value_tokens': b['known_total_tokens'] - a['known_total_tokens'] if known else None,
            'invocation_exceptions_observed': sum(r.get('invocation_exceptions', 0) for r in (a, b))})
    complete = len(rows) == 8 and len(pairs) == 4 and all(p['both_usage_known'] for p in pairs)
    losses = sum(p['success_lost'] for p in pairs) if all(p['both_evaluated'] for p in pairs) else None
    gains = sum(p['success_gained'] for p in pairs) if all(p['both_evaluated'] for p in pairs) else None
    successful = sum(p['both_successful'] for p in pairs) if all(p['both_evaluated'] for p in pairs) else None
    delta = sum(p['exception_minus_value_tokens'] for p in pairs) if complete else None
    errors = sum(p['invocation_exceptions_observed'] for p in pairs)
    gate = bool(complete and not audit_errors and errors > 0 and losses == 0 and successful > 0 and delta < 0)
    return {'all_eight_complete_with_known_usage': complete, 'paired_results': pairs,
        'paired_success_losses': losses, 'paired_success_gains': gains, 'paired_successful_tasks': successful,
        'exception_minus_value_whole_task_tokens': delta, 'invocation_exceptions_observed': errors,
        'development_gate_met': gate, 'general_quality_preservation_claim': False, 'novel_method_claim': False}


def audit_cell(folder, root, plan, original, item, arm, pre, evaluated):
    summary, usage, events, spans = [read(folder / (name + '.json'))
                                    for name in ('summary', 'usage', 'events', 'spans')]
    config = config_for(original, plan, item['task_id'])
    if (read(folder / 'plan.json') != config or read(folder / 'comparison_plan.json') != plan
            or read(folder / 'public_task.json') != item['public_task']
            or summary['arm'] != arm or summary['task_id'] != item['task_id']
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
            or sum(e['effects_unknown'] for e in events) != summary['unknown_effect_requests']):
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
                if event['new_tools'] or (arm == 'error_exception') != ('api_error' in observation):
                    raise ValueError('failure_presentation_or_schema_policy_differs')
        elif event['stage'] == 'model_tool' and 'api_execution' in event:
            raise ValueError('outer_tool_cannot_dispatch_typed_API')
    if evaluated and disposition(summary) == 'stop_batch':
        raise ValueError('evaluation_after_invalid_cell')
    signals = read(folder / 'budget_signals.json') if (folder / 'budget_signals.json').exists() else []
    admissions = read(folder / 'admissions.json') if (folder / 'admissions.json').exists() else []
    attempts = [s for s in signals if s['model_attempted']]
    admitted = [a for a in admissions if a['model_attempted']]
    if ([s['next_call_id'] for s in attempts] != [c['id'] for c in usage]
            or [a['next_call_id'] for a in admitted] != [c['id'] for c in usage]
            or len(signals) - len(attempts) not in (0, 1)
            or len(admissions) - len(admitted) not in (0, 1)):
        raise ValueError('model_notification_admission_correspondence_differs')
    conversation = initial_conversation(original, item['public_task'])
    initial, _ = conversation.for_model(config['observation_page_characters'])
    if digest(initial) != pre['base_messages_sha256']:
        raise ValueError('initial_input_differs_from_preflight')
    last_wall = config['max_wall_seconds']
    checks = []
    for index, (call, signal, entry, budget) in enumerate(zip(usage, attempts, admitted, before, strict=True)):
        base, _ = conversation.for_model(config['observation_page_characters'])
        state = signal['state']; remaining = state['remaining']
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
        supplied = add_notification(base, state)
        if (signal['base_messages_sha256'] != digest(base)
                or signal['model_messages_sha256'] != digest(supplied)
                or signal['cache_prompt'] != (index > 0)):
            raise ValueError('rendered_history_or_cache_policy_differs')
        choice = validate_admission(entry, budget['remaining_tokens_before'], config)
        if not choice['admitted'] or not entry.get('model_request_started'):
            raise ValueError('generation_after_rejection')
        cfg = {**config['model'], 'temperature': config['agent_temperature'], 'seed': config['seed'] + index,
               'num_predict': choice['selected_output_cap'], 'cache_prompt': index > 0}
        request, response = [read(folder / call['id'] / name) for name in ('request.json', 'response.json')]
        if (request != payload_for(cfg, supplied, CODE_TOOLS)
                or call['predicted_input_tokens'] != choice['input_tokens']
                or call['output_cap'] != choice['selected_output_cap']):
            raise ValueError('actual_request_or_reservation_differs')
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
            outer = [spans[e['span_id']] for e in events if e['call'] == call['id'] and e['stage'] == 'model_tool']
            if outer:
                conversation.append(response['message'], outer)
            elif not (index == len(usage) - 1 and summary['stop_reason'] == 'runtime_error'):
                raise ValueError('successful_response_without_execution_record')
        else:
            if index != len(usage) - 1 or any(e['call'] == call['id'] for e in events):
                raise ValueError('unknown_response_executed_or_retried')
            if any(response[k] is not None or call[k] is not None for k in ('input_tokens', 'output_tokens')):
                raise ValueError('unknown_usage_imputed')
        checks.append({'call_id': call['id'], 'status': call['status'],
                       'request_sha256': sha(folder / call['id'] / 'request.json'),
                       'response_sha256': sha(folder / call['id'] / 'response.json')})
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
    return {'run_id': folder.name, 'task_id': item['task_id'], 'arm': arm,
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
        'summary_sha256': sha(folder / 'summary.json'), 'usage_sha256': sha(folder / 'usage.json'),
        'evaluation_sha256': sha(folder / 'evaluation.json') if evaluated else None}


def run(storage, root):
    target = root / 'reports/P78_comparison.json'
    if target.exists():
        raise FileExistsError('preserve_P78_analysis_attempt')
    plan, original, _, prepared = sources(storage, root)
    activation, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if activation['source_hashes'] != frozen_hashes(root) or activation['preflight_sha256'] != sha(root / PREFLIGHT):
        raise ValueError('P78_frozen_sources_changed')
    batch = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    if batch['status'] not in ('complete', 'stopped'):
        raise ValueError('wait_until_batch_is_closed')
    rows, errors = [], []
    for number, arm in run_order():
        item = prepared[number - 1]; rid = cell_id(number, arm)
        folder = storage / 'records/context_pilot' / rid
        fallback = {'run_id': rid, 'task_id': item['task_id'], 'arm': arm, 'record_status': 'not_run',
                    'success': None, 'known_total_tokens': None, 'unknown_usage_calls': None}
        if (folder / 'summary.json').exists():
            try:
                fallback = audit_cell(folder, root, plan, original, item, arm,
                    pre['rows'][number - 1]['conditions'][arm], rid in batch['completed'])
            except Exception as error:
                fallback['record_status'] = 'audit_error'
                errors.append({'run_id': rid, 'type': type(error).__name__, 'reason': str(error)})
        elif folder.exists():
            fallback['record_status'] = 'incomplete_worker'
        rows.append(fallback)
    report = {'phase': 'P78', 'batch_status': batch['status'], 'rows': rows, 'audit_errors': errors,
              **development_gate(rows, errors), 'additional_model_calls': 0, 'additional_api_calls': 0,
              'additional_evaluator_calls': 0, 'private_reasoning_inspected_semantically': False,
              'database_contents_inspected': False, 'reserved_scenarios_read': 0,
              'plan_sha256': sha(root / 'configs/P78_api_error_v01.json'),
              'activation_sha256': sha(root / ACTIVATION), 'auditor_sha256': sha(Path(__file__))}
    write_json(target, report)
    print({k: report[k] for k in ('batch_status', 'audit_errors', 'development_gate_met')})
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args()
    run(a.storage_root, a.repo_root)

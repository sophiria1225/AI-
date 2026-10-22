"""Audit every planned P55 cell, including an incomplete stopped batch.

Rebuild each sent history from the fixed boundary and recorded public tool
receipts; check measured budgets and raw terminal counters without inference.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path

from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission, validate_signal
from budget_signal import digest
from code_agent_interface import CODE_TOOLS
from inventory_display import ARMS, build_condition, disposition
from audit_contract_feedback import audit_feedback_cell
from inference_cache_control import cache_measurement
from later_handoff_sources import prepare_later_sources
from local_llama import parse_response, payload_for
from profile_handoff_costs import summarize_calls
from run_context_comparison import write_json
from run_inventory_comparison import ACTIVATION, PLAN, PREFLIGHT, cell_id, run_order
from run_handoff_factors import ROOT, read, sha


def development_gate(rows):
    if len({(r['task_id'], r['arm']) for r in rows}) != len(rows):
        raise ValueError('duplicate task-condition cell')
    if any(r['record_status'] == 'evaluated' and type(r['success']) is not bool for r in rows):
        raise ValueError('evaluated cell requires a Boolean result')
    complete = (len(rows) == 12 and len({r['task_id'] for r in rows}) == 4
        and all(r['record_status'] == 'evaluated' and r['logical_task_unknown_usage_calls'] == 0 for r in rows))
    contrasts = {control: [] for control in (ARMS[0], ARMS[2])}
    for task in dict.fromkeys(r['task_id'] for r in rows):
        cells = {r['arm']: r for r in rows if r['task_id'] == task}
        if set(cells) != set(ARMS):
            raise ValueError('missing planned condition')
        candidate = cells[ARMS[1]]
        for control in contrasts:
            baseline = cells[control]
            evaluated = candidate['record_status'] == baseline['record_status'] == 'evaluated'
            known = candidate['logical_task_unknown_usage_calls'] == baseline['logical_task_unknown_usage_calls'] == 0
            contrasts[control].append({'task_id': task, 'both_evaluated': evaluated,
                'control_success': baseline['success'], 'candidate_success': candidate['success'],
                'success_lost': bool(baseline['success'] and not candidate['success']) if evaluated else None,
                'success_gained': bool(candidate['success'] and not baseline['success']) if evaluated else None,
                'inventory_input_changed': candidate.get('inventory_input_changed', False),
                'candidate_minus_control_work_tokens': candidate['logical_task_known_total_tokens'] - baseline['logical_task_known_total_tokens']
                    if evaluated and known else None,
                'candidate_minus_control_continuation_tokens': candidate['known_total_tokens'] - baseline['known_total_tokens']
                    if evaluated and known else None})
    decisions = {control: {'paired_results': pairs,
        'paired_success_losses': sum(p['success_lost'] for p in pairs) if complete else None,
        'paired_success_gains': sum(p['success_gained'] for p in pairs) if complete else None,
        'candidate_minus_control_work_tokens': sum(p['candidate_minus_control_work_tokens'] for p in pairs) if complete else None}
        for control, pairs in contrasts.items()}
    quality = complete and all(d['paired_success_losses'] == 0 for d in decisions.values())
    costs = (complete and decisions[ARMS[0]]['candidate_minus_control_work_tokens'] < 0
        and decisions[ARMS[2]]['candidate_minus_control_work_tokens'] <= 0)
    informative_gains = sum(p['success_gained'] is True and p['inventory_input_changed']
                           for p in contrasts[ARMS[2]])
    return {'all_twelve_complete_with_known_usage': complete, 'contrasts': decisions,
        'development_gate_met': quality and costs,
        'inventory_advantage_supported': quality and costs and informative_gains > 0,
        'inventory_success_gains_on_changed_inputs': informative_gains,
        'general_quality_preservation_claim': False, 'novel_method_claim': False}


def audit_cell(folder, item, arm, original, plan, preflight, evaluated):
    names = ('summary.json', 'usage.json', 'events.json', 'spans.json', 'setup.json',
             'source_identity.json', 'plan.json', 'factor_plan.json',
             'prefix_events.json', 'prefix_spans.json', 'prefix_usage.json', 'public_task.json')
    values = {name: read(folder / name) for name in names}
    summary, usage, events, spans, setup, limits = (values[name] for name in
        ('summary.json', 'usage.json', 'events.json', 'spans.json', 'setup.json', 'plan.json'))
    expected_config = copy.deepcopy(original)
    expected_config.update({k: plan[k] for k in ('max_calls', 'max_total_tokens', 'max_wall_seconds')})
    expected_config.update(phase='P55', seed=original['seed'] + 8,
                           max_api_requests=original['api_budget_by_task'][item['task_id']])
    if limits != expected_config or values['factor_plan.json'] != plan:
        raise ValueError('executed model configuration or comparison plan differs')
    prefix = item['prefix']
    if (values['source_identity.json'] != {k: item[k] for k in
            ('task_id', 'source_run', 'source_sha256', 'boundary_manifest_sha256')}
            or summary['run_id'] != folder.name or summary['task_id'] != item['task_id'] or summary['arm'] != arm):
        raise ValueError('wrong cell or source identity')
    for key in ('events', 'spans', 'usage'):
        if values[f'prefix_{key}.json'] != prefix[key]:
            raise ValueError('saved original prefix changed')
    if values['public_task.json'] != prefix['public_task']:
        raise ValueError('original task changed')
    prefix_api = prefix['manifest']['state']['api_requests']
    before, total = budget_before_calls(usage, events, prefix_api, limits)
    if (len(usage) != summary['model_calls'] or total['known_total_tokens'] != summary['known_total_tokens']
            or total['unknown_usage_calls'] != summary['unknown_usage_calls']
            or total['suffix_api_requests'] != summary['api_requests'] or prefix_api != summary['prefix_api_requests']
            or prefix_api + total['suffix_api_requests'] != summary['total_task_api_requests']
            or len(usage) > plan['max_calls'] or total['known_total_tokens'] > plan['max_total_tokens']
            or summary['total_task_api_requests'] > limits['max_api_requests']):
        raise ValueError('summary or declared budget disagrees with actual records')
    ids = [e['span_id'] for e in events]
    if (len(ids) != len(set(ids)) or set(ids) != set(spans) - set(prefix['spans'])
            or any(spans[k] != v for k, v in prefix['spans'].items())
            or sum(e['effects_unknown'] for e in events) != summary['unknown_effect_requests']):
        raise ValueError('archive or event identities changed')
    if evaluated and (disposition(summary) == 'stop_batch' or not summary['python_session']['container_removed']):
        raise ValueError('evaluation followed an invalid cell')
    if setup['status'] == 'matched_observable_prefix':
        replay = setup['environment_replay']; python = setup['python_replay']
        if (replay['api_requests'] != prefix_api or replay['observation_matches'] != prefix_api
                or not replay['db_files_match'] or replay['unknown_effect_requests']
                or python['programs'] != len(item['programs']) or python['api_requests_sent']
                or len(python['checks']) != len(item['programs'])
                or not all(c['observable_prefix_matches'] and not c['api_requests_sent'] for c in python['checks'])):
            raise ValueError('restoration correspondence differs')
        if any(c['program'] != p['name'] or c['source_sha256'] != p['source_sha256']
               for c, p in zip(python['checks'], item['programs'], strict=True)):
            raise ValueError('restored Python program identities differ')
    success = None
    if evaluated:
        evaluation = read(folder / 'evaluation.json')
        if (evaluation['execution_summary_sha256'] != sha(folder / 'summary.json')
                or evaluation['evaluation_returned_to_model'] or type(evaluation['official_success']) is not bool):
            raise ValueError('independent evaluation linkage differs')
        storage = folder.parents[2]
        dbs = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / folder.name / 'tasks' / item['task_id'] / 'dbs'
        current = {str(p.relative_to(dbs)): sha(p) for p in sorted(dbs.rglob('*')) if p.is_file()}
        if not current or current != evaluation['frozen_database_hashes']:
            raise ValueError('evaluated final database files changed')
        evaluator = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/evaluator.py'
        if (evaluation['evaluation_script_sha256'] != sha(ROOT / 'scripts/evaluate_context_trial.py')
                or evaluation['official_evaluator_sha256'] != sha(evaluator)):
            raise ValueError('independent evaluator implementation changed')
        success = evaluation['official_success']
    elif (folder / 'evaluation.json').exists():
        raise ValueError('unrecorded evaluation requires investigation')

    conversation, _ = build_condition(item, arm)
    base, _ = conversation.for_model(limits['observation_page_characters'])
    if digest(base) != preflight['base_messages_sha256']:
        raise ValueError('initial display differs from fixed preflight')
    signals = read(folder / 'budget_signals.json') if (folder / 'budget_signals.json').exists() else []
    entries = read(folder / 'admissions.json') if (folder / 'admissions.json').exists() else []
    attempted = [s for s in signals if s['model_attempted']]
    admitted_requests = [e for e in entries if e['model_attempted']]
    call_ids = [c['id'] for c in usage]
    if ([s['next_call_id'] for s in attempted] != call_ids
            or [e['next_call_id'] for e in admitted_requests] != call_ids
            or len(signals) - len(attempted) not in (0, 1)
            or attempted != signals[:len(attempted)]
            or len(entries) - len(admitted_requests) not in (0, 1)
            or admitted_requests != entries[:len(admitted_requests)]):
        raise ValueError('notification, admission and model-call correspondence differs')
    if signals and read(folder / 'initial_messages_private.json') != base:
        raise ValueError('saved first input differs from reconstruction')
    checks, last_wall = [], limits['max_wall_seconds']
    for index, (call, notification, entry, budget) in enumerate(zip(usage, attempted, admitted_requests, before, strict=True)):
        base, _ = conversation.for_model(limits['observation_page_characters'])
        supplied = validate_signal(notification, base, budget, limits, index)
        wall = notification['state']['remaining']['wall_seconds_at_snapshot']
        if wall > last_wall:
            raise ValueError('remaining wall snapshot increased')
        last_wall = wall
        choice = validate_admission(entry, budget['remaining_tokens_before'], limits)
        if not choice['admitted'] or not entry.get('model_request_started'):
            raise ValueError('generation occurred after rejection')
        cfg = {**limits['model'], 'temperature': limits['agent_temperature'], 'seed': limits['seed'] + index,
               'num_predict': choice['selected_output_cap'], 'cache_prompt': index > 0}
        request, response = (read(folder / call['id'] / name) for name in ('request.json', 'response.json'))
        if request != payload_for(cfg, supplied, CODE_TOOLS):
            raise ValueError('actual request or full history differs')
        if (call['predicted_input_tokens'] != choice['input_tokens']
                or call['output_cap'] != choice['selected_output_cap']):
            raise ValueError('usage admission fields differ')
        check = {'call_id': call['id'], 'remaining_tokens': choice['remaining_tokens'],
                 'counted_input_tokens': choice['input_tokens'], 'output_cap': choice['selected_output_cap'],
                 'notification_characters': notification['notification_characters'],
                 'request_sha256': sha(folder / call['id'] / 'request.json'),
                 'response_sha256': sha(folder / call['id'] / 'response.json'),
                 'raw_terminal_counters_checked': False}
        if call['status'] == 'ok':
            raw_path = folder / call['id'] / 'raw_response.json'
            parsed = parse_response(read(raw_path))
            if any(parsed[k] != response[k] for k in parsed):
                raise ValueError('normalized response differs from raw terminal result')
            if (response['input_tokens'] != choice['input_tokens']
                    or response['output_tokens'] > choice['selected_output_cap']):
                raise ValueError('terminal token count differs from reservation')
            check.update(raw_terminal_counters_checked=True, raw_response_sha256=sha(raw_path))
            if index == 0:
                cache = cache_measurement('cold_1', response, response['input_tokens'])
                if cache != notification.get('first_input_measurement'):
                    raise ValueError('first-input measured cache record differs')
                check['first_cache_confirmed'] = cache['state_confirmed']
                if not cache['state_confirmed'] and summary['stop_reason'] != 'runtime_error':
                    raise ValueError('continued after first-cache violation')
            outer = [spans[e['span_id']] for e in events if e['call'] == call['id'] and e['stage'] == 'model_tool']
            if outer:
                conversation.append(response['message'], outer)
            elif not (index == len(usage) - 1 and summary['stop_reason'] == 'runtime_error'):
                raise ValueError('successful model result lacks recorded execution')
        else:
            if index != len(usage) - 1 or any(e['call'] == call['id'] for e in events):
                raise ValueError('unknown model response was executed or retried')
            if any(response[k] is not None or call[k] is not None for k in ('input_tokens', 'output_tokens')):
                raise ValueError('unknown usage was imputed as a number')
        checks.append(check)
    if signals and len(signals) > len(attempted):
        budget = {'remaining_api_before': limits['max_api_requests'] - prefix_api - total['suffix_api_requests'],
                  'remaining_calls_before': limits['max_calls'] - len(usage),
                  'remaining_tokens_before': limits['max_total_tokens'] - total['known_total_tokens'],
                  'known_tokens_before': total['known_total_tokens']}
        base, _ = conversation.for_model(limits['observation_page_characters'])
        validate_signal(signals[-1], base, budget, limits, len(usage))
        if len(entries) > len(admitted_requests) and 'input_tokens' in entries[-1]:
            choice = validate_admission(entries[-1], budget['remaining_tokens_before'], limits)
            if choice['admitted']:
                raise ValueError('admitted final decision has no model request')
    if (folder / 'conversation_private.json').exists() and read(folder / 'conversation_private.json') != conversation.messages():
        raise ValueError('final underlying history differs from recorded append-only continuation')
    profile = summarize_calls(usage, lambda cid: read(folder / cid / 'response.json'),
                              lambda cid: read(folder / cid / 'request.json'))
    if profile['totals']['known_total_tokens'] != summary['known_total_tokens']:
        raise ValueError('terminal cost profile differs')
    archive = selected = repeated = 0
    queries = Counter()
    sent_names, unsent_names, program_statuses = Counter(), Counter(), Counter()
    for event in events:
        span = spans[event['span_id']]; action = span['action']
        if event['stage'] == 'model_tool' and action:
            archive += action['name'] == 'read_span'
            if action['name'] == 'run_python':
                program_statuses[span['observation'].get('status', 'missing')] += 1
                try: selected += len(json.loads(action['arguments']).get('span_ids', []))
                except (TypeError, ValueError): pass
        if event['stage'] == 'python_api':
            (sent_names if event['api_request_sent'] else unsent_names)[action['name']] += 1
        if event['stage'] == 'python_api' and event['api_request_sent']:
            queries[(action['name'], json.dumps(json.loads(action['arguments']), sort_keys=True))] += 1
    repeated = sum(n - 1 for n in queries.values())
    row = {'run_id': folder.name, 'task_id': item['task_id'], 'arm': arm,
           'record_status': 'evaluated' if evaluated else 'attempted_unevaluated',
           'success': success, 'stop_reason': summary['stop_reason'], 'model_calls': len(usage),
           'known_total_tokens': summary['known_total_tokens'], 'unknown_usage_calls': summary['unknown_usage_calls'],
           'prefix_known_total_tokens': sum(c['input_tokens'] + c['output_tokens'] for c in prefix['usage'] if c['status'] == 'ok'),
           'prefix_unknown_usage_calls': sum(c['status'] != 'ok' for c in prefix['usage']),
           'prefix_model_calls': len(prefix['usage']),
           'api_requests': summary['api_requests'], 'prefix_api_requests': prefix_api,
           'setup_api_requests': setup['environment_replay'].get('api_requests', 0),
           'setup_wall_seconds': setup['wall_seconds'], 'continuation_wall_seconds': summary['wall_seconds'],
           'full_wall_seconds': summary['full_wall_seconds'],
           'display_construction_seconds': summary['transfer'].get('transfer_wall_seconds', 0),
           'input_count_seconds': sum(e.get('count_wall_seconds') or 0 for e in entries),
           'input_counts_without_timing': sum(e.get('count_wall_seconds') is None for e in entries),
           'archive_read_calls': archive, 'selected_prior_receipts': selected,
           'sent_api_names': dict(sent_names), 'unsent_api_names': dict(unsent_names),
           'program_status_counts': dict(program_statuses),
           'repeat_identical_request_excess': repeated, 'source_boundary_sha256': item['boundary_manifest_sha256'],
           'notification_characters': sum(c['notification_characters'] for c in checks),
           'admission_rejections': sum(e.get('admitted') is False for e in entries),
           'reduced_output_caps': sum(c['output_cap'] < limits['max_output_tokens'] for c in usage),
           'first_input_tokens': usage[0]['input_tokens'] if usage else None,
           'first_counted_input_tokens': usage[0]['predicted_input_tokens'] if usage else None,
           'request_checks': checks, 'cost_profile': profile['totals'],
           'source_sha256': {name: sha(folder / name) for name in names}}
    for name in ('budget_signals.json', 'admissions.json', 'conversation_private.json', 'initial_messages_private.json', 'evaluation.json'):
        if (folder / name).exists(): row['source_sha256'][name] = sha(folder / name)
    return row


def audit(storage, root, frozen):
    plan, freeze, preflight = (read(frozen / name) for name in (PLAN, ACTIVATION, PREFLIGHT))
    for name, value in freeze['source_hashes'].items():
        if sha(frozen / name) != value:
            raise ValueError('frozen implementation changed: ' + name)
        if (root / name).exists() and sha(root / name) != value:
            raise ValueError('audit dependency differs from executed code: ' + name)
    folder = storage / 'records/context_pilot' / plan['batch_id']
    state = read(folder / 'status.json')
    if state['status'] not in ('complete', 'stopped'):
        raise ValueError('wait for the entire fixed batch to close')
    if (read(folder / 'frozen_plan.json') != plan or read(folder / 'activation.json') != freeze
            or read(folder / 'preflight.json') != preflight or sha(frozen / PREFLIGHT) != freeze['preflight_sha256']
            or sha(frozen / 'reports/P47_runtime_checks.json') != freeze['runtime_check_sha256']
            or state['model_identity'] != preflight['model_identity']
            or state['git_commit'] != preflight['git_commit']):
        raise ValueError('batch activation or preflight changed')
    _, original, tools, schemas, items = prepare_later_sources(storage, frozen)
    order = [cell_id(n, arm) for n, _, arm in run_order(items)]
    started = [r['run_id'] for r in state['rows']]
    if (state['planned'] != order or started != order[:len(started)]
            or state['completed'] != started[:len(state['completed'])]
            or (state['status'] == 'complete' and (len(state['completed']) != 12 or state['active'] is not None))):
        raise ValueError('fixed cohort or execution order differs')
    rows = []
    for number, item in enumerate(items, 1):
        for arm in ARMS:
            rid = cell_id(number, arm); trial = storage / 'records/context_pilot' / rid
            if rid not in started:
                if trial.exists():
                    raise ValueError('unaccounted partial cell requires investigation: ' + rid)
                rows.append({'run_id': rid, 'task_id': item['task_id'], 'arm': arm,
                             'record_status': 'not_run_after_stop', 'success': None,
                             'model_calls': 0, 'known_total_tokens': 0, 'unknown_usage_calls': 0,
                             'api_requests': 0, 'prefix_api_requests': 0, 'setup_api_requests': 0})
                continue
            row = audit_cell(trial, item, arm, original, plan,
                             preflight['rows'][number - 1]['conditions'][arm], rid in state['completed'])
            # Frozen helper uses its arm only to select the feedback mode.
            # Every P55 condition uses the same public_schema mode.
            row['feedback_audit'] = audit_feedback_cell(trial, item, 'full_contract_keep', tools, schemas)
            row['inventory_input_changed'] = not preflight['rows'][number - 1]['detail_vs_both_base_equal']
            row['feedback_count'] = len(row['feedback_audit']['feedback_events'])
            row['feedback_control_seconds'] = row['feedback_audit']['control_wall_seconds']
            saved = next(r for r in state['rows'] if r['run_id'] == rid)
            if any(row[k] != saved[k] for k in ('task_id', 'arm', 'model_calls', 'known_total_tokens',
                                               'unknown_usage_calls', 'api_requests', 'prefix_api_requests')):
                raise ValueError('batch and cell counters disagree')
            if rid in state['completed']:
                if row['success'] != saved['success']:
                    raise ValueError('batch and official success differ')
                summary = read(trial / 'summary.json')
                if (saved['disposition'] != disposition(summary) or not saved['idle_recovery']['one_slot_idle']
                        or not 0 <= saved['idle_recovery']['wall_seconds'] <= plan['max_idle_wait_seconds'] + 10):
                    raise ValueError('evaluation followed invalid disposition or idle recovery')
                row['idle_recovery_seconds'] = saved['idle_recovery']['wall_seconds']
            rows.append(row)
    if (state['not_run'] != [rid for rid in order if rid not in started]
            or state['unevaluated'] != [rid for rid in started if rid not in state['completed']]):
        raise ValueError('missing-cell accounting differs')
    totals = {}
    for row in rows:
        row['logical_task_known_total_tokens'] = row.get('prefix_known_total_tokens', 0) + row['known_total_tokens']
        row['logical_task_unknown_usage_calls'] = row.get('prefix_unknown_usage_calls', 0) + row['unknown_usage_calls']
        row['logical_task_model_calls'] = row.get('prefix_model_calls', 0) + row['model_calls']
        row['logical_task_api_requests'] = row['prefix_api_requests'] + row['api_requests']
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        total = {'planned_trials': 4, 'attempted_trials': sum(r['record_status'] != 'not_run_after_stop' for r in selected),
                 'evaluated_trials': sum(r['record_status'] == 'evaluated' for r in selected),
                 'successes': sum(r['success'] is True for r in selected)}
        for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'prefix_api_requests',
                    'setup_api_requests', 'setup_wall_seconds', 'continuation_wall_seconds', 'full_wall_seconds',
                    'display_construction_seconds', 'input_count_seconds', 'notification_characters',
                    'archive_read_calls', 'selected_prior_receipts', 'reduced_output_caps', 'admission_rejections',
                    'feedback_count', 'feedback_control_seconds', 'prefix_known_total_tokens',
                    'prefix_unknown_usage_calls', 'logical_task_known_total_tokens', 'logical_task_unknown_usage_calls',
                    'prefix_model_calls', 'logical_task_model_calls', 'logical_task_api_requests'):
            total[key] = sum(r.get(key, 0) for r in selected)
        profile = Counter()
        for row in selected: profile.update(row.get('cost_profile', {}))
        total['cost_profile'] = dict(profile)
        totals[arm] = total
    return {'phase': 'P55', 'batch_status': state['status'], 'all_planned_cells_accounted': True,
            'audit_errors': [], 'rows': rows, 'totals': totals,
            'record_status_counts': dict(Counter(r['record_status'] for r in rows)), **development_gate(rows),
            'additional_model_calls': 0, 'additional_api_requests': 0, 'additional_tokenizer_requests': 0,
            'additional_evaluator_calls': 0, 'reserved_scenarios_read': 0,
            'primary_cost': 'common measured prefix plus all continuation logical input and output tokens',
            'identical_input_negative_control': 'P29_03_CODE D and B; any behavioral difference is not inventory causality',
            'source_sha256': {'plan': sha(frozen / PLAN), 'activation': sha(frozen / ACTIVATION),
                'preflight': sha(frozen / PREFLIGHT), 'batch_status': sha(folder / 'status.json'),
                'runtime_checks': sha(frozen / 'reports/P47_runtime_checks.json'),
                'auditor': sha(Path(__file__)),
                'feedback_auditor': sha(root / 'scripts/audit_contract_feedback.py')},
            'limits': ['Four known development tasks, one continuation per condition, no statistical noninferiority claim.',
                       'Unknown terminal usage is additional to known totals and never imputed as zero.',
                       'Raw server counters and saved inputs were reconstructed; no independent retokenization.',
                       'Repeated identical requests include necessary reads and writes, not proven waste.',
                       'Notification characters and construction time are not marginal token attributions.',
                       'Single-worker display and ordinary feedback controls; combination alone establishes neither novelty nor multi-agent savings.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--frozen-root', type=Path, required=True); args = parser.parse_args()
    target = args.repo_root / 'reports/P55_comparison.json'
    if target.exists(): raise FileExistsError('preserve all previous audits')
    result = audit(args.storage_root, args.repo_root, args.frozen_root)
    write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'record_status_counts', 'development_gate_met')})

"""Reconstruct inline requests, metadata transport and shared accounting.

Reads saved records only. No model, tokenizer, generated program, API, evaluator
or semantic summary judge runs. Separate-summary cells use the frozen P118 audit.
"""
from collections import Counter
from copy import deepcopy
import json
from types import SimpleNamespace

from api_error_comparison import task_snapshot
from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission
from audit_single_checkpoint_trace import audit_trace as audit_separate
from budget_observation import notification
from checkpoint_attempt_usage import attempt_usage
from inference_cache_control import cache_measurement
from inline_checkpoint_history import InlineCheckpoint
from inline_checkpoint_protocol import split_inline_response
from local_llama import parse_response
from native_data_compute import selected_receipts
from public_display import CODE_TOOLS
from receipt_reasoning_history import digest, require
from run_handoff_factors import read, sha
from tool_choice_local_llama import payload_for


class CountStopped(Exception):
    pass


def audit_trace(folder, config, conversation):
    if config['checkpoint_policy'] == 'single_checkpoint':
        return audit_separate(folder, config, conversation)
    require(config['checkpoint_policy'] == 'inline_checkpoint', 'explicit_inline_audit_policy_required')

    def saved(name, default=None):
        path = folder / (name + '.json')
        return read(path) if path.exists() else deepcopy(default)

    summary, usage, terminal, admissions, events, spans = [saved(n) for n in (
        'summary', 'usage', 'terminal_usage', 'admissions', 'events', 'spans')]
    admissions = admissions or []
    signals = saved('budget_observations', [])
    views, controls, counts = [saved(n, []) for n in (
        'inline_history_views', 'inline_controls', 'inline_input_counts')]
    require(attempt_usage(SimpleNamespace(calls=terminal, admissions=admissions)) == usage,
            'shared_dispatch_accounting_changed')
    budgets, total = budget_before_calls(usage, events, 0, config)
    require(summary['model_calls'] == len(usage) and
            summary['known_total_tokens'] == total['known_total_tokens'] and
            summary['unknown_usage_calls'] == total['unknown_usage_calls'] and
            summary['api_requests'] == total['suffix_api_requests'], 'worker_accounting_changed')
    require(len(usage) <= config['max_calls'] and total['known_total_tokens'] <= config['max_total_tokens'] and
            total['suffix_api_requests'] <= config['max_api_requests'], 'shared_budget_exceeded')
    require(all(c['role'] == 'agent' for c in usage), 'inline_must_not_hide_a_summary_or_judge_call')
    ids = [e['span_id'] for e in events]
    require(len(ids) == len(set(ids)) and set(ids) == set(spans), 'event_archive_mismatch')
    receipts = [e['api_execution'] for e in events if 'api_execution' in e]
    require(receipts == summary['api_execution_receipts'], 'invocation_receipts_changed')
    require(sum(e['effects_unknown'] for e in events if e['api_request_sent']) ==
            summary['unknown_effect_requests'], 'unknown_effect_accounting_changed')
    for event in events:
        if event['api_request_sent']:
            receipt = event.get('api_execution')
            require(receipt and receipt['bridge_request_sent'] and not receipt['automatic_retries'],
                    'sent_API_requires_one_typed_receipt')
            if receipt['status'] == 'raised':
                require(not event['new_tools'] and 'api_error' in spans[event['span_id']]['observation'],
                        'confirmed_exception_presentation_changed')
        elif event['stage'] == 'model_tool':
            require('api_execution' not in event, 'outer_tool_cannot_send_API')
        require('inline_transport' not in event or event['stage'] == 'model_tool',
                'inline_binding_on_inner_API')
    dispatches = [a for a in admissions if a.get('model_request_started')]
    require([a['next_call_id'] for a in dispatches] == [c['id'] for c in usage], 'all_shared_attempts_required')
    signal_map = {s['next_call_id']: s for s in signals}
    view_map = {v['next_agent_call_id']: v for v in views}
    require(len(signal_map) == len(signals) and len(view_map) == len(views) and
            set(signal_map) == set(view_map), 'unique_actor_signal_and_view_required')
    require([s['next_call_id'] for s in signals if s['model_attempted']] == [c['id'] for c in usage],
            'actor_signal_attempts_changed')
    control = InlineCheckpoint()
    expected_controls, checks, prior = [], [], {}
    count_index, last_wall, offered_call_id = 0, config['max_wall_seconds'], None

    def supplied(base, prefix, api):
        return notification(base, task_snapshot(config, prefix, api, 0), 'not_exposed')[0]

    def take_count(number, purpose, messages, tools):
        nonlocal count_index
        require(count_index < len(counts), 'expected_native_count_missing')
        count = counts[count_index]; count_index += 1
        require(count['after_model_calls'] == number and count['purpose'] == purpose and
                count['messages_sha256'] == digest(messages) and count['tools_sha256'] == digest(tools),
                'native_count_not_bound_to_exact_input')
        if count['status'] == 'failed':
            require(number == len(usage) and count_index == len(counts), 'failed_count_must_stop')
            raise CountStopped()
        require(count['status'] == 'complete' and type(count['input_tokens']) is int and
                count['input_tokens'] > 0, 'positive_native_count_required')
        return count['input_tokens']

    for number in range(len(usage) + 1):
        if number and usage[number - 1]['status'] != 'ok':
            break
        base, _ = conversation.for_model(config['observation_page_characters'])
        api = sum(e['api_request_sent'] for e in events if e['call'] in {c['id'] for c in usage[:number]})
        cid = f'call_{number + 1:03d}'
        signal = signal_map.get(cid)
        # A completed/stopped cell need not resolve its final valid checkpoint
        # when no next input count or agent request exists.
        if signal is None and not any(c['after_model_calls'] == number for c in counts[count_index:]):
            break
        try:
            if control.opportunity_used and control.decision is None:
                require(control.after == base and control.views is not None, 'unclosed_inline_continuation')
                a = take_count(number, 'ordinary_next_input', supplied(control.views['ordinary'], usage[:number], api), CODE_TOOLS)
                b = take_count(number, 'compacted_next_input', supplied(control.views['compacted'], usage[:number], api), CODE_TOOLS)
                decision = control.decide(a, b)
                expected_controls.append({'status': 'checkpoint_decided', 'after_model_calls': number,
                                          **decision, 'semantics_verified': False})
                require(saved('inline_checkpoint_private') == {
                    'proposal': control.proposal, 'checkpoint': control.split['checkpoint'],
                    'transport_binding': control.split['binding'], 'decision': decision},
                    'saved_inline_checkpoint_changed')
            working, tools, offered = control.view(base), CODE_TOOLS, None
            if not control.opportunity_used:
                n = take_count(number, 'trigger', supplied(base, usage[:number], api), CODE_TOOLS)
                offered = control.begin(base, CODE_TOOLS, n)
                expected_controls.append({'status': 'inline_offered' if offered else 'below_trigger_or_recent_only',
                    'after_model_calls': number, 'trigger_input_tokens': n,
                    'source_archive_sha256': digest(base), 'semantics_verified': False})
                if offered is not None:
                    working, tools, offered_call_id = offered['messages'], offered['tools'], cid
                    require(saved('inline_offer_private') == offered, 'saved_inline_offer_changed')
        except CountStopped:
            require(signal is None, 'generation_after_failed_control_count')
            break
        if signal is None:
            require(number == len(usage), 'missing_actor_signal')
            break
        state = signal['measured_state']
        expected_state = task_snapshot(config, usage[:number], api, 0)
        wall = state['remaining']['wall_seconds_at_snapshot']
        expected_state['remaining']['wall_seconds_at_snapshot'] = wall
        require(state == expected_state and 0 <= wall <= last_wall, 'actor_shared_budget_notice_changed')
        last_wall = wall
        messages, visible = notification(working, state, 'not_exposed')
        require(signal['visible_state'] == visible and signal['time_visibility'] == 'not_exposed' and
                signal['model_messages_sha256'] == digest(messages) and
                signal['model_tools_sha256'] == digest(tools) and signal['cache_prompt'] == (number > 0),
                'actor_notice_or_schema_changed')
        require(view_map[cid] == {'next_agent_call_id': cid,
            'original_history_sha256': digest(base), 'working_history_sha256': digest(working),
            'tools_sha256': digest(tools), 'inline_offered': offered is not None,
            'checkpoint_used': bool(control.decision and control.decision['accepted']),
            'archive_deleted': False, 'semantics_verified': False}, 'inline_projection_changed')
        if not signal['model_attempted']:
            require(number == len(usage), 'unattempted_request_before_later_dispatch')
            pending = [a for a in admissions if a['next_call_id'] == cid]
            require((len(pending) == 1 and not pending[0].get('model_request_started')) or
                    (not pending and summary['stop_reason'] in ('call_limit', 'wall_limit')),
                    'unattempted_admission_changed')
            if pending and 'admitted' in pending[0]:
                validate_admission(pending[0], config['max_total_tokens'] - total['known_total_tokens'], config)
            break
        require(number < len(usage), 'signal_without_usage_attempt')
        call, budget, admission = usage[number], budgets[number], dispatches[number]
        require(call['id'] == cid, 'sequential_actor_identity_required')
        choice = validate_admission(admission, budget['remaining_tokens_before'], config)
        require(choice['admitted'], 'generation_after_budget_rejection')
        cfg = {**config['model'], 'temperature': config['agent_temperature'],
               'seed': config['seed'] + number, 'num_predict': choice['selected_output_cap'],
               'cache_prompt': number > 0}
        request_path, response_path = folder / cid / 'request.json', folder / cid / 'response.json'
        request = read(request_path) if request_path.exists() else None
        response = read(response_path) if response_path.exists() else None
        missing = call.get('error_kind') == 'dispatched_without_terminal_usage'
        require(request is None or request == payload_for(cfg, messages, tools), 'actual_inline_request_differs')
        if missing:
            require(response is None and call['server_receipt_confirmed'] is False,
                    'missing_terminal_cannot_gain_receipt')
        else:
            require(request is not None and response is not None and
                    call['predicted_input_tokens'] == choice['input_tokens'] and
                    call['output_cap'] == choice['selected_output_cap'], 'terminal_reservation_changed')
        selected_events = [e for e in events if e['call'] == cid]
        if call['status'] != 'ok':
            require(number == len(usage) - 1 and not selected_events and
                    all(call[k] is None and (response is None or response[k] is None)
                        for k in ('input_tokens', 'output_tokens')), 'unknown_usage_executed_or_imputed')
        else:
            parsed = parse_response(read(folder / cid / 'raw_response.json'))
            require(all(parsed[k] == response[k] for k in parsed), 'raw_terminal_normalization_changed')
            require(all(call.get(k) == response.get(k) for k in (
                'input_tokens', 'output_tokens', 'cached_input_tokens')) and
                call['finish_reason'] == response['done_reason'], 'terminal_usage_changed')
            require(response['input_tokens'] == choice['input_tokens'] and
                    response['output_tokens'] <= choice['selected_output_cap'], 'terminal_exceeded_admission')
            cold_ok = True
            if number == 0:
                cold = cache_measurement('cold_1', response, response['input_tokens'])
                cold_ok = cold['state_confirmed']
                require(signal.get('first_input_measurement') == cold, 'first_cache_measurement_changed')
            outer_events = [e for e in selected_events if e['stage'] == 'model_tool']
            if outer_events:
                require(cold_ok, 'execution_after_non_cold_first_request')
                split = split_inline_response(response['message'], offered=offered is not None,
                    finish_reason=response['done_reason'], usage_known=True)
                outer = [spans[e['span_id']] for e in outer_events]
                for i, event in enumerate(outer_events):
                    if split['binding'] is not None:
                        expected_binding = {'version': 'inline_checkpoint_transport_v01',
                            'original_payload_sha256': split['original_payload_sha256'],
                            **split['binding'], 'status': split['status'],
                            'execution_success_verified': False, 'semantics_verified': False}
                        require(len(outer_events) == 1 and event.get('inline_transport') == expected_binding,
                                'inline_execution_binding_changed')
                    else:
                        require('inline_transport' not in event, 'unexpected_inline_transport_binding')
                    path = folder / 'programs' / f'{cid}_{i + 1:02d}' / 'input_private.json'
                    calls = split['execution_message'].get('tool_calls') or []
                    fn = calls[i]['function'] if calls else None
                    observation = outer[i]['observation']
                    needs_program = fn and fn['name'] == 'run_python' and 'status' in observation
                    require(not needs_program or path.exists(), 'submitted_program_source_missing')
                    if path.exists():
                        args = json.loads(fn['arguments'])
                        payload = read(path)
                        require(set(args) == {'code', 'span_ids'} and payload['code'] == args['code'] and
                                payload['observations'] == selected_receipts(args['span_ids'], prior),
                                'submitted_program_or_receipt_selection_changed')
                conversation.append(response['message'], outer)
                if offered is not None:
                    after, _ = conversation.for_model(config['observation_page_characters'])
                    projected = control.close(after, split)
                    expected_controls.append({'status': 'offered_turn_closed', 'after_model_calls': number + 1,
                        'split_status': split['status'], 'ordinary_sha256': projected['ordinary_sha256'],
                        'compacted_sha256': projected['compacted_sha256'],
                        'transport_metadata_hidden': projected['transport_metadata_hidden'], 'semantics_verified': False})
                    stored = saved('inline_closed_turn_private')
                    require(stored == {'split': split, 'view_hashes': {k: v for k, v in projected.items()
                            if k.endswith('_sha256')}, 'decision': control.decision}, 'closed_inline_state_changed')
            else:
                require(number == len(usage) - 1 and not selected_events and summary['stop_reason'] in (
                    'runtime_error', 'wall_limit', 'api_request_limit', 'user_stop', 'cleanup_error'),
                    'known_response_without_execution_record')
        prior.update({e['span_id']: spans[e['span_id']] for e in selected_events})
        checks.append({'call_id': cid, 'role': 'agent', 'status': call['status'],
            **{k: call.get(k) for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'finish_reason')},
            'request_sha256': sha(request_path) if request_path.exists() else None,
            'response_sha256': sha(response_path) if response_path.exists() else None,
            'API_requests': sum(e['api_request_sent'] for e in selected_events),
            'inline_offered': offered is not None})
    require(count_index == len(counts) and controls == expected_controls, 'control_timeline_changed')
    require(saved('conversation_private', conversation.messages()) == conversation.messages(), 'archive_replay_changed')
    terminals = {c['id']: c for c in terminal}
    for signal in signals:
        if signal['model_attempted']:
            call = terminals.get(signal['next_call_id'])
            require(signal['terminal_usage_recorded'] == (call is not None) and
                    signal['usage_unknown'] == (call is None or call['status'] != 'ok'),
                    'actor_signal_terminal_status_changed')
    known = [c for c in usage if c['status'] == 'ok']
    by_role = {'agent': {'calls': len(usage), 'unknown_usage': len(usage) - len(known),
        'input_tokens': sum(c['input_tokens'] for c in known), 'output_tokens': sum(c['output_tokens'] for c in known)},
        'focus': {'calls': 0, 'unknown_usage': 0, 'input_tokens': 0, 'output_tokens': 0}}
    require(summary['usage_by_role'] == by_role, 'role_totals_changed')
    expected_summary = {'policy': 'inline_checkpoint', 'opportunity_used': control.opportunity_used,
        'offered_call_id': offered_call_id, 'offered_turn_closed': control.after is not None,
        'checkpoint_installed': bool(control.decision and control.decision['accepted']),
        'valid_checkpoint_pending_without_next_request': bool(
            control.views and control.views['compacted'] is not None and control.decision is None),
        'decision': control.decision, 'separate_summary_calls': 0, 'judge_calls': 0,
        'all_metadata_output_charged_as_agent': True, 'control_cost_included_in_work_wall': True,
        'archive_deleted': False, 'semantic_fidelity_verified': False,
        'task_quality_established': False, 'novel_method_claim': False}
    require(summary['checkpoint_control'] == expected_summary, 'inline_summary_disposition_changed')
    return {**total, 'model_calls': len(usage), 'usage_by_role': by_role, 'request_checks': checks,
        'checkpoint_installed': expected_summary['checkpoint_installed'],
        'checkpoint_opportunity': 'inline_offered' if control.opportunity_used else None,
        'checkpoint_controls': controls, 'input_count_records': len(counts),
        'invocation_status_counts': dict(Counter(r['status'] for r in receipts)),
        'additional_model_calls': 0, 'additional_API_requests': 0, 'additional_tokenizer_calls': 0,
        'summary_semantics_verified': False}

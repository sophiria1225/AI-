"""Replay the recorded protocol and shared ledger without model/API execution.

No summary is judged semantically. Recorded native input counts are bound to
their rendered inputs; this audit does not run another tokenizer or infer
counterfactual future behavior.
"""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

from api_error_comparison import task_snapshot
from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission
from budget_observation import notification
from checkpoint_attempt_usage import attempt_usage
from fixed_budget_local_llama import payload_for as summary_payload
from inference_cache_control import cache_measurement
from local_llama import parse_response
from public_display import CODE_TOOLS
from receipt_reasoning_history import digest, require
from run_handoff_factors import read, sha
from single_checkpoint_history import (
    TRIGGER_INPUT_TOKENS, RECENT_TURNS, candidate, closed_turns, parse_checkpoint, project)
from tool_choice_local_llama import payload_for as agent_payload


def audit_trace(folder, config, conversation):
    def saved(name, default=None):
        path = folder / (name + '.json')
        return read(path) if path.exists() else deepcopy(default)

    summary, usage, terminal, admissions, events, spans = [saved(n) for n in (
        'summary', 'usage', 'terminal_usage', 'admissions', 'events', 'spans')]
    admissions = admissions or []
    signals = saved('budget_observations', [])
    views = saved('checkpoint_history_views', [])
    controls = saved('checkpoint_controls', [])
    counts = saved('checkpoint_input_counts', [])
    require(attempt_usage(SimpleNamespace(calls=terminal, admissions=admissions)) == usage,
            'shared_dispatch_accounting_changed')
    budgets, total = budget_before_calls(usage, events, 0, config)
    require(summary['model_calls'] == len(usage) and
            summary['known_total_tokens'] == total['known_total_tokens'] and
            summary['unknown_usage_calls'] == total['unknown_usage_calls'] and
            summary['api_requests'] == total['suffix_api_requests'], 'worker_accounting_changed')
    require(len(usage) <= config['max_calls'] and total['known_total_tokens'] <= config['max_total_tokens'] and
            total['suffix_api_requests'] <= config['max_api_requests'], 'shared_budget_exceeded')
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
    dispatches = [a for a in admissions if a.get('model_request_started')]
    require([a['next_call_id'] for a in dispatches] == [c['id'] for c in usage],
            'all_shared_attempts_required')
    signal_map = {s['next_call_id']: s for s in signals}
    view_map = {v['next_agent_call_id']: v for v in views}
    require(len(signal_map) == len(signals) and len(view_map) == len(views) and
            set(signal_map) == set(view_map), 'unique_actor_signal_and_view_required')
    opportunities = [c for c in controls if c['status'] != 'below_trigger_or_recent_only']
    require(len(opportunities) <= 1, 'only_one_checkpoint_opportunity')
    control = opportunities[0] if opportunities else None
    agent_number = summary_number = 0
    checkpoint = proposal = None
    states, proposed_views, checks = {}, {}, []
    last_wall = config['max_wall_seconds']

    def supplied(base, prefix, api):
        state = task_snapshot(config, prefix, api, 0)
        return notification(base, state, 'not_exposed')[0]

    def check_signal(signal, view, base, working, index, api, tokens):
        nonlocal last_wall
        state = signal['measured_state']
        expected = task_snapshot(config, usage[:index], api, 0)
        require(state['used'] == expected['used'], 'actor_notice_shared_cost_changed')
        expected['remaining']['wall_seconds_at_snapshot'] = state['remaining']['wall_seconds_at_snapshot']
        require(state == expected and 0 <= state['remaining']['wall_seconds_at_snapshot'] <= last_wall,
                'actor_notice_limits_changed')
        last_wall = state['remaining']['wall_seconds_at_snapshot']
        actual, visible = notification(working, state, 'not_exposed')
        require(signal['visible_state'] == visible and signal['time_visibility'] == 'not_exposed' and
                signal['model_messages_sha256'] == digest(actual) and signal['cache_prompt'] == (index > 0),
                'actor_notice_or_rendered_input_changed')
        require(view['original_history_sha256'] == digest(base) and
                view['working_history_sha256'] == digest(working) and
                view['checkpoint_used'] == (checkpoint is not None) and
                view['archive_deleted'] is False and view['semantics_verified'] is False,
                'checkpoint_projection_changed')
        return actual

    for index, (call, admission, budget) in enumerate(zip(usage, dispatches, budgets, strict=True)):
        base, _ = conversation.for_model(config['observation_page_characters'])
        api = config['max_api_requests'] - budget['remaining_api_before']
        states[index] = {'base': deepcopy(base), 'api': api,
                         'proposal': deepcopy(proposal), 'checkpoint': deepcopy(checkpoint)}
        selected_events = [e for e in events if e['call'] == call['id']]
        if call['role'] == 'focus':
            require(summary_number == 0 and config['checkpoint_policy'] == 'single_checkpoint' and
                    not selected_events and call['id'] not in signal_map and control is not None and
                    control['after_model_calls'] == index, 'summary_must_not_execute_or_repeat')
            possible = candidate(base)
            require(possible is not None, 'summary_requires_closed_old_turns')
            for key in ('cutoff', 'source_prefix_sha256', 'source_archive_sha256',
                        'replaced_turns', 'retained_recent_turns'):
                require(control[key] == possible[key], 'summary_source_boundary_changed')
            messages, tools, transport = possible['summary_messages'], [], summary_payload
            role_number, temperature = summary_number, config['draft_temperature']
            summary_number += 1
        else:
            require(call['role'] == 'agent' and call['id'] in signal_map, 'known_actor_call_required')
            working = project(base, proposal, checkpoint) if checkpoint is not None else base
            messages = check_signal(signal_map[call['id']], view_map[call['id']], base, working, index,
                                    api, budget['known_tokens_before'])
            tools, transport = CODE_TOOLS, agent_payload
            role_number, temperature = agent_number, config['agent_temperature']
            agent_number += 1
        choice = validate_admission(admission, budget['remaining_tokens_before'], config)
        require(choice['admitted'], 'generation_after_budget_rejection')
        cfg = {**config['model'], 'temperature': temperature, 'seed': config['seed'] + role_number,
               'num_predict': choice['selected_output_cap'], 'cache_prompt': index > 0}
        request_path, response_path = folder / call['id'] / 'request.json', folder / call['id'] / 'response.json'
        request = read(request_path) if request_path.exists() else None
        response = read(response_path) if response_path.exists() else None
        missing = call.get('error_kind') == 'dispatched_without_terminal_usage'
        require(request is None or request == transport(cfg, messages, tools), 'actual_request_differs')
        if not missing:
            require(request is not None and response is not None and
                    call['predicted_input_tokens'] == choice['input_tokens'] and
                    call['output_cap'] == choice['selected_output_cap'], 'terminal_reservation_changed')
        else:
            require(response is None and call['server_receipt_confirmed'] is False,
                    'missing_terminal_cannot_gain_receipt')
        if call['status'] == 'ok':
            parsed = parse_response(read(folder / call['id'] / 'raw_response.json'))
            require(all(parsed[k] == response[k] for k in parsed), 'raw_terminal_normalization_changed')
            require(all(call.get(k) == response.get(k) for k in (
                'input_tokens', 'output_tokens', 'cached_input_tokens')), 'terminal_usage_changed')
            require(call['finish_reason'] == response['done_reason'], 'terminal_finish_reason_changed')
            require(response['input_tokens'] == choice['input_tokens'] and
                    response['output_tokens'] <= choice['selected_output_cap'], 'terminal_exceeded_admission')
            if index == 0:
                cold = cache_measurement('cold_1', response, response['input_tokens'])
                require(call['role'] == 'agent' and cold['state_confirmed'] and
                        signal_map[call['id']].get('first_input_measurement') == cold, 'first_actor_not_cold')
            if call['role'] == 'focus':
                try:
                    value = parse_checkpoint(response['message'], response['done_reason'])
                except (ValueError, TypeError, RecursionError):
                    require(control['status'] == 'invalid_summary_keep_original', 'invalid_summary_accepted')
                else:
                    proposed_views[index + 1] = project(base, possible, value)
                    require(control['status'] in ('checkpoint_installed', 'not_shorter_keep_original', 'aborted'),
                            'valid_summary_disposition_changed')
                    if control['status'] == 'checkpoint_installed':
                        require(control['checkpoint_next_input_tokens'] < control['ordinary_next_input_tokens'],
                                'nonshrinking_checkpoint_installed')
                        require(control['checkpoint_sha256'] == digest(value), 'checkpoint_value_changed')
                        proposal, checkpoint = deepcopy(possible), value
                        proposal.pop('summary_messages')
            else:
                outer = [spans[e['span_id']] for e in selected_events if e['stage'] == 'model_tool']
                if outer:
                    conversation.append(response['message'], outer)
                else:
                    require(index == len(usage) - 1 and not selected_events and summary['stop_reason'] in (
                        'runtime_error', 'wall_limit', 'api_request_limit', 'user_stop', 'cleanup_error'),
                        'actor_response_without_execution_record')
        else:
            require(index == len(usage) - 1 and not selected_events and
                    all(call[k] is None and (response is None or response[k] is None)
                        for k in ('input_tokens', 'output_tokens')), 'unknown_usage_executed_or_imputed')
            if call['role'] == 'focus':
                require(control['status'] == 'aborted', 'unknown_summary_not_aborted')
        checks.append({'call_id': call['id'], 'role': call['role'], 'status': call['status'],
                       'input_tokens': call['input_tokens'], 'output_tokens': call['output_tokens'],
                       'cached_input_tokens': call.get('cached_input_tokens'),
                       'finish_reason': call.get('finish_reason'),
                       'request_sha256': sha(request_path) if request_path.exists() else None,
                       'response_sha256': sha(response_path) if response_path.exists() else None,
                       'API_requests': sum(e['api_request_sent'] for e in selected_events)})

    base, _ = conversation.for_model(config['observation_page_characters'])
    states[len(usage)] = {'base': base, 'api': total['suffix_api_requests'],
                          'proposal': proposal, 'checkpoint': checkpoint}
    require(saved('conversation_private', conversation.messages()) == conversation.messages(), 'archive_replay_changed')
    if checkpoint is not None:
        require(saved('checkpoint_private') == {'proposal': proposal, 'checkpoint': checkpoint},
                'stored_checkpoint_changed')
    require([c['after_model_calls'] for c in counts] == sorted(c['after_model_calls'] for c in counts),
            'input_count_timeline_changed')
    for count in counts:
        number = count['after_model_calls']
        require(number in states and all(c['status'] == 'ok' for c in usage[:number]),
                'input_count_after_unknown_or_missing_state')
        state = states[number]
        if count['role'] == 'focus':
            possible = candidate(state['base'])
            require(possible is not None and control is not None and control['after_model_calls'] == number,
                    'unexpected_summary_input_count')
            allowed, tools = [possible['summary_messages']], []
        else:
            require(count['role'] == 'agent', 'unknown_input_count_role')
            bases = [state['base']]
            if state['checkpoint'] is not None:
                bases.append(project(state['base'], state['proposal'], state['checkpoint']))
            if number in proposed_views:
                bases.append(proposed_views[number])
            allowed = [supplied(b, usage[:number], state['api']) for b in bases]
            tools = CODE_TOOLS
        require(count['tools_sha256'] == digest(tools) and
                count['messages_sha256'] in {digest(m) for m in allowed}, 'count_input_not_bound_to_history')
        require(count['status'] == 'failed' or count['status'] == 'complete' and
                type(count.get('input_tokens')) is int and count['input_tokens'] > 0,
                'invalid_recorded_native_count')
    for event in controls:
        number = event['after_model_calls']
        require(number in states, 'control_without_prefix_state')
        state = states[number]
        expected = digest(supplied(state['base'], usage[:number], state['api']))
        matching = [c for c in counts if c['after_model_calls'] == number and c['role'] == 'agent' and
                    c['status'] == 'complete' and c['messages_sha256'] == expected]
        require(matching, 'control_trigger_count_missing')
        measured = event.get('trigger_input_tokens', event.get('count', {}).get('input_tokens'))
        require(any(c['input_tokens'] == measured for c in matching), 'control_trigger_count_changed')
        eligible = measured >= TRIGGER_INPUT_TOKENS and len(closed_turns(state['base'])) > RECENT_TURNS
        require(eligible == (event['status'] != 'below_trigger_or_recent_only'), 'checkpoint_trigger_changed')
        if event is control:
            if config['checkpoint_policy'] == 'full':
                require(event['status'] == 'full_control_retains_archive' and summary_number == 0,
                        'full_control_changed')
            else:
                relevant = [c for c in usage if c['role'] == 'focus']
                known = [c for c in relevant if c['status'] == 'ok']
                require(event['summary_known_tokens'] == sum(c['input_tokens'] + c['output_tokens'] for c in known)
                        and event['unknown_usage_calls'] == sum(c['status'] != 'ok' for c in relevant)
                        and event['model_attempted'] == bool(relevant), 'summary_control_cost_changed')
                missing = sum(c.get('terminal_usage_recorded') is False for c in relevant)
                require(event['dispatched_without_terminal_usage'] == missing and
                        event['summary_calls'] == len(relevant) - missing, 'summary_terminal_count_changed')
                if 'summary_input_count' in event:
                    n = event['summary_input_count']['input_tokens']
                    summary_counts = [c for c in counts if c['after_model_calls'] == number and
                                      c['role'] == 'focus' and c['status'] == 'complete']
                    require(len(summary_counts) == 1 and summary_counts[0]['input_tokens'] == n,
                            'summary_screening_count_changed')
                    reservation = n + measured + 2 * config['max_output_tokens']
                    require(event['screening_tokens_using_current_agent_input'] == reservation,
                            'summary_screening_reservation_changed')
                    enough_calls = number + 2 <= config['max_calls']
                    tokens = sum(c['input_tokens'] + c['output_tokens'] for c in usage[:number])
                    enough_tokens = tokens + reservation <= config['max_total_tokens']
                    enough_context = n + config['max_output_tokens'] <= config['model']['num_ctx']
                    skipped = ('insufficient_shared_call_budget' if not enough_calls else
                               'insufficient_shared_token_budget' if not enough_tokens else
                               'summary_context_limit' if not enough_context else None)
                    if skipped is not None:
                        require(event['status'] == skipped and not relevant, 'summary_screening_bypassed')
                    else:
                        require(event['status'] not in ('insufficient_shared_call_budget',
                            'insufficient_shared_token_budget', 'summary_context_limit'), 'summary_skip_reason_changed')
                if event['status'] in ('checkpoint_installed', 'not_shorter_keep_original'):
                    require((event['checkpoint_next_input_tokens'] < event['ordinary_next_input_tokens']) ==
                            (event['status'] == 'checkpoint_installed'), 'checkpoint_size_decision_changed')
                    post = [c for c in counts if c['after_model_calls'] == number + 1 and c['role'] == 'agent'
                            and c['status'] == 'complete']
                    require([c['input_tokens'] for c in post] == [event['ordinary_next_input_tokens'],
                            event['checkpoint_next_input_tokens']], 'post_summary_counts_changed')
    attempted_actor_ids = [c['id'] for c in usage if c['role'] == 'agent']
    require([s['next_call_id'] for s in signals if s['model_attempted']] == attempted_actor_ids,
            'actor_signal_attempts_changed')
    terminal_by_id = {c['id']: c for c in terminal}
    for signal in signals:
        if signal['model_attempted']:
            row = terminal_by_id.get(signal['next_call_id'])
            require(signal['terminal_usage_recorded'] == (row is not None) and
                    signal['usage_unknown'] == (row is None or row['status'] != 'ok'),
                    'actor_signal_terminal_status_changed')
    unused = [s for s in signals if not s['model_attempted']]
    require(len(unused) <= 1, 'multiple_unattempted_actor_calls')
    if unused:
        require(not usage or usage[-1]['status'] == 'ok', 'continuation_after_unknown_usage')
        signal = unused[0]
        working = project(base, proposal, checkpoint) if checkpoint is not None else base
        check_signal(signal, view_map[signal['next_call_id']], base, working, len(usage),
                     total['suffix_api_requests'], total['known_total_tokens'])
    by_role = {}
    for role in ('agent', 'focus'):
        rows = [c for c in usage if c['role'] == role]
        known = [c for c in rows if c['status'] == 'ok']
        by_role[role] = {'calls': len(rows), 'unknown_usage': len(rows) - len(known),
                         'input_tokens': sum(c['input_tokens'] for c in known),
                         'output_tokens': sum(c['output_tokens'] for c in known)}
    require(summary['usage_by_role'] == by_role, 'role_totals_changed')
    return {**total, 'model_calls': len(usage), 'usage_by_role': by_role,
            'request_checks': checks, 'checkpoint_installed': checkpoint is not None,
            'checkpoint_opportunity': control['status'] if control else None,
            'checkpoint_controls': controls,
            'input_count_records': len(counts), 'invocation_status_counts': dict(Counter(r['status'] for r in receipts)),
            'additional_model_calls': 0, 'additional_API_requests': 0, 'additional_tokenizer_calls': 0,
            'summary_semantics_verified': False}

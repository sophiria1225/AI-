"""Restore old history on recorded checkpoint trajectories without executing it.

The two inputs share the realized actions, outputs, metadata transport, budget
notices and request parameters. This diagnoses input replacement only; it does
not predict behavior, quality, cache use or budget feasibility of another run.
"""
from copy import deepcopy
import hashlib
import json

from budget_observation import notification
from inline_checkpoint_history import InlineCheckpoint
from inline_checkpoint_protocol import split_inline_response
from public_display import CODE_TOOLS
from receipt_reasoning_history import digest, require
from required_inline_checkpoint_history import RequiredInlineCheckpoint
from single_checkpoint_history import candidate, project

DISPLAYS = ('actual', 'restored_old_history')
PHASES = ('P118', 'P119', 'P120')


def prepared_views(conversation, config, usage, events, spans, signals,
                   history_views, controls, checkpoint, requests, responses, phase):
    require(phase in PHASES, 'fixed_closed_checkpoint_phase_required')
    policy = config['checkpoint_policy']
    require(policy in (('full', 'single_checkpoint') if phase == 'P118'
                       else ('single_checkpoint', 'inline_checkpoint')), 'fixed_checkpoint_policy_required')
    ids = [c['id'] for c in usage]
    require(len(ids) == len(set(ids)) <= 80 and len(events) <= 4000,
            'bounded_unique_attempts_required')
    require(set(requests) == set(responses) == set(ids), 'all_attempt_slots_required')
    ranks = {cid: i for i, cid in enumerate(ids)}
    order = [ranks.get(e['call'], -1) for e in events]
    require(-1 not in order and order == sorted(order), 'chronological_records_required')
    require(len({e['span_id'] for e in events}) == len(events)
            and {e['span_id'] for e in events} == set(spans), 'complete_saved_spans_required')
    signal_map = {s['next_call_id']: s for s in signals}
    view_map = {v['next_agent_call_id']: v for v in history_views}
    actor_ids = [c['id'] for c in usage if c['role'] == 'agent']
    require(len(signal_map) == len(signals) and len(view_map) == len(history_views)
            and set(signal_map) == set(view_map) and set(actor_ids) <= set(view_map),
            'unique_actor_projection_records_required')
    inline = (RequiredInlineCheckpoint() if phase == 'P120' else InlineCheckpoint()) \
        if policy == 'inline_checkpoint' else None
    rows = []
    separate_started = False
    for index, call in enumerate(usage):
        cid = call['id']
        request, response = requests[cid], responses[cid]
        base, _ = conversation.for_model(config['observation_page_characters'])
        active, offered = False, None
        if call['role'] == 'focus':
            require(policy == 'single_checkpoint' and not separate_started,
                    'one_separate_summary_attempt_required')
            separate_started = True
            proposal = candidate(base)
            require(proposal is not None, 'summary_closed_prefix_required')
            supplied = restored = proposal['summary_messages']
            tools = []
        else:
            require(call['role'] == 'agent', 'known_role_required')
            signal, view = signal_map[cid], view_map[cid]
            require(view['original_history_sha256'] == digest(base), 'original_archive_changed')
            if inline is not None:
                if inline.opportunity_used and inline.decision is None:
                    decisions = [c for c in controls if c['status'] == 'checkpoint_decided'
                                 and c['after_model_calls'] == index]
                    require(len(decisions) == 1, 'one_recorded_installation_decision_required')
                    event = decisions[0]
                    decision = inline.decide(event['ordinary_input_tokens'], event['compacted_input_tokens'])
                    require(all(event[k] == v for k, v in decision.items()), 'recorded_decision_changed')
                working = inline.view(base)
                tools = CODE_TOOLS
                if not inline.opportunity_used:
                    triggers = [c for c in controls if c['after_model_calls'] == index
                                and c['status'] in ('below_trigger_or_recent_only', 'inline_offered')]
                    require(len(triggers) == 1, 'one_recorded_inline_trigger_required')
                    offered = inline.begin(base, CODE_TOOLS, triggers[0]['trigger_input_tokens'])
                    require(bool(offered) == (triggers[0]['status'] == 'inline_offered'),
                            'recorded_inline_opportunity_changed')
                    if offered is not None:
                        working, tools = offered['messages'], offered['tools']
                active = bool(inline.decision and inline.decision['accepted'])
                ordinary = working
                if active:
                    require(inline.after is not None and base[:len(inline.after)] == inline.after,
                            'immutable_offered_turn_prefix_required')
                    # Preserve metadata removal in both views. Only the older
                    # history replacement is removed from this diagnostic view.
                    ordinary = deepcopy(inline.views['ordinary']) + deepcopy(base[len(inline.after):])
                require(view['inline_offered'] == bool(offered) and view['tools_sha256'] == digest(tools),
                        'recorded_offer_or_schema_changed')
            else:
                active = view['checkpoint_used']
                require(type(active) is bool and (not active or policy == 'single_checkpoint'
                        and separate_started and checkpoint is not None), 'installed_checkpoint_source_required')
                working = project(base, checkpoint['proposal'], checkpoint['checkpoint']) if active else base
                ordinary, tools = base, CODE_TOOLS
            require(view['checkpoint_used'] == active and view['working_history_sha256'] == digest(working),
                    'actual_history_projection_changed')
            supplied, visible = notification(working, signal['measured_state'], 'not_exposed')
            restored, restored_visible = notification(ordinary, signal['measured_state'], 'not_exposed')
            require(visible == restored_visible == signal['visible_state']
                    and digest(supplied) == signal['model_messages_sha256'], 'fixed_actual_budget_notice_required')
        if request is not None:
            require(request['messages'] == supplied and request.get('tools', []) == tools,
                    'recorded_request_or_schema_changed')
        for display, messages in zip(DISPLAYS, (supplied, restored), strict=True):
            payload = deepcopy(request)
            if payload is not None:
                payload['messages'] = deepcopy(messages)
                untouched = deepcopy(payload)
                untouched['messages'] = request['messages']
                require(untouched == request, 'non_message_parameters_must_stay_identical')
            rows.append({'call_id': cid, 'role': call['role'], 'display': display,
                'checkpoint_active': active, 'actual_usage_status': call['status'],
                'actual_request_available': request is not None,
                'actual_measured_input_tokens': call.get('input_tokens') if call['status'] == 'ok' else None,
                'actual_measured_output_tokens': call.get('output_tokens') if call['status'] == 'ok' else None,
                'actual_output_cap': call.get('output_cap'), 'payload': payload})
        selected = [e for e in events if e['call'] == cid]
        if call['status'] == 'ok':
            require(request is not None and response is not None, 'known_request_and_response_required')
            if call['role'] == 'focus':
                require(not selected, 'summary_must_not_execute')
            else:
                outer = [spans[e['span_id']] for e in selected if e['stage'] == 'model_tool']
                if outer:
                    conversation.append(response['message'], outer)
                    if offered is not None:
                        split = split_inline_response(response['message'], offered=True,
                            finish_reason=response['done_reason'], usage_known=True)
                        after, _ = conversation.for_model(config['observation_page_characters'])
                        inline.close(after, split)
                else:
                    require(index == len(usage) - 1 and not selected,
                            'known_unexecuted_response_must_be_terminal')
        else:
            require(index == len(usage) - 1 and not selected
                    and call.get('input_tokens') is None and call.get('output_tokens') is None,
                    'unknown_usage_cannot_gain_execution_or_cost')
    return rows


def collect_renderings(directory, views):
    groups = {}
    for view in views:
        groups.setdefault(view['call_id'], []).append(view)
    rows = []
    for group in groups.values():
        require([v['display'] for v in group] == list(DISPLAYS), 'both_ordered_displays_required')
        rendered = {}
        for view in group:
            if not view['actual_request_available']:
                continue
            path = directory / (view['case_id'] + '_rendered_private.json')
            require(path.stat().st_size <= 16777216, 'bounded_rendered_input_required')
            value = json.loads(path.read_text())
            require(value['id'] == view['case_id'] and value['input_tokens'] == len(value['tokens'])
                    and value['media_files'] == 0, 'valid_rendered_input_required')
            rendered[view['display']] = value
        require(len(rendered) in (0, 2), 'complete_display_pair_required')
        if not rendered:
            rows += [{**view, 'status': 'missing_recorded_request', 'input_tokens': None,
                      'restoration_input_difference': None, 'actual_unknown_usage_not_imputed': True}
                     for view in group]
            continue
        actual, restored = (rendered[d] for d in DISPLAYS)
        measured = group[0]['actual_measured_input_tokens']
        require(measured is None or actual['input_tokens'] == measured, 'actual_measured_count_differs')
        require(actual['session_controls'] == restored['session_controls']
                and actual['parsed_non_message_parameters'] == restored['parsed_non_message_parameters'],
                'only_history_replacement_may_change')
        if not group[0]['checkpoint_active']:
            require(actual['tokens'] == restored['tokens'], 'inactive_replacement_must_not_change_input')
        difference = restored['input_tokens'] - actual['input_tokens']
        for view in group:
            value = rendered[view['display']]
            path = directory / (view['case_id'] + '_rendered_private.json')
            cap = view['actual_output_cap']
            rows.append({**view, 'status': 'counted', 'input_tokens': value['input_tokens'],
                'restoration_input_difference': difference,
                'input_and_actual_output_cap_fit_context': value['input_tokens'] + cap <= 65536
                    if type(cap) is int else None,
                'prompt_sha256': hashlib.sha256(value['prompt'].encode()).hexdigest(),
                'token_sequence_sha256': digest(value['tokens']),
                'rendered_private_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'actual_unknown_usage_not_imputed': view['actual_usage_status'] != 'ok'})
    return rows


def summarize_cell(source, rows):
    selected = [r for r in rows if r['display'] == 'actual']
    counted = [r for r in selected if r['status'] == 'counted']
    complete = (source['record_status'] in ('evaluated', 'unevaluated')
                and len(counted) == len(selected) == source['model_calls'])
    known = complete and source['unknown_usage_calls'] == 0
    direct = sum(r['restoration_input_difference'] for r in counted) if complete else None
    focus = source.get('usage_by_role', {}).get('focus')
    focus_cost = (focus['input_tokens'] + focus['output_tokens']
                  if focus and focus['unknown_usage'] == 0 else None)
    cumulative = 0
    timeline = []
    if complete:
        for row in selected:
            cumulative += row['restoration_input_difference']
            if row['checkpoint_active']:
                timeline.append({'call_id': row['call_id'], 'actual_usage_status': row['actual_usage_status'],
                    'input_difference': row['restoration_input_difference'], 'cumulative_input_difference': cumulative,
                    'minus_separate_summary_cost': cumulative - focus_cost
                        if focus_cost is not None and source['checkpoint_policy'] == 'single_checkpoint' else None})
    return {'run_id': source['run_id'], 'task_id': source['task_id'],
        'checkpoint_policy': source['checkpoint_policy'], 'record_status': source['record_status'],
        'actual_success': source['success'], 'actual_model_attempts': source.get('model_calls'),
        'actual_known_total_tokens': source.get('known_total_tokens'),
        'actual_unknown_usage_calls': source.get('unknown_usage_calls'),
        'all_attempted_inputs_counted': complete, 'counted_actual_inputs': len(counted),
        'direct_input_difference_on_realized_path': direct, 'separate_summary_exact_tokens': focus_cost,
        'direct_input_difference_minus_separate_summary_cost': direct - focus_cost
            if direct is not None and focus_cost is not None and source['checkpoint_policy'] == 'single_checkpoint' else None,
        'hypothetical_restore_cost_on_same_outputs': source['known_total_tokens'] + direct if known else None,
        'hypothetical_restore_cost_exceeds_task_token_budget': source['known_total_tokens'] + direct > 450000 if known else None,
        'any_restored_context_overflow': any(r.get('input_and_actual_output_cap_fit_context') is False
            for r in rows if r['display'] == 'restored_old_history'),
        'active_replacement_input_timeline': timeline,
        'inline_metadata_output_cost_separately_estimated': False,
        'actual_unknown_usage_not_imputed': source.get('unknown_usage_calls') != 0,
        'all_original_budget_notices_and_non_message_parameters_held_fixed': True,
        'counterfactual_trajectory_or_quality_claim': False, 'whole_task_savings_claim': False}

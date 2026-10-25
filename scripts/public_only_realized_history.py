"""Reconstruct full archives behind P114 inputs without executing saved actions.

Local input differences hold the realized trajectory and budget notice fixed.
They are not causal predictions of the outputs or cost under another policy.
"""
from copy import deepcopy
import hashlib
import json

from budget_observation import notification
from receipt_reasoning_history import digest, execution_evidence, project as receipt_project, require
from public_only_reasoning_history import project as public_project
from whole_task_receipt_history import initial_conversation

POLICIES = ('full', 'recent', 'execution_gated', 'public_only')


def project(messages, evidence, policy):
    require(policy in POLICIES, 'fixed_four_display_policies_required')
    return (public_project if policy == 'public_only' else receipt_project)(messages, evidence, policy)


def prepared_views(original, public_task, config, usage, events, spans, signals,
                   execution_records, history_views, requests, responses):
    actual_policy = config['reasoning_display_policy']
    require(actual_policy == 'public_only', 'recorded_P114_public_only_policy_required')
    ids = [u['id'] for u in usage]
    require(len(ids) <= 80 and len(ids) == len(set(ids)) and len(events) <= 4000,
            'bounded_unique_saved_calls_required')
    ranks = {cid: i for i, cid in enumerate(ids)}
    order = [ranks.get(e['call'], -1) for e in events]
    require(-1 not in order and order == sorted(order), 'chronological_records_required')
    require(len({e['span_id'] for e in events}) == len(events)
            and {e['span_id'] for e in events} == set(spans), 'complete_saved_span_mapping')
    attempts = [s for s in signals if s['model_attempted']]
    require([s['next_call_id'] for s in attempts] == ids
            and set(requests) == set(responses) == set(ids), 'all_attempt_slots_required')
    require(len(history_views) == len(signals)
            and len(signals)-len(usage) in (0, 1), 'all_actual_projection_records_required')
    conversation = initial_conversation(original, public_task)
    evidence = []
    masks = {p: set() for p in POLICIES}
    rows = []
    for index, (call, signal) in enumerate(zip(usage, attempts, strict=True)):
        cid = call['id']
        request = requests[cid]
        canonical, _ = conversation.for_model(config['observation_page_characters'])
        for policy in POLICIES:
            projected, metadata = project(canonical, evidence, policy)
            removed = set(metadata['removed_reasoning_turns'])
            metadata['redisplayed_reasoning_turns'] = sorted(masks[policy]-removed)
            masks[policy] = removed
            supplied, visible = notification(projected, signal['measured_state'], 'not_exposed')
            if policy == actual_policy:
                require(history_views[index]['next_call_id'] == cid
                        and metadata == history_views[index]['projection'], 'actual_projection_changed')
                require(visible == signal['visible_state']
                        and digest(projected) == signal['base_messages_sha256']
                        and digest(supplied) == signal['model_messages_sha256'],
                        'actual_budget_or_input_changed')
                if request is not None:
                    require(request['messages'] == supplied, 'actual_request_messages_changed')
            payload = None
            if request is not None:
                payload = deepcopy(request)
                payload['messages'] = supplied
                other = deepcopy(payload)
                other['messages'] = request['messages']
                require(other == request, 'non_message_request_parameters_changed')
            rows.append(dict(call_id=cid, policy=policy, actual_policy=actual_policy,
                actual_usage_status=call['status'], actual_request_available=request is not None,
                actual_measured_input_tokens=call.get('input_tokens') if call['status'] == 'ok' else None,
                actual_measured_output_tokens=call.get('output_tokens') if call['status'] == 'ok' else None,
                actual_measured_cached_input_tokens=call.get('cached_input_tokens') if call['status'] == 'ok' else None,
                projection=metadata, payload=payload))
        selected = [e for e in events if e['call'] == cid]
        outer = [spans[e['span_id']] for e in selected if e['stage'] == 'model_tool']
        if call['status'] == 'ok':
            require(request is not None and responses[cid] is not None, 'known_response_records_required')
            if outer:
                conversation.append(responses[cid]['message'], outer)
                entry = execution_evidence(selected, {e['span_id']: spans[e['span_id']] for e in selected},
                                           pending_reads=0)
                require(len(execution_records) > len(evidence), 'execution_record_missing')
                recorded = execution_records[len(evidence)]
                require(recorded['call_id'] == cid and recorded['evidence'] == entry,
                        'trusted_execution_record_changed')
                evidence.append(entry)
            else:
                require(index == len(usage)-1 and not selected, 'unexecuted_known_response_must_be_terminal')
        else:
            require(index == len(usage)-1 and not selected, 'unknown_response_executed_or_retried')
            require(call.get('input_tokens') is None and call.get('output_tokens') is None,
                    'unknown_usage_must_stay_unknown')
    require(len(evidence) == len(execution_records), 'extra_execution_records')
    if len(history_views) > len(usage):
        require(not signals[-1]['model_attempted'], 'terminal_view_cannot_be_an_unrecorded_attempt')
    return rows, evidence


def collect_renderings(directory, views):
    """Validate against the actual policy's count, which need not be full."""
    groups = {}
    for view in views:
        groups.setdefault(view['call_id'], []).append(view)
    rows = []
    previous = {}
    for cid, group in groups.items():
        require([v['policy'] for v in group] == list(POLICIES), 'four_ordered_views_required')
        rendered = {}
        for view in group:
            if not view['actual_request_available']:
                continue
            path = directory/(view['case_id']+'_rendered_private.json')
            require(path.stat().st_size <= 16777216, 'bounded_rendered_record')
            value = json.loads(path.read_text())
            require(value['id'] == view['case_id'] and value['input_tokens'] == len(value['tokens'])
                    and value['media_files'] == 0, 'rendered_input_shape')
            rendered[view['policy']] = value
        require(len(rendered) in (0, 4), 'complete_local_policy_quadruplet_required')
        if not rendered:
            for view in group:
                rows.append(dict(**view, status='missing_recorded_request', input_tokens=None,
                    delta_from_full=None, delta_from_actual=None, actual_unknown_usage_not_imputed=True,
                    input_and_max_output_fit_context=None))
            previous.clear()  # Never claim adjacency across a missing request.
            continue
        full = rendered['full']
        actual = rendered[group[0]['actual_policy']]
        measured = group[0]['actual_measured_input_tokens']
        require(measured is None or actual['input_tokens'] == measured,
                'actual_measured_input_count_differs')
        for view in group:
            policy = view['policy']
            value = rendered[policy]
            require(value['session_controls'] == actual['session_controls']
                    and value['parsed_non_message_parameters'] == actual['parsed_non_message_parameters'],
                    'only_history_may_change_decoder_controls')
            old = previous.get(policy)
            common = 0
            if old is not None:
                for a, b in zip(old, value['tokens']):
                    if a != b:
                        break
                    common += 1
            previous[policy] = value['tokens']
            path = directory/(view['case_id']+'_rendered_private.json')
            rows.append(dict(**view, status='counted', input_tokens=value['input_tokens'],
                input_and_max_output_fit_context=value['input_tokens']+4096 <= 65536,
                context_fit_is_not_total_budget_admission=True,
                delta_from_full=value['input_tokens']-full['input_tokens'],
                delta_from_actual=value['input_tokens']-actual['input_tokens'],
                prompt_sha256=hashlib.sha256(value['prompt'].encode()).hexdigest(),
                token_sequence_sha256=digest(value['tokens']),
                rendered_private_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                adjacent_input_common_prefix_tokens=common if old is not None else None,
                common_prefix_is_not_measured_cache_usage=True,
                actual_unknown_usage_not_imputed=view['actual_usage_status'] != 'ok'))
    return rows


def summarize_cell(source, rows):
    actual_policy = source['reasoning_display_policy']
    selected = [r for r in rows if r['policy'] == actual_policy]
    counted = [r for r in selected if r['status'] == 'counted']
    complete = (source['record_status'] in ('evaluated', 'unevaluated')
                and len(counted) == len(selected) == source['model_calls'])
    known = source.get('unknown_usage_calls') == 0 and complete
    omission = -sum(r['delta_from_full'] for r in counted) if complete else None
    return dict(run_id=source['run_id'], task_id=source['task_id'], actual_policy=actual_policy,
        record_status=source['record_status'], actual_success=source['success'],
        actual_model_attempts=source.get('model_calls'), actual_known_total_tokens=source.get('known_total_tokens'),
        actual_unknown_usage_calls=source.get('unknown_usage_calls'),
        actual_full_logical_tokens=source.get('known_total_tokens') if known else None,
        counted_actual_inputs=len(counted), all_attempted_inputs_counted=complete,
        actual_policy_input_omission_on_realized_path=omission,
        hypothetical_full_display_cost_on_same_outputs=(source['known_total_tokens']+omission) if known else None,
        hypothetical_cost_is_not_an_observed_full_policy_run=True,
        actual_unknown_usage_not_imputed=source.get('unknown_usage_calls') != 0,
        terminal_unattempted_projection_included_as_model_cost=False,
        hypothetical_context_limit=65536, hypothetical_output_reservation=4096,
        any_hypothetical_context_overflow=any(r.get('input_and_max_output_fit_context') is False for r in rows),
        hypothetical_inputs={p: dict(
            counted=sum(r['policy'] == p and r['status'] == 'counted' for r in rows),
            input_sum=sum(r['input_tokens'] for r in rows if r['policy'] == p and r['status'] == 'counted')
                if complete else None,
            delta_from_actual_sum=sum(r['delta_from_actual'] for r in rows if r['policy'] == p and r['status'] == 'counted')
                if complete else None) for p in POLICIES})


def accounting_decompositions(cells, historical_rows):
    """Use closed P111 full costs; no full policy was run on the P114 path."""
    result = []
    tasks = [c['task_id'] for c in cells]
    require(len(tasks) == len(set(tasks)) == 4 and len(historical_rows) == 12,
            'all_four_new_and_twelve_historical_conditions_required')
    require({r['task_id'] for r in historical_rows} == set(tasks), 'same_four_known_tasks_required')
    for actual in cells:
        require(actual['actual_policy'] == 'public_only', 'only_public_only_was_run_in_P114')
        choices = {r['reasoning_display_policy']: r for r in historical_rows if r['task_id'] == actual['task_id']}
        require(set(choices) == set(POLICIES[:3]) and len([r for r in historical_rows
                if r['task_id'] == actual['task_id']]) == 3, 'all_three_historical_policies_required')
        full = choices['full']
        full_cost = (full['known_total_tokens'] if full['record_status'] in ('evaluated', 'unevaluated')
                     and full['unknown_usage_calls'] == 0 else None)
        known = actual['actual_full_logical_tokens'] is not None and full_cost is not None
        delta = actual['actual_full_logical_tokens']-full_cost if known else None
        omission = actual['actual_policy_input_omission_on_realized_path']
        result.append(dict(task_id=actual['task_id'], actual_policy='public_only',
            actual_run_id=actual['run_id'], historical_full_run_id=full['run_id'],
            full_success=full['success'], candidate_success=actual['actual_success'],
            historical_full_unknown_usage_calls=full['unknown_usage_calls'],
            all_logical_usage_known=known, observed_cost_difference_from_full=delta,
            local_input_omission_on_candidate_path=omission,
            remainder_after_adding_back_local_omission=delta+omission if known and omission is not None else None,
            contemporaneous_comparison=False, remainder_is_not_a_causal_effect=True,
            quality_preservation_or_savings_claim=False))
    return result

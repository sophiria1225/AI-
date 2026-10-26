"""P130 derived rolling audit with trusted inventory boundary reconstruction.

No model, tokenizer, program, API, evaluator or semantic judge is invoked.
Recorded native counts are bound to reconstructed inputs. This proves neither
summary truthfulness nor preservation of task quality.
"""
from collections import Counter
from copy import deepcopy
import json
import math
from types import SimpleNamespace

from api_error_comparison import task_snapshot
from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission
from budget_observation import notification
from checkpoint_attempt_usage import attempt_usage
from fixed_budget_local_llama import payload_for as summary_payload
from inference_cache_control import cache_measurement
from inline_checkpoint_protocol import split_inline_response
from local_llama import parse_response
from native_data_compute import selected_receipts
from public_display import CODE_TOOLS
from receipt_reasoning_history import digest, require
from rolling_checkpoint_inference import AdmissionAwareRollingCheckpoint
from run_handoff_factors import read, sha, ROOT
from audit_whole_task_region_projection import equal, duration
from checkpoint_inventory_inference import boundary_descriptor
from checkpoint_inventory_runtime import encoded, validate_response, MAX_CAPTURES
from checkpoint_runtime_inventory import CheckpointInventory, digest as inventory_digest
import hashlib
from pathlib import Path
import re
from tool_choice_local_llama import payload_for as agent_payload


def expected_inventory_python():
    return read(ROOT / 'configs/python_export_image_v01.json')['expected_python']


class InventoryAudit:
    """Validate trusted capture observations and independently rebuild timing.

    Captured metadata is not recomputed by executing the saved Python source.
    The trust boundary is the fixed collector and its request/response binding.
    """
    def __init__(self, folder, config):
        self.folder, self.config = folder, config
        require(config['run_id'] == folder.name, 'inventory_execution_scope_changed')
        self.controller = CheckpointInventory(mode=config['checkpoint_inventory_policy'], execution_scope=folder.name)
        self.records = read(folder / 'checkpoint_inventory_capture_private.json')
        require(type(self.records) is list and len(self.records) <= MAX_CAPTURES,
                'bounded_inventory_capture_records_required')
        self.cursor, self.packets, self.boundaries, self.views = 0, [], [], []
        self.files = ['checkpoint_inventory_capture_private.json', 'checkpoint_inventory_events_private.json',
            'checkpoint_inventory_packets_private.json', 'checkpoint_inventory_boundaries_private.json',
            'checkpoint_inventory_inference_views.json']
        self.expected_python = expected_inventory_python()

    def capture(self, normalized, working, *, revision, after_model_calls, decision):
        require(self.cursor < len(self.records), 'accepted_checkpoint_missing_inventory_capture')
        boundary = boundary_descriptor(normalized, working, revision=revision,
            after_model_calls=after_model_calls, decision=decision)
        record = self.records[self.cursor]
        location = self.folder / 'checkpoint_inventory' / f'capture_{revision:03d}'
        request_bytes = (location / 'request_private.json').read_bytes()
        request = read(location / 'request_private.json')
        require(type(request) is dict and set(request) == {'op', 'protocol', 'request_id',
            'execution_scope_sha256', 'checkpoint_revision', 'program_index', 'source_boundary_sha256'},
            'inventory_request_shape_changed')
        require(request_bytes == encoded(request), 'inventory_request_wire_bytes_changed')
        require(type(request['request_id']) is str and len(request['request_id']) == 32
            and all(c in '0123456789abcdef' for c in request['request_id']), 'inventory_request_identity_required')
        prefix_programs = []
        for path in (self.folder / 'programs').glob('*'):
            require(path.is_dir() and re.fullmatch(r'call_[0-9]{3}_[0-9]{2}', path.name),
                    'inventory_program_boundary_shape_changed')
            if int(path.name.split('_')[1]) <= after_model_calls:
                prefix_programs.append(path.name)
        expected_request = dict(op='checkpoint_inventory', protocol='checkpoint_inventory_capture_v1',
            request_id=request['request_id'], execution_scope_sha256=self.controller.scope_sha256,
            checkpoint_revision=revision, program_index=len(prefix_programs),
            source_boundary_sha256=inventory_digest(boundary))
        equal(request, expected_request, 'inventory_capture_not_bound_to_current_closed_program_prefix')
        wire = (location / 'wire_private.jsonl').read_bytes()
        response_bytes = (location / 'response_private.json').read_bytes()
        response = read(location / 'response_private.json')
        require(wire == response_bytes == encoded(response), 'inventory_response_wire_not_single_exact_packet')
        snapshot = validate_response(response, request, request_bytes, self.expected_python)
        result = read(location / 'result_private.json')
        expected_result = dict(status='ok', checkpoint_revision=revision, program_index=len(prefix_programs),
            request_sha256=hashlib.sha256(request_bytes).hexdigest(), response_sha256=hashlib.sha256(wire).hexdigest(),
            request_bytes=len(request_bytes), response_bytes=len(wire), request_sent=True,
            inventory=snapshot, execution_scope_sha256=self.controller.scope_sha256,
            source_boundary_sha256=inventory_digest(boundary), ordinary_program_count_unchanged=True,
            response_complete=True, new_model_calls=0, new_API_requests=0, inventory_sha256=inventory_digest(snapshot),
            wall_seconds=duration(result['wall_seconds'], 'invalid_inventory_capture_time'), session_usable=True)
        equal(result, expected_result, 'inventory_capture_result_changed')
        host_wall = duration(record['host_wall_seconds'], 'invalid_inventory_host_time')
        require(result['wall_seconds'] <= host_wall, 'inventory_capture_time_outside_host_control')
        equal(record, dict(expected_result, host_wall_seconds=host_wall), 'inventory_capture_ledger_changed')
        self.cursor += 1
        packet = self.controller.prepare(snapshot, accepted=True, revision=revision,
            program_index=len(prefix_programs), source_boundary_sha256=inventory_digest(boundary))
        self.boundaries.append(boundary); self.packets.append(packet)
        self.files.extend(str(p.relative_to(self.folder)) for p in sorted(location.iterdir()) if p.is_file())

    def actor_view(self, cid, base, ordinary, working, supplied, revision, pending, signal):
        self.views.append(dict(next_agent_call_id=cid, checkpoint_revision=revision,
            normalized_history_sha256=digest(base), checkpoint_view_sha256=digest(ordinary),
            inventory_view_sha256=digest(working), supplied_messages_sha256=digest(supplied),
            packet_sha256=pending['packet_sha256'] if pending else None,
            inventory_prepared=pending is not None,
            inventory_included=pending is not None and self.controller.mode == 'checkpoint_inventory',
            **{k: signal[k] for k in ('model_attempted', 'terminal_usage_recorded', 'usage_unknown')},
            raw_archive_modified=False, focus_request_modified=False))

    def finish(self, summary):
        require(self.cursor == len(self.records), 'unreplayed_or_unaccepted_inventory_capture')
        actual = {p.name for p in (self.folder / 'checkpoint_inventory').glob('*')}
        require(actual == {f'capture_{i:03d}' for i in range(1, self.cursor + 1)},
                'extra_or_missing_inventory_capture_directory')
        for filename, expected in (
            ('checkpoint_inventory_events_private.json', self.controller.events),
            ('checkpoint_inventory_packets_private.json', self.packets),
            ('checkpoint_inventory_boundaries_private.json', self.boundaries),
            ('checkpoint_inventory_inference_views.json', self.views)):
            equal(read(self.folder / filename), expected, 'inventory_timeline_or_view_changed')
        wall = sum(r['host_wall_seconds'] for r in self.records)
        require(wall <= summary['wall_seconds'], 'inventory_control_time_outside_work_clock')
        capture = dict(captures=len(self.records), successful_captures=len(self.records),
            capture_wall_seconds=wall, known_request_bytes=sum(r['request_bytes'] for r in self.records),
            known_response_bytes=sum(r['response_bytes'] for r in self.records),
            unknown_capture_replies=0,
            capture_accounting_complete=True, contract_failed=False, records_sha256=inventory_digest(self.records),
            environment_API_requests=0, model_calls=0, generated_programs_executed=0,
            ordinary_program_count_unchanged=True, control_wall_included_in_work_wall=True,
            values_disclosed=False, scalar_lengths_disclosed=False,
            trusted_engine_integrity_assumed=True, hostile_python_security_sandbox=False)
        dispatched = [v for v in self.views if v['model_attempted']]
        exposed = [v for v in dispatched if v['inventory_included']]
        expected = dict(self.controller.summary(), live_worker_connected=True, capture=capture,
            contract_failed=False, counted_actor_views=len(self.views), dispatched_actor_views=len(dispatched),
            actual_inventory_exposures=len(exposed), actual_exposed_packet_sha256=[v['packet_sha256'] for v in exposed],
            views_sha256=inventory_digest(self.views), packets_sha256=inventory_digest(self.packets),
            boundaries_sha256=inventory_digest(self.boundaries), raw_archive_unchanged=True,
            focus_requests_unchanged=True, all_model_roles_and_inventory_input_share_budget=True,
            disclosure_activity_requires_actual_dispatch=True)
        equal(summary['checkpoint_inventory'], expected, 'inventory_summary_not_reconstructed')
        require(summary['checkpoint_inventory_summary_error_type'] is None,
                'inventory_incomplete_summary_accounting_unknown')
        return dict(inventory_runtime=expected, inventory_notice_actor_calls=len(exposed),
            inventory_captures=len(self.records), inventory_contract_failed=False, inventory_accounting_complete=True,
            inventory_capture_wall_seconds=wall, inventory_request_bytes=capture['known_request_bytes'],
            inventory_response_bytes=capture['known_response_bytes'],
            inventory_capture_metadata_recomputed_from_program_values=False,
            inventory_request_boundary_and_disclosure_reconstructed=True,
            inventory_audit_hashes={name: sha(self.folder / name) for name in self.files})


class TraceStopped(Exception):
    def __init__(self, exception_type):
        self.exception_type = exception_type


def audit_trace(folder, config, conversation):
    folder = Path(folder)
    require(config['checkpoint_policy'] == 'rolling_separate'
        and config['projection_policy'] == 'explicit_joined_fields'
        and config['output_grounding_policy'] == 'feedback', 'fixed_P130_shared_runtime_required')
    inventory = InventoryAudit(folder, config)
    mode = 'inline' if config['checkpoint_policy'] == 'rolling_inline' else 'separate'
    require(config.get('rolling_checkpoint_max_opportunities') == 3
            and config.get('rolling_min_fresh_turns') == 3
            and config.get('inline_checkpoint_requirement') == (
                'required_when_run_python' if mode == 'inline' else 'not_applicable'),
            'fixed_rolling_audit_limits_required')

    def saved(name, default=None):
        path = folder / (name + '.json')
        return read(path) if path.exists() else deepcopy(default)

    summary, usage, terminal, admissions, events, spans = [saved(n) for n in (
        'summary', 'usage', 'terminal_usage', 'admissions', 'events', 'spans')]
    admissions = admissions or []
    signals, views, controls, counts, offers, closed = [saved(n, []) for n in (
        'budget_observations', 'rolling_history_views', 'rolling_controls',
        'rolling_input_counts', 'rolling_offers_private', 'rolling_closed_private')]
    require(attempt_usage(SimpleNamespace(calls=terminal, admissions=admissions)) == usage,
            'shared_dispatch_accounting_changed')
    budgets, total = budget_before_calls(usage, events, 0, config)
    require(summary['model_calls'] == len(usage)
            and summary['known_total_tokens'] == total['known_total_tokens']
            and summary['unknown_usage_calls'] == total['unknown_usage_calls']
            and summary['api_requests'] == total['suffix_api_requests'], 'worker_accounting_changed')
    require(len(usage) <= config['max_calls']
            and total['known_total_tokens'] <= config['max_total_tokens']
            and total['suffix_api_requests'] <= config['max_api_requests'], 'shared_budget_exceeded')
    require(all(c['role'] in ('agent', 'focus') for c in usage)
            and (mode != 'inline' or all(c['role'] == 'agent' for c in usage)),
            'unplanned_model_role')
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
        require('inline_transport' not in event or (mode == 'inline' and event['stage'] == 'model_tool'),
                'unexpected_inline_transport')
    dispatches = [a for a in admissions if a.get('model_request_started')]
    require([a['next_call_id'] for a in dispatches] == [c['id'] for c in usage],
            'all_shared_attempts_required')
    signal_map = {s['next_call_id']: s for s in signals}
    view_map = {v['next_agent_call_id']: v for v in views}
    require(len(signal_map) == len(signals) and len(view_map) == len(views)
            and set(signal_map) == set(view_map), 'unique_actor_signal_and_view_required')
    require([s['next_call_id'] for s in signals if s['model_attempted']] ==
            [c['id'] for c in usage if c['role'] == 'agent'], 'actor_signal_attempts_changed')
    control = AdmissionAwareRollingCheckpoint(mode)
    expected_controls, expected_offers, expected_closed, checks = [], [], [], []
    prior, index, count_index = {}, 0, 0
    last_wall = config['max_wall_seconds']
    seen_signals = []

    def api_before():
        prefix = {c['id'] for c in usage[:index]}
        return sum(e['api_request_sent'] for e in events if e['call'] in prefix)

    def supplied(base):
        return notification(base, task_snapshot(config, usage[:index], api_before(), 0),
                            'not_exposed')[0]

    def take_count(role, purpose, messages, tools):
        nonlocal count_index
        if count_index == len(counts) and index == len(usage) and 'wall_limit' in summary['stop_reason']:
            raise TraceStopped('BudgetStop')
        require(count_index < len(counts), 'expected_native_count_missing')
        count = counts[count_index]
        count_index += 1
        require(count['role'] == role and count['after_model_calls'] == index
                and count['purpose'] == purpose and count['messages_sha256'] == digest(messages)
                and count['tools_sha256'] == digest(tools), 'native_count_not_bound_to_exact_input')
        if count['status'] == 'failed':
            require(index == len(usage) and count_index == len(counts), 'failed_count_must_stop')
            raise TraceStopped(count['exception_type'])
        require(count['status'] == 'complete' and type(count['input_tokens']) is int
                and count['input_tokens'] > 0, 'positive_native_count_required')
        return count

    def resolve(base):
        if control.pending is None:
            return
        pending = control.pending
        require(pending['stage'] == 'closed' and pending.get('value') is not None,
                'rolling_turn_must_close_before_next_request')
        control._check(base)
        require(len(base) == control._bound_length, 'new_turn_before_resolution')
        a = take_count('agent', 'ordinary_next_input', supplied(pending['views']['ordinary']), CODE_TOOLS)
        b = take_count('agent', 'compacted_next_input', supplied(pending['views']['compacted']), CODE_TOOLS)
        decision = control.decide(a['input_tokens'], b['input_tokens'])
        expected_controls.append({'status': 'checkpoint_decided', 'after_model_calls': index, **decision})
        if decision.get('accepted') is True:
            inventory.capture(base, control.view(base), revision=control.revision,
                after_model_calls=index, decision=control.events[-1])

    def reject_unstarted(role):
        cid = f'call_{index + 1:03d}'
        pending = [a for a in admissions if a['next_call_id'] == cid]
        require(index == len(usage) and len(pending) <= 1
                and all(not a.get('model_request_started') and a['role'] == role for a in pending),
                'unattempted_admission_changed')
        if pending:
            if 'admitted' in pending[0]:
                validate_admission(pending[0], config['max_total_tokens'] - total['known_total_tokens'], config)
            return pending[0].get('exception_type', 'BudgetStop')
        require(summary['stop_reason'] in ('call_limit', 'wall_limit', 'user_stop'),
                'missing_unattempted_admission')
        return 'BudgetStop'

    def consume(role, messages, tools, offered=False):
        nonlocal index
        if index == len(usage):
            raise TraceStopped(reject_unstarted(role))
        call, admission, budget = usage[index], dispatches[index], budgets[index]
        cid = f'call_{index + 1:03d}'
        require(call['id'] == cid and call['role'] == role and admission['role'] == role,
                'sequential_shared_role_identity_required')
        choice = validate_admission(admission, budget['remaining_tokens_before'], config)
        require(choice['admitted'], 'generation_after_budget_rejection')
        cfg = {**config['model'], 'temperature': config['agent_temperature'] if role == 'agent'
               else config['draft_temperature'],
               'seed': config['seed'] + sum(c['role'] == role for c in usage[:index]),
               'num_predict': choice['selected_output_cap'], 'cache_prompt': index > 0}
        transport = agent_payload if role == 'agent' else summary_payload
        request_path, response_path = folder / cid / 'request.json', folder / cid / 'response.json'
        request = read(request_path) if request_path.exists() else None
        response = read(response_path) if response_path.exists() else None
        missing = call.get('error_kind') == 'dispatched_without_terminal_usage'
        require(request is None or request == transport(cfg, messages, tools), 'actual_rolling_request_differs')
        if missing:
            require(response is None and call['server_receipt_confirmed'] is False,
                    'missing_terminal_cannot_gain_receipt')
        else:
            require(request is not None and response is not None
                    and call['predicted_input_tokens'] == choice['input_tokens']
                    and call['output_cap'] == choice['selected_output_cap'], 'terminal_reservation_changed')
        selected_events = [e for e in events if e['call'] == cid]
        require(role == 'agent' or not selected_events, 'summary_cannot_execute_API')
        checks.append({'call_id': cid, 'role': role, 'status': call['status'],
            **{k: call.get(k) for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'finish_reason')},
            'request_sha256': sha(request_path) if request_path.exists() else None,
            'response_sha256': sha(response_path) if response_path.exists() else None,
            'API_requests': sum(e['api_request_sent'] for e in selected_events),
            'inline_offered': offered if role == 'agent' else False})
        if role == 'agent' and inventory.controller.pending is not None:
            inventory.controller.submitted(revision=control.revision, call_id=cid)
        index += 1
        if call['status'] != 'ok':
            require(index == len(usage) and not selected_events and all(call[k] is None and
                (response is None or response[k] is None) for k in ('input_tokens', 'output_tokens')),
                'unknown_usage_executed_or_imputed')
            raise TraceStopped(admission['exception_type'])
        parsed = parse_response(read(folder / cid / 'raw_response.json'))
        require(all(parsed[k] == response[k] for k in parsed), 'raw_terminal_normalization_changed')
        require(all(call.get(k) == response.get(k) for k in (
            'input_tokens', 'output_tokens', 'cached_input_tokens'))
            and call['finish_reason'] == response['done_reason'], 'terminal_usage_changed')
        require(response['input_tokens'] == choice['input_tokens']
                and response['output_tokens'] <= choice['selected_output_cap'], 'terminal_exceeded_admission')
        if index == 1:
            cold = cache_measurement('cold_1', response, response['input_tokens'])
            require(role == 'agent' and signal_map[cid].get('first_input_measurement') == cold,
                    'first_cache_measurement_changed')
            require(cold['state_confirmed'] or (index == len(usage) and not selected_events),
                    'execution_after_non_cold_first_request')
        return call, response, selected_events

    while True:
        if index and usage[index-1]['status'] != 'ok':
            break
        cid = f'call_{index+1:03d}'
        if cid not in signal_map and not any(c['after_model_calls'] == index for c in counts[count_index:]):
            break
        base, _ = conversation.for_model(config['observation_page_characters'])
        offered = None
        try:
            resolve(base)
            if control.opportunities < control.max_opportunities:
                working = control.view(base)
                count = take_count('agent', 'trigger', supplied(working), CODE_TOOLS)
                offered = control.begin(base, count['input_tokens'], CODE_TOOLS)
                expected_controls.append({'status': 'checkpoint_offered' if offered else 'below_trigger_or_not_eligible',
                    'after_model_calls': index, 'trigger_input_tokens': count['input_tokens'],
                    'source_archive_sha256': digest(base), 'visible_history_sha256': digest(working),
                    'opportunities': control.opportunities, 'semantics_verified': False})
                if offered is not None:
                    expected_offers.append({'after_model_calls': index, 'offer': deepcopy(offered)})
            if offered is not None and mode == 'separate':
                before = index
                event = {'status': 'separate_summary_started', 'opportunity_index': offered['opportunity_index'],
                    'after_model_calls': index, 'model_attempted': False, 'summary_calls': 0,
                    'summary_known_tokens': 0, 'semantics_verified': False}
                position = len(expected_controls)
                expected_controls.append(event)
                try:
                    count = take_count('focus', 'separate_summary_input', offered['summary_messages'], [])
                    # The control log stores the counter result, without its envelope.
                    result = {k: v for k, v in count.items() if k not in (
                        'role', 'purpose', 'after_model_calls', 'messages_sha256', 'tools_sha256', 'status')}
                    reserve = count['input_tokens'] + offered['trigger_input_tokens'] + 2 * config['max_output_tokens']
                    event.update(summary_input_count=result, screening_tokens_using_current_agent_input=reserve)
                    spent = sum(c['input_tokens']+c['output_tokens'] for c in usage[:index] if c['status']=='ok')
                    reason = ('insufficient_shared_call_budget' if index + 2 > config['max_calls'] else
                              'insufficient_shared_token_budget' if spent + reserve > config['max_total_tokens'] else
                              'summary_context_limit' if count['input_tokens']+config['max_output_tokens'] > config['model']['num_ctx'] else None)
                    if reason:
                        event.update(status='separate_summary_not_dispatched',
                                     decision=control.skip_unstarted_summary(base, reason))
                    else:
                        call, response, _ = consume('focus', offered['summary_messages'], [])
                        projected = control.close_separate(base, response['message'], response['done_reason'], usage_known=True)
                        expected_closed.append({'mode': 'separate', 'call_id': call['id'],
                            'opportunity_index': offered['opportunity_index'], 'source_archive_sha256': digest(base),
                            'ordinary_sha256': projected['ordinary_sha256'], 'compacted_sha256': projected['compacted_sha256']})
                        event['status'] = 'separate_summary_closed'
                        resolve(base)
                except TraceStopped as error:
                    event.update(status='separate_summary_aborted', exception_type=error.exception_type)
                    raise
                finally:
                    relevant = usage[before:index]
                    missing = sum(c.get('terminal_usage_recorded') is False for c in relevant)
                    require(position < len(controls), 'summary_control_record_missing')
                    wall = controls[position].get('control_wall_seconds')
                    require(type(wall) in (int, float) and math.isfinite(wall) and
                            0 <= wall <= summary['wall_seconds'], 'invalid_summary_control_time')
                    event.update(summary_calls=len(relevant)-missing,
                        summary_known_tokens=sum(c['input_tokens']+c['output_tokens'] for c in relevant if c['status']=='ok'),
                        model_attempted=bool(relevant), dispatched_without_terminal_usage=missing,
                        unknown_usage_calls=sum(c['status']!='ok' for c in relevant), control_wall_seconds=wall)
            inline = offered is not None and mode == 'inline'
            ordinary_working, tools = (offered['messages'], offered['tools']) if inline else (control.view(base), CODE_TOOLS)
            pending_inventory = deepcopy(inventory.controller.pending)
            working = inventory.controller.view(ordinary_working, revision=control.revision, role='agent')
            cid = f'call_{index+1:03d}'
            signal = signal_map.get(cid)
            require(signal is not None, 'missing_actor_signal')
            seen_signals.append(cid)
            state = signal['measured_state']
            expected_state = task_snapshot(config, usage[:index], api_before(), 0)
            wall = state['remaining']['wall_seconds_at_snapshot']
            expected_state['remaining']['wall_seconds_at_snapshot'] = wall
            require(state == expected_state and 0 <= wall <= last_wall, 'actor_shared_budget_notice_changed')
            last_wall = wall
            messages, visible = notification(working, state, 'not_exposed')
            inventory.actor_view(cid, base, ordinary_working, working, messages, control.revision,
                pending_inventory, signal)
            require(signal['visible_state'] == visible and signal['time_visibility'] == 'not_exposed'
                and signal['model_messages_sha256'] == digest(messages)
                and signal['model_tools_sha256'] == digest(tools)
                and signal['cache_prompt'] == (index > 0), 'actor_notice_or_schema_changed')
            require(view_map[cid] == {'next_agent_call_id': cid,
                'original_history_sha256': digest(base), 'working_history_sha256': digest(working),
                'tools_sha256': digest(tools), 'inline_offered': inline,
                'checkpoint_revision': control.revision, 'checkpoint_used': control.checkpoint is not None,
                'archive_deleted': False, 'semantics_verified': False}, 'rolling_projection_changed')
            if not signal['model_attempted']:
                reject_unstarted('agent')
                break
            call, response, selected_events = consume('agent', messages, tools, inline)
        except TraceStopped:
            break
        outer_events = [e for e in selected_events if e['stage'] == 'model_tool']
        if outer_events:
            split = split_inline_response(response['message'], offered=inline,
                finish_reason=response['done_reason'], usage_known=True) if mode == 'inline' else None
            outer = [spans[e['span_id']] for e in outer_events]
            execution = split['execution_message'] if split else response['message']
            for i, event in enumerate(outer_events):
                binding = None if split is None else split['binding']
                if binding is not None:
                    expected_binding = {'version': 'inline_checkpoint_transport_v01',
                        'original_payload_sha256': split['original_payload_sha256'], **binding,
                        'status': split['status'], 'execution_success_verified': False, 'semantics_verified': False}
                    require(len(outer_events) == 1 and event.get('inline_transport') == expected_binding,
                            'inline_execution_binding_changed')
                else:
                    require('inline_transport' not in event, 'unexpected_inline_transport_binding')
                path = folder / 'programs' / f'{cid}_{i+1:02d}' / 'input_private.json'
                calls = execution.get('tool_calls') or []
                fn = calls[i]['function'] if calls else None
                needs_program = fn and fn['name'] == 'run_python' and 'status' in outer[i]['observation']
                require(not needs_program or path.exists(), 'submitted_program_source_missing')
                if path.exists():
                    args, payload = json.loads(fn['arguments']), read(path)
                    require(set(args) == {'code', 'span_ids'} and payload['code'] == args['code']
                        and payload['observations'] == selected_receipts(args['span_ids'], prior),
                        'submitted_program_or_receipt_selection_changed')
            conversation.append(response['message'], outer)
            if inline:
                after, _ = conversation.for_model(config['observation_page_characters'])
                projected = control.close_inline(after, split, usage_known=True)
                expected_closed.append({'mode': 'inline', 'call_id': cid,
                    'opportunity_index': offered['opportunity_index'], 'source_archive_sha256': digest(after),
                    'split': split, 'ordinary_sha256': projected['ordinary_sha256'],
                    'compacted_sha256': projected['compacted_sha256']})
                expected_controls.append({'status': 'inline_turn_closed', 'opportunity_index': offered['opportunity_index'],
                    'after_model_calls': index, 'split_status': split['status'],
                    'ordinary_sha256': projected['ordinary_sha256'], 'compacted_sha256': projected['compacted_sha256'],
                    'semantics_verified': False})
        else:
            require(index == len(usage) and not selected_events and summary['stop_reason'] in (
                'runtime_error', 'wall_limit', 'api_request_limit', 'user_stop', 'cleanup_error'),
                'known_response_without_execution_record')
        prior.update({e['span_id']: spans[e['span_id']] for e in selected_events})

    require(index == len(usage) and count_index == len(counts) and controls == expected_controls,
            'control_timeline_changed')
    require(offers == expected_offers and closed == expected_closed, 'private_checkpoint_state_changed')
    require(seen_signals == [s['next_call_id'] for s in signals], 'unreplayed_actor_signal')
    require(saved('conversation_private', conversation.messages()) == conversation.messages(), 'archive_replay_changed')
    terminals = {c['id']: c for c in terminal}
    for signal in signals:
        if signal['model_attempted']:
            call = terminals.get(signal['next_call_id'])
            require(signal['terminal_usage_recorded'] == (call is not None)
                and signal['usage_unknown'] == (call is None or call['status'] != 'ok'),
                'actor_signal_terminal_status_changed')
    known = [c for c in usage if c['status'] == 'ok']
    by_role = {role: {'calls': sum(c['role']==role for c in usage),
        'unknown_usage': sum(c['role']==role and c['status']!='ok' for c in usage),
        'input_tokens': sum(c['input_tokens'] for c in known if c['role']==role),
        'output_tokens': sum(c['output_tokens'] for c in known if c['role']==role)} for role in ('agent','focus')}
    require(summary['usage_by_role'] == by_role, 'role_totals_changed')
    pending = control.pending
    expected_summary = {'policy': config['checkpoint_policy'], 'opportunity_used': control.opportunities > 0,
        'opportunities': control.opportunities, 'max_opportunities': 3,
        'installations': control.revision, 'checkpoint_installed': control.revision > 0,
        'decisions': control.events, 'pending_stage': pending['stage'] if pending else None,
        'valid_checkpoint_pending_without_next_request': bool(pending and pending['stage']=='closed' and pending.get('value') is not None),
        'separate_summary_calls': by_role['focus']['calls'], 'judge_calls': 0,
        'all_summary_and_agent_costs_in_shared_budget': True,
        'schema_checkpoint_required': mode == 'inline', 'tool_choice_forced': False,
        'control_cost_included_in_work_wall': True, 'archive_deleted': False,
        'semantic_fidelity_verified': False, 'task_quality_established': False, 'novel_method_claim': False}
    require(summary['checkpoint_control'] == expected_summary, 'rolling_summary_disposition_changed')
    inventory_checked = inventory.finish(summary)
    return {**total, **inventory_checked, 'model_calls': len(usage), 'usage_by_role': by_role, 'request_checks': checks,
        'checkpoint_installed': control.revision > 0, 'checkpoint_installations': control.revision,
        'checkpoint_opportunity': control.opportunities, 'checkpoint_controls': controls,
        'input_count_records': len(counts), 'invocation_status_counts': dict(Counter(r['status'] for r in receipts)),
        'additional_model_calls': 0, 'additional_API_requests': 0, 'additional_tokenizer_calls': 0,
        'summary_semantics_verified': False}

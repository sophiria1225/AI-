"""Closed P127 records: deterministic control reconstruction, with no execution.

Only trusted controller code runs here. Generated Python is parsed and hashed,
never executed. The replay transport has no external transport and supplies an
ordinary response only when the recorded dispatch is actually requested. Thus
an omitted full read cannot populate the reconstructed cache for free.
"""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess

from agent_read_view_runtime import SchemaForwardingViewChannel
from api_error_comparison import disposition
from audit_rolling_checkpoint_trace import audit_trace
from region_field_projection import plan_region_projection
from automatic_projection_runtime import ProjectionApiChannel
from budget_signal import digest
from compact_api_receipts import ReceiptMetrics, decode_receipts, encode_receipts
from container_api_python import ApiChannel
from context_preservation import compact
from contract_comparison import FeedbackProgram
from field_read_contract import CONTRACT_ID
from inspect_appworld_api_schemas import load_public_tools
from native_data_compute import selected_receipts
from region_projection_runtime import RegionProjectionHost, RegionProjectionProgram, POLICIES
from persistent_read_view_python import ViewControlChannel
from public_api_result_transport import PublicResultTransport
from public_api_envelope import PROTOCOL
from public_name_catalog import PublicNameCatalog
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_whole_task_region_projection import ACTIVATION, PLAN, PREFLIGHT, frozen_hashes, sources
from shared_api_reservations import RequestBudget
from whole_task_region_projection import (ERROR_POLICY, cell_id, config_for, initial_conversation,
                                   run_order, summarize)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def duration(value, reason):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, reason)
    return value


def equal(actual, expected, reason):
    # JSON comparison retains distinctions such as true versus 1, and keeps
    # diagnostics independent of private source/API content.
    require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
            json.dumps(expected, sort_keys=True, allow_nan=False), reason)


def expected_row(event, span):
    row = dict(action=span['action'], observation=span['observation'],
               api_request_sent=event['api_request_sent'], new_tools=event['new_tools'])
    if event.get('effects_unknown'):
        row['effects_unknown'] = True
    if 'api_execution' in event:
        row['api_execution'] = event['api_execution']
    return row


def audit_segment_report(plan, report):
    """Independently check selected segment artifacts, never execute source."""
    require(report['plan_sha256'] == plan.plan_sha256
        and report['source_sha256'] == plan.source_sha256
        and report['transformed_sha256'] == plan.transformed_sha256,
        'region_plan_or_artifact_hash_changed')
    segments, regions = report['segments'], report['regions']
    complete = report['execution_status'] == 'ok'
    require(type(segments) is list and type(regions) is list
        and type(report['hits']) is int and report['hits'] >= 0
        and type(report['transformed']) is bool, 'invalid_segment_report_shape')
    if not segments:
        require(not regions and not report['transformed'] and report['hits'] == 0,
                'empty_segment_report_claims_transformation')
        return
    require(len(segments) <= len(plan.segments)
        and (not complete or len(segments) == len(plan.segments)),
        'selected_segments_are_not_execution_prefix')
    expected_regions = []
    for index, (segment, expected) in enumerate(zip(segments, plan.segments)):
        transformed = segment['transformed']
        require(type(segment['segment_index']) is int and segment['segment_index'] == index
            and type(transformed) is bool and type(segment['completed']) is bool
            and (not complete and index == len(segments)-1 or segment['completed'])
            and segment['kind'] == expected['kind']
            and segment['original_sha256'] == expected['source_sha256']
            and segment['candidate_sha256'] == expected['transformed_sha256']
            and segment['selected_sha256'] == expected[
                'transformed_sha256' if transformed else 'source_sha256']
            and (not transformed or segment['kind'] == 'region'),
            'selected_segment_hash_or_completion_changed')
        if segment['kind'] == 'region':
            expected_regions.append((segment, expected))
    require(len(expected_regions) == len(regions), 'region_report_count_changed')
    previous_hits = 0
    for region, (selected, expected) in zip(regions, expected_regions):
        require(type(region['site_index']) is int and region['site_index'] == expected['site_index']
            and type(region['admitted']) is bool and type(region['transformed']) is bool
            and region['admitted'] is selected['transformed']
            and region['transformed'] is selected['transformed']
            and region['original_sha256'] == expected['source_sha256']
            and region['executed_sha256'] == selected['selected_sha256']
            and region['reason'] == selected['reason']
            and type(region['reason']) is str
            and all(type(region[k]) is int for k in ('hits_before', 'hits_after'))
            and region['hits_before'] == previous_hits
            and region['hits_after'] >= previous_hits,
            'region_admission_or_hit_interval_changed')
        previous_hits = region['hits_after']
    require(previous_hits == report['hits']
        and report['transformed'] is any(region['admitted'] for region in regions),
        'region_total_hits_or_transformation_changed')


class RecordedTransport(PublicResultTransport):
    """Read saved ordinary results; an actual network/process call is impossible."""
    def __init__(self):
        super().__init__(None)
        self.queue = []
        self.position = 0
        self.requested = False
        self.mismatch = False

    def begin(self, rows):
        require(self.position == len(self.queue), 'unconsumed_recorded_API_rows')
        self.queue, self.position, self.requested = deepcopy(rows), 0, False

    def request(self, command):
        try:
            require(self.transport is None and not self.requested and
                    self.position < len(self.queue), 'unrecorded_API_request')
            row = self.queue[self.position]
            action = row['action']
            app, api = action['name'].split('__', 1)
            equal(command, {'op': 'call', 'call': dict(app=app, api=api,
                  args=json.loads(action['arguments']))}, 'recorded_API_order_changed')
            receipt = row.get('api_execution')
            require(type(receipt) is dict, 'dispatch_without_typed_receipt')
            self.receipts.append(deepcopy(receipt))
            self.requested = True
            self.fatal |= receipt['status'] in ('unknown', 'not_dispatched')
            self.complete |= bool(receipt.get('declared_complete'))
            observation = deepcopy(row['observation'])
            observation.pop('contract_feedback', None)
            if not receipt['bridge_request_sent']:
                raise RuntimeError('recorded_pretransport_rejection')
            if 'transport_error_type' in observation:
                # The original ApiChannel catches this and records the class
                # name only. No exception text or invented return value enters.
                error = type(observation['transport_error_type'], (Exception,), {})
                raise error('recorded_unknown_outcome')
            if 'api_error' in observation:
                return {'ok': False, 'error': observation['api_error']}
            require('observation' in observation, 'ordinary_return_value_missing')
            return {'ok': True, 'result': observation}
        except (KeyError, ValueError, TypeError):
            self.mismatch = True
            raise

    def record(self, row):
        require(not self.mismatch and self.position < len(self.queue),
                'reconstructed_API_record_unexpected')
        normalized = deepcopy(row)
        if normalized.get('effects_unknown') is False:
            normalized.pop('effects_unknown')
        equal(normalized, self.queue[self.position], 'reconstructed_API_record_changed')
        require(self.requested == ('api_execution' in row), 'typed_receipt_without_dispatch')
        self.position += 1
        self.requested = False


def compact_audit(folder, events, spans, summary):
    metrics = ReceiptMetrics(record_calls=len(events))
    pending, outer = [], []
    snapshots, seen, call, nonces = {}, {}, None, set()
    ordinals, model_actions = {}, {}
    require(list(spans) == [event['span_id'] for event in events], 'span_event_order_changed')
    for event in events:
        sid = event['span_id']
        span = spans[sid]
        require(span['id'] == sid and type(event['api_request_sent']) is bool,
                'invalid_span_or_API_flag')
        receipt = event.get('api_execution')
        if receipt is not None:
            require(event['stage'] == 'python_api' and receipt['protocol'] == PROTOCOL
                and type(receipt['bridge_request_sent']) is bool
                and receipt['bridge_request_sent'] == event['api_request_sent']
                and receipt['automatic_retries'] == 0 and receipt['rollback_guaranteed'] is False
                and receipt['status'] in ('returned', 'raised', 'unknown', 'not_dispatched'),
                'typed_API_receipt_contract_changed')
            duration(receipt['transport_and_decode_wall_seconds'], 'invalid_typed_receipt_time')
            if receipt['bridge_request_sent']:
                require(type(receipt.get('nonce')) is str and receipt['nonce'] and
                        receipt['nonce'] not in nonces, 'missing_or_reused_invocation_nonce')
                nonces.add(receipt['nonce'])
                require(receipt['status'] != 'not_dispatched', 'sent_receipt_claims_no_dispatch')
            else:
                require(receipt['status'] == 'not_dispatched', 'undispatched_receipt_claims_execution')
            if receipt['status'] in ('returned', 'raised'):
                require(type(receipt.get('raw_reply_sha256')) is str and len(receipt['raw_reply_sha256']) == 64
                    and type(receipt.get('declared_complete')) is bool, 'known_API_reply_evidence_missing')
        else:
            require(event['api_request_sent'] is False, 'sent_API_without_typed_receipt')
        if event['call'] != call:
            require(not pending, 'unassigned_inner_API_records')
            call = event['call']
            require(call not in snapshots, 'noncontiguous_model_execution_records')
            snapshots[call] = deepcopy(seen)
            response = read(folder / call / 'response.json')
            require(response['status'] == 'ok', 'execution_after_unknown_model_response')
            calls = response['message'].get('tool_calls') or []
            model_actions[call] = [item.get('function', {}) for item in calls] if calls else [None]
        if event['stage'] == 'python_api':
            pending.append(event)
        else:
            require(event['stage'] == 'model_tool', 'unknown_event_stage')
            ordinals[call] = ordinals.get(call, 0) + 1
            observation, action = span['observation'], span['action']
            require(ordinals[call] <= len(model_actions[call]), 'extra_model_tool_execution_record')
            equal(action, model_actions[call][ordinals[call] - 1], 'executed_tool_differs_from_model_response')
            if type(action) is dict and action.get('name') == 'run_python' and 'api_receipts' in observation:
                receipts = decode_receipts(observation['api_receipts'])
                wanted = [dict(span_id=item['span_id'], api=spans[item['span_id']]['action']['name'],
                               api_request_sent=item['api_request_sent']) for item in pending]
                equal(receipts, wanted, 'compact_receipt_order_identity_or_dispatch_changed')
                equal(encode_receipts(receipts), observation['api_receipts'], 'receipt_roundtrip_changed')
                metrics.transformed_observations += 1
                metrics.receipt_rows += len(receipts)
                metrics.original_compact_json_bytes += len(compact(receipts).encode())
                metrics.table_compact_json_bytes += len(compact(observation['api_receipts']).encode())
                outer.append((f'{call}_{ordinals[call]:02d}', span, deepcopy(pending), snapshots[call]))
                pending.clear()
            else:
                require(not pending, 'API_records_without_program_boundary')
        seen[sid] = span
    require(not pending, 'terminal_inner_API_records_without_boundary')
    require(all(ordinals.get(call) == len(actions) for call, actions in model_actions.items()),
            'missing_model_tool_execution_record')
    require(summary['unknown_effect_requests'] == sum(e['effects_unknown'] for e in events
            if e['api_request_sent']), 'unknown_API_effect_count_changed')
    metrics.transform_seconds = duration(summary['compact_receipts']['transform_seconds'],
                                         'invalid_receipt_format_time')
    equal(metrics.summary(), summary['compact_receipts'], 'compact_receipt_cost_changed')
    return outer


def audit_runtime(folder, config, tools):
    """Audit one closed worker's evidence without executing its Python source."""
    folder = Path(folder)
    try:
        return _audit_runtime(folder, config, tools)
    except (OSError, KeyError, TypeError, IndexError, AssertionError) as error:
        raise ValueError('projection_runtime_evidence_missing_or_malformed') from error


def _audit_runtime(folder, config, tools):
    summary, events, spans = (read(folder / name) for name in
                              ('summary.json', 'events.json', 'spans.json'))
    outer = compact_audit(folder, events, spans, summary)
    private = ['projection_programs_private.json', 'request_budget_events_private.json',
               'projection_control_events_private.json', 'projection_lookup_events_private.json',
               'ordinary_cache_events_private.json', 'joined_field_events_private.json']
    runtime = summary.get('projection_runtime')
    if runtime is None:
        require(not outer and not events and not list((folder / 'programs').glob('*')),
                'missing_runtime_with_executed_programs')
        return dict(projection_runtime=None, projection_hits=None, projection_contract_failed=None,
                    compact_receipts=summary['compact_receipts'], program_costs=[],
                    runtime_audit_hashes={name: sha(folder / name) for name in
                        ('summary.json', 'events.json', 'spans.json')})
    rows = read(folder / private[0])
    require([row['program'] for row in rows] == [entry[0] for entry in outer],
            'program_attempts_differ_from_recorded_boundaries')
    require(sorted(p.name for p in (folder / 'programs').glob('*') if p.is_dir()) ==
            sorted(row['program'] for row in rows), 'extra_or_missing_program_directory')
    budget, catalog, bridge = RequestBudget(config['max_api_requests']), PublicNameCatalog(tools), RecordedTransport()
    feedback = FeedbackProgram(lambda source, observations, channel, **kw: channel, 'public_schema')
    host, program_costs, checked_files = None, [], ['summary.json', 'events.json', 'spans.json']
    for number, ((name, span, inner, snapshot), row) in enumerate(zip(outer, rows), 1):
        require(not budget.stopped, 'program_started_after_closed_request_budget')
        location = folder / 'programs' / name
        payload = read(location / 'input_private.json')
        args = json.loads(span['action']['arguments'])
        require(type(args) is dict and set(args) == {'code', 'span_ids'}
            and type(args['code']) is str and 0 < len(args['code']) <= 20000
            and type(args['span_ids']) is list and len(args['span_ids']) <= 160
            and all(type(value) is str for value in args['span_ids'])
            and len(args['span_ids']) == len(set(args['span_ids'])), 'submitted_program_argument_shape_changed')
        expected_input = dict(code=args['code'], observations=selected_receipts(args['span_ids'], snapshot),
            program_index=number, api_schemas={n: catalog.catalog[n]['function'] for n in sorted(catalog.visible)})
        equal(payload, expected_input, 'program_source_or_prior_receipts_or_schema_changed')
        plan = plan_region_projection(payload['code'])  # AST only; no generated execution.
        require((location / 'projection_candidate_source_private.py').read_text() == plan.transformed_source,
                'candidate_execution_source_changed')
        evidence = read(location / 'projection_program_private.json')
        result, raw = read(location / 'projection_result_private.json'), read(location / 'result_private.json')
        equal(evidence['result'], result, 'adapter_result_changed')
        before = budget.snapshot()
        bridge.begin([expected_row(e, spans[e['span_id']]) for e in inner])
        base = ApiChannel(catalog, bridge, budget.available)
        wrapped = ProjectionApiChannel(base, budget)
        wrapped.receipted = feedback('', [], wrapped.receipted)
        if host is None:
            host = RegionProjectionHost(wrapped, policy=config['projection_policy'],
                execution_scope=folder.name, public_source_directory=(folder.parents[2] /
                    '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify'))
        else:
            host.attach(wrapped)
        host.expect(plan)
        event_start, report_start = len(host.projection_events), len(host.program_reports)
        field_start = len(host.field_events)
        control = ViewControlChannel(host, bridge.record)
        wire = SchemaForwardingViewChannel(control)
        packets = [json.loads(line) for line in (location / 'wire_private.jsonl').read_text().splitlines()]
        done = None
        for packet in packets:
            require(done is None and type(packet.get('program_index')) is int and
                    packet['program_index'] == number, 'wire_program_boundary_changed')
            if packet.get('kind') == 'api':
                wire.exchange({k: v for k, v in packet.items() if k != 'program_index'})
            else:
                require(set(packet) == {'kind', 'python', 'program_index', 'stdout', 'stdout_truncated', 'error'}
                    and packet['kind'] == 'done' and type(packet['stdout']) is str and len(packet['stdout']) <= 65536
                    and type(packet['stdout_truncated']) is bool
                    and (packet['error'] is None or type(packet['error']) is str), 'invalid_program_done_message')
                done = packet
        require(bridge.position == len(bridge.queue) and not bridge.requested and not bridge.mismatch,
                'ordinary_API_rows_not_consumed_once')
        if done is not None:
            for key in ('stdout', 'stdout_truncated', 'error'):
                equal(raw.get(key), done[key], 'raw_result_differs_from_done_boundary')
            require(raw['status'] == ('execution_error' if done['error'] else 'ok'),
                    'raw_result_status_differs_from_done_boundary')
        else:
            require(raw['status'] != 'ok', 'successful_program_missing_done_boundary')
        # These are the only adapter-level failure latches outside host controls.
        if str(raw.get('error', '')).startswith('ProjectionWireFault:'):
            host.projection_failed = budget.stopped = True
        reports = host.program_reports[report_start:]
        missing_trace_after_partial = (any(e['kind'] == 'partial' for e in
            host.projection_events[event_start:]) and len(reports) != 1)
        if missing_trace_after_partial:
            host.projection_failed = budget.stopped = True
        if raw['status'] == 'ok' and len(reports) != 1:
            host.projection_failed = budget.stopped = True
        if len(reports) == 1:
            require(raw['status'] in ('ok', 'execution_error') and
                    reports[0]['execution_status'] == raw['status'],
                    'region_report_execution_status_changed')
            audit_segment_report(plan, reports[0])
        expected_evidence = dict(policy=config['projection_policy'], source_sha256=plan.source_sha256,
            transformed_sha256=plan.transformed_sha256, region_plan_sha256=plan.plan_sha256,
            transformed_artifact_is_review_only=True, static_eligible=plan.eligible,
            executed_source_sha256=plan.source_sha256 if config['projection_policy'] == POLICIES[0] else None,
            static_reason=plan.reason, sites=plan.sites, budget_before=before, budget_after=budget.snapshot(),
            original_generated_archive_unchanged=True,
            execution_transform_report=reports, projection_failed=host.projection_failed,
            projection_events=host.projection_events[event_start:], field_events=host.field_events[field_start:],
            control_requests=control.control_requests,
            control_request_bytes=control.control_request_bytes, control_reply_bytes=control.control_reply_bytes,
            result=result)
        equal(evidence, expected_evidence, 'projection_execution_evidence_changed')
        expected_forwarding = dict(exchanges=wire.exchanges,
            schema_deliveries=sum(len(e['new_schema_names']) for e in wire.exchanges),
            reply_wire_bytes=sum(e['reply_wire_bytes'] for e in wire.exchanges), extra_API_requests=0,
            submitted_source_sha256=plan.source_sha256,
            execution_transform_record='projection_program_private.json')
        equal(read(location / 'projection_schema_forwarding_private.json'), expected_forwarding,
              'control_reply_schema_bytes_or_hash_changed')
        require(result['api_requests'] == budget.spent - before['spent'] and budget.pending == 0,
                'program_request_accounting_changed')
        require(result['declared_complete'] == base.complete and result['unknown_effects'] == base.fatal,
                'program_completion_or_effects_flag_changed')
        if host.projection_failed:
            require(result['status'] == 'harness_error' and result['session_usable'] is False and
                    number == len(rows), 'projection_failure_did_not_stop_interpreter')
            equal(result['underlying_execution_status'], raw['status'], 'underlying_execution_status_changed')
            equal(result['underlying_execution_error'], raw.get('error'), 'underlying_execution_error_changed')
            equal(result['contract_stop_reason'], 'region_execution_report_missing_after_partial'
                if missing_trace_after_partial else 'region_projection_contract_failed',
                'region_contract_stop_reason_changed')
        else:
            require(result['status'] == raw['status'], 'adapter_status_changed')
            require(not {'underlying_execution_status', 'underlying_execution_error',
                         'contract_stop_reason'} & result.keys(), 'invented_underlying_execution_failure')
        for key in ('stdout', 'stdout_truncated', 'declared_complete', 'unknown_effects'):
            equal(result[key], raw[key], 'adapter_changed_execution_result')
        observation = span['observation']
        for key in ('status', 'stdout', 'stdout_truncated', 'api_requests', 'declared_complete', 'unknown_effects'):
            equal(observation[key], result[key], 'displayed_program_result_changed')
        equal(observation['error'], result.get('error', result.get('error_type')), 'displayed_program_error_changed')
        expected_program = dict(program=name, source_sha256=plan.source_sha256, status=result['status'],
            budget_before=before, budget_after=budget.snapshot(), wall_seconds=duration(row['wall_seconds'],
                'invalid_program_wall_time'), evidence_recorded=True,
            evidence_sha256=sha(location / 'projection_program_private.json'), schema_evidence_recorded=True,
            schema_deliveries=expected_forwarding['schema_deliveries'],
            schema_reply_wire_bytes=expected_forwarding['reply_wire_bytes'],
            schema_evidence_sha256=sha(location / 'projection_schema_forwarding_private.json'))
        expected_program.update({key: evidence[key] for key in (
            'transformed_sha256', 'executed_source_sha256', 'static_eligible', 'static_reason',
            'execution_transform_report', 'projection_failed', 'control_requests',
            'control_request_bytes', 'control_reply_bytes')})
        equal(row, expected_program, 'program_index_or_evidence_hash_changed')
        program_costs.append({k: row[k] for k in ('program', 'status', 'source_sha256',
            'evidence_sha256', 'schema_evidence_sha256', 'wall_seconds', 'control_requests',
            'control_request_bytes', 'control_reply_bytes', 'schema_deliveries', 'schema_reply_wire_bytes')})
        checked_files += [str(p.relative_to(folder)) for p in sorted(location.iterdir()) if p.is_file()]
    equal(read(folder / 'request_budget_events_private.json'), budget.events, 'request_reservation_history_changed')
    equal(summary['request_budget'], budget.snapshot(), 'final_request_budget_changed')
    equal(summary['api_execution_receipts'], bridge.receipts, 'typed_API_receipt_sequence_changed')
    require(summary['api_requests'] == budget.spent == sum(e['api_request_sent'] for e in events) ==
            sum(receipt['bridge_request_sent'] for receipt in bridge.receipts), 'task_API_accounting_changed')
    for filename, value in (
            ('projection_control_events_private.json', host.control_events if host else []),
            ('projection_lookup_events_private.json', host.projection_events if host else []),
            ('ordinary_cache_events_private.json', host.ordinary_cache_events if host else []),
            ('joined_field_events_private.json', host.field_events if host else [])):
        if host:
            equal(read(folder / filename), value, 'private_control_or_cache_history_changed')
        else:
            require(not (folder / filename).exists(), 'unexpected_control_history_without_host')
    feedback.control_seconds = duration(runtime['feedback']['control_wall_seconds'], 'invalid_feedback_time')
    if host:
        host.control_wall_seconds_including_backend = duration(runtime['control_wall_seconds_including_backend'],
                                                              'invalid_control_wall_time')
        host.projection_lookup_wall_seconds = duration(runtime['projection_lookup_wall_seconds'], 'invalid_lookup_time')
        require(host.projection_lookup_wall_seconds <= host.control_wall_seconds_including_backend <=
                sum(row['wall_seconds'] for row in rows), 'control_time_outside_program_wall')
        saved_adapter = runtime['demand_adapter']
        host.demand_adapter._lookup_seconds = duration(saved_adapter['lookup_wall_seconds'],
                                                       'invalid_demand_lookup_time')
        host.demand_adapter._verification_seconds = duration(saved_adapter['verification_wall_seconds'],
                                                             'invalid_authority_verification_time')
        require(host.demand_adapter._lookup_seconds <= host.control_wall_seconds_including_backend
            and host.demand_adapter._verification_seconds <= sum(row['wall_seconds'] for row in rows),
            'demand_adapter_time_outside_program_wall')
    reconstructed = object.__new__(RegionProjectionProgram)
    reconstructed.host, reconstructed.budget, reconstructed.policy = host, budget, config['projection_policy']
    reconstructed.program_rows, reconstructed.feedback = rows, feedback
    equal(runtime, reconstructed.summary(), 'projection_runtime_summary_changed')
    equal(summary['contract_feedback'], feedback.summary(), 'feedback_summary_changed')
    if summary['stop_reason'] == 'projection_contract_stopped':
        require(host is not None and host.projection_failed and budget.stopped and
                summary['unknown_effect_requests'] == 0 and summary['cleanup_confirmed'] is True,
                'known_projection_stop_not_closed_or_effects_unknown')
    checked_files += [name for name in private if (folder / name).exists()]
    require(runtime['projection_partial_hits'] == runtime['automatic_region_partial_hits'],
            'automatic_and_explicit_field_hits_conflated')
    return dict(projection_runtime=runtime, projection_hits=runtime['projection_partial_hits'],
        automatic_region_partial_hits=runtime['automatic_region_partial_hits'],
        explicit_field_requests=runtime['explicit_field_requests'],
        explicit_field_partial_hits=runtime['explicit_field_partial_hits'],
        projection_contract_failed=runtime['projection_failed'], compact_receipts=summary['compact_receipts'],
        program_costs=program_costs, runtime_audit_hashes={name: sha(folder / name) for name in checked_files})


def audit_cell(folder, root, plan, original, item, policy, pre, evaluated, *, tools=None):
    folder, root = Path(folder), Path(root)
    summary = read(folder / 'summary.json')
    config = config_for(original, plan, item['task_id'], policy)
    require(read(folder / 'plan.json') == config and read(folder / 'comparison_plan.json') == plan
        and read(folder / 'public_task.json') == item['public_task'] and summary['arm'] == ERROR_POLICY
        and summary['time_visibility'] == 'not_exposed' and summary['checkpoint_policy'] == 'rolling_separate'
        and summary['projection_policy'] == policy and summary['reasoning_budget_tokens'] == -1
        and summary['task_id'] == item['task_id'] and summary['run_id'] == folder.name
        and summary['prefix_api_requests'] == 0, 'executed_P127_condition_changed')
    conversation = initial_conversation(original, item['public_task'])
    initial, _ = conversation.for_model(config['observation_page_characters'])
    require(digest(initial) == pre['base_messages_sha256'], 'initial_input_differs_from_preflight')
    checked = audit_trace(folder, config, conversation)
    if tools is None:
        tools = load_public_tools(folder.parents[2] / '.runtime/appworld/r18_probe_01/data')[0]
    runtime = audit_runtime(folder, config, tools)
    require(not evaluated or disposition(summary) != 'stop_batch', 'evaluation_after_invalid_cell')
    success = None
    if evaluated:
        evaluation = read(folder / 'evaluation.json')
        require(evaluation['execution_summary_sha256'] == sha(folder / 'summary.json')
            and evaluation['evaluation_returned_to_model'] is False and type(evaluation['official_success']) is bool
            and evaluation['evaluation_script_sha256'] == sha(root / 'scripts/evaluate_context_trial.py'),
            'independent_evaluation_link_changed')
        dbs = (folder.parents[2] / '.runtime/appworld/r18_probe_01/experiments/outputs'
               / folder.name / 'tasks' / item['task_id'] / 'dbs')
        hashes = {str(p.relative_to(dbs)): sha(p) for p in sorted(dbs.rglob('*')) if p.is_file()}
        require(bool(hashes) and hashes == evaluation['frozen_database_hashes'], 'evaluated_database_hashes_changed')
        success = evaluation['official_success']
    known = [call for call in read(folder / 'usage.json') if call['status'] == 'ok']
    return {**checked, **runtime, 'run_id': folder.name, 'task_id': item['task_id'],
        'time_visibility': 'not_exposed', 'checkpoint_policy': 'rolling_separate', 'projection_policy': policy,
        'record_status': 'evaluated' if evaluated else 'unevaluated', 'success': success,
        **{k: summary[k] for k in ('stop_reason', 'model_calls', 'known_total_tokens', 'unknown_usage_calls',
                                  'api_requests', 'wall_seconds', 'full_wall_seconds', 'cleanup_wall_seconds')},
        'input_tokens': sum(c['input_tokens'] for c in known),
        'output_tokens': sum(c['output_tokens'] for c in known),
        'cached_input_tokens': sum(c['cached_input_tokens'] for c in known)
            if all(type(c.get('cached_input_tokens')) is int for c in known) else None,
        'setup_wall_seconds': summary['setup']['wall_seconds'],
        'summary_sha256': sha(folder / 'summary.json'), 'usage_sha256': sha(folder / 'usage.json'),
        'evaluation_sha256': sha(folder / 'evaluation.json') if evaluated else None}


def run(storage, root):
    storage, root = Path(storage), Path(root)
    target = root / 'reports/P127_comparison.json'
    if target.exists():
        raise FileExistsError('preserve_all_P127_audit_attempts')
    pipeline_dir = storage / 'records/context_pilot/P127_pipeline_v01'
    pipeline, server = read(pipeline_dir / 'status.json'), read(pipeline_dir / 'server_final.json')
    require(pipeline['status'] in ('complete', 'stopped') and pipeline.get('server_stopped')
        and server['status'] == 'stopped' and server['supervisor_pid'] == pipeline['server_supervisor_pid'],
        'owned_P127_pipeline_must_be_closed_before_audit')
    for key in ('pid', 'supervisor_pid'):
        process = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='],
                                 capture_output=True, text=True, timeout=10)
        require(process.returncode == 1 and not process.stdout.strip(), 'owned_P127_process_still_exists')
    plan, original, tools, prepared = sources(storage, root)
    activation, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    require(activation['source_hashes'] == frozen_hashes(root)
        and activation['preflight_sha256'] == sha(root / PREFLIGHT), 'P127_frozen_sources_changed')
    batch = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    require(batch['status'] in ('complete', 'stopped'), 'wait_until_budget_batch_closes')
    rows, errors = [], []
    for number, policy in run_order():
        item = prepared[number - 1]
        rid = cell_id(number, policy)
        folder = storage / 'records/context_pilot' / rid
        row = dict(run_id=rid, task_id=item['task_id'], time_visibility='not_exposed',
            checkpoint_policy='rolling_separate', projection_policy=policy, record_status='not_run',
            success=None, known_total_tokens=None, unknown_usage_calls=None,
            projection_hits=None, projection_contract_failed=None)
        if (folder / 'summary.json').exists():
            try:
                row = audit_cell(folder, root, plan, original, item, policy,
                    pre['rows'][number - 1]['conditions'][policy], rid in batch['completed'], tools=tools)
                require(read(folder / 'summary.json')['phase'] == 'P127', 'wrong_budget_worker')
            except Exception as error:
                row.update(record_status='audit_error', success=None, known_total_tokens=None,
                           unknown_usage_calls=None, projection_hits=None, projection_contract_failed=None)
                errors.append(dict(run_id=rid, type=type(error).__name__, reason=str(error)
                    if type(error) is ValueError else 'malformed_or_missing_audit_input'))
        elif folder.exists() or batch.get('active') == rid:
            # The parent records activation before spawning the worker. A
            # startup failure may leave no trial directory, but is not proof
            # that the slot was never attempted or had zero execution cost.
            row['record_status'] = 'incomplete_worker'
        rows.append(row)
    result = dict(phase='P127', batch_status=batch['status'], rows=rows, audit_errors=errors,
        **summarize(rows, errors), pipeline_status_sha256=sha(pipeline_dir / 'status.json'),
        server_final_sha256=sha(pipeline_dir / 'server_final.json'), owned_processes_absent=True,
        plan_sha256=sha(root / PLAN), activation_sha256=sha(root / ACTIVATION), auditor_sha256=sha(Path(__file__)),
        additional_model_calls=0, additional_api_calls=0, additional_evaluator_calls=0,
        reserved_scenarios_read=0, private_reasoning_inspected_semantically=False,
        database_contents_inspected=False, generated_code_executed_by_auditor=False)
    write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'audit_errors', 'development_gate_met')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    arguments = parser.parse_args()
    run(arguments.storage_root, arguments.repo_root)

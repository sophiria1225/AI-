"""P129 ordinary output-grounding replay from original wire and typed results.

Only trusted host/controller code runs. Original model programs are parsed,
never executed. Effective write actions are regenerated from prior records;
saved proposals or grounding ledgers never supply the decision or CSV content.
"""
from copy import deepcopy
import json
from pathlib import Path

from audit_whole_task_region_projection import (RecordedTransport, audit_segment_report,
    compact_audit, duration, equal, expected_row as base_expected_row, require)
from agent_read_view_runtime import SchemaForwardingViewChannel
from automatic_projection_runtime import ProjectionApiChannel
from container_api_python import ApiChannel
from contract_comparison import FeedbackProgram
from context_preservation import compact
from native_data_compute import selected_receipts
from output_grounding_runtime import OutputGroundingController, GroundedReceiptExchange
from persistent_read_view_python import ViewControlChannel
from public_name_catalog import PublicNameCatalog
from public_output_grounding import PublicExportMonitor, verify_public_export_sources, digest
from region_field_projection import plan_region_projection
from region_projection_runtime import RegionProjectionHost, RegionProjectionProgram, POLICIES
from run_handoff_factors import read, sha
from shared_api_reservations import RequestBudget


def expected_row(event, span):
    row = base_expected_row(event, span)
    if 'output_grounding_entry' in event:
        row['output_grounding_entry'] = event['output_grounding_entry']
    return row


class GroundingRecordedTransport(RecordedTransport):
    def __init__(self, on_event):
        super().__init__()
        self.on_event, self.events, self.spans = on_event, [], {}

    def begin_grounded(self, events, spans):
        self.events, self.spans = events, spans
        super().begin([expected_row(e, spans[e['span_id']]) for e in events])

    def record(self, row):
        event = self.events[self.position]
        super().record(row)
        self.on_event(event, self.spans[event['span_id']], row.get('output_grounding_entry'))


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
        # An initialization failure does not establish zero controller cost or
        # a complete grounding ledger. The batch retains this fixed slot as an
        # audit_error with unknown amounts; its original records remain intact.
        raise ValueError('grounding_runtime_uninitialized_accounting_unknown')
    rows = read(folder / private[0])
    require([row['program'] for row in rows] == [entry[0] for entry in outer],
            'program_attempts_differ_from_recorded_boundaries')
    require(sorted(p.name for p in (folder / 'programs').glob('*') if p.is_dir()) ==
            sorted(row['program'] for row in rows), 'extra_or_missing_program_directory')
    budget, catalog = RequestBudget(config['max_api_requests']), PublicNameCatalog(tools)
    public_root = folder.parents[2] / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
    contract = verify_public_export_sources(public_root)
    equal(summary['output_grounding_public_contract'], contract, 'output_grounding_public_contract_changed')
    controller = OutputGroundingController(PublicExportMonitor(read(folder / 'public_task.json'),
        execution_scope=folder.name), mode=config['output_grounding_policy'])
    event_cursor = 0
    private_notices = []
    def consume_event(event, span, entry_index=None):
        nonlocal event_cursor
        require(event_cursor < len(events) and events[event_cursor] == event,
                'grounding_source_must_follow_actual_record_order')
        require(entry_index == event.get('output_grounding_entry'), 'grounding_record_marker_changed')
        controller.observe(event, span, entry_index=entry_index)
        event_cursor += 1
    def consume_outer(event, span):
        notice = controller.take_notice()
        equal(span['observation'].get('output_grounding_notice'), notice, 'grounding_outer_notice_changed')
        require(('output_grounding_notice' in span['observation']) == (notice is not None),
                'grounding_notice_presence_changed')
        if notice is not None:
            private_notices.append(dict(call_id=event['call'], span_id=event['span_id'],
                notice=notice, notice_sha256=digest(notice)))
        consume_event(event, span)
        return notice
    bridge = GroundingRecordedTransport(consume_event)
    event_positions = {event['span_id']: i for i, event in enumerate(events)}
    notices = []
    feedback = FeedbackProgram(lambda source, observations, channel, **kw: channel, 'public_schema')
    host, program_costs, checked_files = None, [], ['summary.json', 'events.json', 'spans.json']
    for number, ((name, span, inner, snapshot), row) in enumerate(zip(outer, rows), 1):
        require(not budget.stopped, 'program_started_after_closed_request_budget')
        location = folder / 'programs' / name
        start = event_positions[inner[0]['span_id'] if inner else span['id']]
        while event_cursor < start:
            event = events[event_cursor]
            require(event['stage'] == 'model_tool', 'unreplayed_API_before_program')
            consume_outer(event, spans[event['span_id']])
        controller.program = name
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
        bridge.begin_grounded(inner, spans)
        base = ApiChannel(catalog, bridge, budget.available)
        wrapped = ProjectionApiChannel(base, budget)
        wrapped.receipted = feedback('', [], wrapped.receipted)
        wrapped.receipted = GroundedReceiptExchange(wrapped.receipted, wrapped.base, controller)
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
        notice = consume_outer(events[event_cursor], span)
        notices.append(dict(program=name, notice_sha256=digest(notice),
            notice_UTF8_bytes=len(compact(notice).encode()) if notice is not None else 0))
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
    while event_cursor < len(events):
        event = events[event_cursor]
        require(event['stage'] == 'model_tool', 'unreplayed_API_after_last_program')
        consume_outer(event, spans[event['span_id']])
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
    grounding = summary['output_grounding']
    controller.wall_seconds = duration(grounding['wall_seconds'], 'invalid_grounding_control_time')
    require(controller.wall_seconds <= summary['wall_seconds'], 'grounding_time_outside_work_clock')
    equal(read(folder / 'output_grounding_events_private.json'), controller.entries,
          'grounding_decisions_or_payload_bindings_changed')
    equal(read(folder / 'output_grounding_notices_private.json'), private_notices,
          'grounding_notice_ledger_changed')
    equal(grounding, controller.summary(), 'grounding_summary_not_reconstructed')
    require(summary['output_grounding_summary_error_type'] is None,
            'incomplete_grounding_summary_cannot_be_verified')
    require(controller.observed_events == len(events) and not controller.notices,
            'grounding_event_or_notice_accounting_incomplete')
    checked_files.extend(('output_grounding_events_private.json', 'output_grounding_notices_private.json'))
    require(runtime['projection_partial_hits'] == runtime['automatic_region_partial_hits'],
            'automatic_and_explicit_field_hits_conflated')
    return dict(**grounding_metrics(grounding), grounding_runtime=grounding,
        grounding_audit_hashes={name: sha(folder / name) for name in (
            'summary.json', 'public_task.json', 'events.json', 'spans.json',
            'output_grounding_events_private.json', 'output_grounding_notices_private.json')},
        grounding_program_notices=notices, projection_runtime=runtime, projection_hits=runtime['projection_partial_hits'],
        automatic_region_partial_hits=runtime['automatic_region_partial_hits'],
        explicit_field_requests=runtime['explicit_field_requests'],
        explicit_field_partial_hits=runtime['explicit_field_partial_hits'],
        projection_contract_failed=runtime['projection_failed'], compact_receipts=summary['compact_receipts'],
        program_costs=program_costs, runtime_audit_hashes={name: sha(folder / name) for name in checked_files})



def grounding_metrics(grounding):
    # The strict successful-repair field is supplied by the reexecuted trusted
    # controller only after the actual typed reply and monitor backup check.
    return dict(grounding_write_checks=grounding['write_checks'],
        grounding_feedback_blocks=grounding['feedback_blocks'],
        grounding_repair_attempts=grounding['repair_attempts'],
        grounding_sent_repairs=grounding['grounding_sent_repairs'],
        grounding_repairs=grounding['grounding_repairs'],
        grounding_incomplete_write_records=grounding['incomplete_write_records'],
        grounding_pending_notices=grounding['pending_notices'],
        grounding_contract_failed=not grounding['contract_intact'],
        grounding_accounting_complete=bool(grounding['contract_intact']
            and grounding['incomplete_write_records'] == 0 and grounding['pending_notices'] == 0),
        grounding_wall_seconds=grounding['wall_seconds'], grounding_ledger_sha256=grounding['ledger_sha256'])

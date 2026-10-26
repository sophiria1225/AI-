"""P128 worker: shared explicit runtime, immutable full/disclosed receipt history.

All host records and expansions remain in the paid job ledger. No automatic
region transformation is enabled in either display condition.
"""
import datetime as dt
import time

from whole_task_receipt_disclosure import initial_conversation, config_for, MODES, SEEDS, cell_id
from receipt_disclosure_rolling_inference import ReceiptDisclosureRollingInference
from checkpoint_attempt_usage import attempt_usage
from compact_api_receipts import execute_response, ReceiptMetrics
from context_preservation import page_span
from native_data_compute import selected_receipts
from region_projection_runtime import RegionProjectionPython, RegionProjectionProgram
from shared_api_reservations import RequestBudget
from joined_public_read_views import verify_joined_implementation
from preflight_public_api_live import RecordedBridge, confirm_initial_world
from public_api_result_transport import PublicResultTransport, TypedBridgeProcess
from public_display import CODE_TOOLS
from public_name_catalog import PublicNameCatalog
from run_context_comparison import BudgetStop, write_json


def check_api_accounting(budget, api_requests, events, bridge):
    """At program boundaries, one ledger counts each actually dispatched request."""
    if (budget.pending != 0 or budget.spent != api_requests
            or api_requests != sum(int(event['api_request_sent']) for event in events)
            or api_requests != sum(int(receipt['bridge_request_sent']) for receipt in bridge.receipts)):
        budget.stopped = True
        raise RuntimeError('projection_API_ledger_and_receipts_disagree')


def run_cell(storage, root, plan, original, tools, item, arm, run_id, *, receipt_mode, replication):
    if (receipt_mode not in MODES or type(replication) is not int
            or not 1 <= replication <= len(SEEDS)):
        raise ValueError('fixed_receipt_mode_and_replication_required')
    config = config_for(original, plan, item['task_id'], receipt_mode, replication)
    number = next(i for i, task in enumerate(plan['known_tasks'], 1)
                  if task['task_id'] == item['task_id'])
    if run_id != cell_id(replication, number, receipt_mode) or config['seed'] != SEEDS[replication - 1]:
        raise ValueError('fixed_cell_identity_and_seed_required')
    config['run_id'] = run_id
    projection_policy = 'explicit_joined_fields'
    if (config.get('projection_policy') != projection_policy
            or config.get('receipt_disclosure_policy') != receipt_mode):
        raise ValueError('shared_explicit_runtime_and_receipt_mode_required')
    checkpoint_policy = 'rolling_separate'
    if config['checkpoint_policy'] != checkpoint_policy or arm != 'error_exception':
        raise ValueError('common_rolling_checkpoint_and_exception_policy_required')
    time_visibility = 'not_exposed'
    trial = storage / 'records/context_pilot' / run_id
    appworld = storage / '.runtime/appworld/r18_probe_01'
    world = appworld / 'experiments/outputs' / run_id
    if trial.exists() or world.exists():
        raise FileExistsError('preserve_every_budget_observation_attempt')
    trial.mkdir(parents=True)
    write_json(trial / 'plan.json', config)
    write_json(trial / 'comparison_plan.json', plan)
    write_json(trial / 'source_identity.json', {k: item[k] for k in
        ('task_id', 'source_run', 'known_public_task_sha256')})
    catalog = PublicNameCatalog(tools)
    bridge = recorded = raw = session = infer = adapter = budget = conversation = None
    disclosure_error_type = sidecar_save_error_type = None
    receipt_metrics = ReceiptMetrics()
    started = time.monotonic()
    setup = {'status': 'running'}
    spans, events, formatting = {}, [], {}
    api_requests, complete, reason = 0, False, 'not_started'
    bridge_cleanup = None
    stopped = lambda: (storage / '.runtime/P128.stop').exists()
    try:
        if stopped():
            raise InterruptedError('explicit_P128_stop')
        public_source_directory = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify'
        verify_joined_implementation(public_source_directory)
        raw = TypedBridgeProcess(storage / '.runtime/appworld/venv/bin/python', appworld, trial,
                                 timeout_seconds=90)
        recorded = RecordedBridge(raw, trial, started + plan['max_setup_seconds'], stop=stopped)
        bridge = PublicResultTransport(recorded)
        public = confirm_initial_world(bridge.request({'op': 'init', 'task_id': item['task_id'],
            'experiment': run_id, 'seed': plan['world_seed']}), item['public_task'])
        write_json(trial / 'public_task.json', public)
        conversation = initial_conversation(original, public, receipt_mode, execution_scope=run_id)
        session = RegionProjectionPython(storage, trial / 'python_session', policy=projection_policy)
        budget = RequestBudget(config['max_api_requests'])
        if time.monotonic() - started >= plan['max_setup_seconds']:
            raise TimeoutError('setup_deadline')
        setup.update(status='initial_public_state_matched', wall_seconds=time.monotonic() - started)
        write_json(trial / 'setup.json', setup)
        infer = ReceiptDisclosureRollingInference(config, trial, conversation=conversation)
        adapter = RegionProjectionProgram(session, budget, execution_scope=run_id,
            public_source_directory=public_source_directory, policy=projection_policy)
        task_deadline = infer.started + config['max_wall_seconds']

        def program(source, observations, channel, **kwargs):
            recorded.deadline = min(task_deadline, time.monotonic() + kwargs['timeout'])
            result = adapter(source, observations, channel, **kwargs)
            check_api_accounting(budget, api_requests, events, bridge)
            return result

        while not complete:
            check_api_accounting(budget, api_requests, events, bridge)
            if budget.stopped:
                raise RuntimeError('projection_request_budget_stopped_no_retry')
            if stopped():
                raise InterruptedError('explicit_P128_stop')
            if api_requests >= config['max_api_requests']:
                raise BudgetStop('api_request_limit')
            messages, formatting = conversation.for_model(config['observation_page_characters'])
            infer.api_requests = api_requests
            message = infer.call('agent', messages, CODE_TOOLS)
            call_id = infer.calls[-1]['id']
            current_spans, first = [], True

            def record(row, display=True):
                nonlocal api_requests, complete, first
                sid = f's{len(spans) + 1}'
                spans[sid] = {'id': sid, 'assistant': (message.get('content') or '') if first else '',
                              'action': row['action'], 'observation': row['observation']}
                first = False
                if display:
                    current_spans.append(spans[sid])
                api_requests += int(row['api_request_sent'])
                complete |= bool(row['observation'].get('declared_complete')) or bridge.complete
                event = {'call': call_id, 'span_id': sid,
                         'stage': 'model_tool' if display else 'python_api',
                         'api_request_sent': row['api_request_sent'], 'new_tools': row['new_tools'],
                         'effects_unknown': row.get('effects_unknown', False), 'declared_complete': complete}
                if 'api_execution' in row:
                    event['api_execution'] = dict(row['api_execution'])
                events.append(event)
                write_json(trial / 'spans.json', spans)
                write_json(trial / 'events.json', events)
                write_json(trial / 'progress.json', {'arm': arm, 'task_id': item['task_id'],
                    'time_visibility':time_visibility, 'checkpoint_policy':checkpoint_policy,
            'projection_policy':projection_policy,
            'receipt_disclosure_policy':receipt_mode, 'receipt_mode':receipt_mode, 'replication':replication,
            'reasoning_budget_tokens':config['model']['reasoning_budget_tokens'],
                    'calls':len(attempt_usage(infer)), 'tokens':infer.tokens, 'api_requests':api_requests,
                    'unknown_usage_calls':sum(c['status'] != 'ok' for c in attempt_usage(infer))})
                return sid

            rows = execute_response(message, catalog, bridge, selected_receipts(list(spans), spans), record,
                receipt_metrics=receipt_metrics,
                out=trial, storage=storage, call_id=call_id,
                remaining_api=lambda: config['max_api_requests'] - api_requests,
                may_continue=lambda: time.monotonic() < task_deadline and not complete and not stopped(),
                remaining_wall=lambda: task_deadline - time.monotonic(), program=program,
                read_archive=lambda sid, offset: page_span(spans, sid, offset,
                                                           config['observation_page_characters']))
            check_api_accounting(budget, api_requests, events, bridge)
            try:
                conversation.append_closed_turn(message, current_spans, call_id=call_id,
                    events=events, spans=spans, pending_reads=budget.pending)
                write_json(trial / 'receipt_disclosure_sidecar_private.json',
                           conversation.disclosure_snapshot())
            except Exception as error:
                disclosure_error_type = type(error).__name__
                raise
            finally:
                # Even a rejected seal cannot erase the paid API records above.
                write_json(trial / 'conversation_private.json', conversation.messages())
            if bridge.fatal or any(r.get('effects_unknown') for r in rows):
                raise RuntimeError('unknown_API_effect_no_retry')
            if not session.usable or any(r['observation'].get('status') == 'harness_error' for r in rows):
                raise RuntimeError('interpreter_unavailable_no_retry')
        reason = 'agent_declared_complete'
    except BudgetStop as error:
        reason = str(error)
    except Exception as error:
        reason = 'setup_failure' if infer is None else 'runtime_error'
        if isinstance(error, InterruptedError):
            reason = 'user_stop'
        elif (infer is not None and any(c['status'] != 'ok' for c in attempt_usage(infer))):
            reason = 'model_usage_unknown'
        elif (str(error) == 'interpreter_unavailable_no_retry'
              and adapter is not None and adapter.host is not None and adapter.host.projection_failed
              and bridge is not None and not bridge.fatal
              and not any(event['effects_unknown'] for event in events if event['api_request_sent'])):
            # This cell stays stopped. Its known-cost failure can be evaluated;
            # a fresh task may continue only after the existing cleanup checks.
            reason = 'projection_contract_stopped'
        if (reason not in ('model_usage_unknown', 'user_stop') and conversation is not None
                and (disclosure_error_type is not None or conversation.contract_failed)):
            reason = 'receipt_disclosure_contract_stopped'
        if infer is None:
            setup['status'] = 'failed'
        write_json(trial / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        work_wall = time.monotonic() - infer.started if infer else 0
        setup.setdefault('wall_seconds', time.monotonic() - started)
        cleanup_started = time.monotonic()
        cleanup_errors = []
        if session is not None:
            try:
                session.close()
            except Exception as error:
                cleanup_errors.append(type(error).__name__)
        if raw is not None:
            try:
                bridge_cleanup = raw.close()
            except Exception as error:
                cleanup_errors.append(type(error).__name__)
        cleanup_wall = time.monotonic() - cleanup_started
        cleanup_confirmed = (not cleanup_errors and session is not None
            and session.state.get('container_removed') is True
            and bridge_cleanup is not None and bridge_cleanup.get('graceful') is True
            and bridge_cleanup.get('process_stopped') is True
            and bridge_cleanup.get('transport_failed') is False
            and cleanup_wall <= plan['max_cleanup_seconds'])
        if not cleanup_confirmed and reason not in ('setup_failure', 'user_stop'):
            reason = 'cleanup_error'
        terminal_calls = infer.calls if infer else []
        write_json(trial / 'terminal_usage.json', terminal_calls)
        calls = attempt_usage(infer)
        known = [c for c in calls if c['status'] == 'ok']
        for name, value in (('usage', calls), ('spans', spans), ('events', events), ('setup', setup)):
            write_json(trial / (name + '.json'), value)
        disclosure_summary = None
        if conversation is not None:
            try:
                write_json(trial / 'conversation_private.json', conversation.messages())
                write_json(trial / 'receipt_disclosure_sidecar_private.json',
                           conversation.disclosure_snapshot())
            except Exception as error:
                sidecar_save_error_type = type(error).__name__
            try:
                disclosure_summary = conversation.disclosure_summary()
            except Exception as error:
                sidecar_save_error_type = sidecar_save_error_type or type(error).__name__
            if sidecar_save_error_type is not None:
                if reason not in ('cleanup_error', 'setup_failure', 'user_stop', 'model_usage_unknown'):
                    reason = 'receipt_disclosure_contract_stopped'
        summary = {'phase':'P128', 'run_id':run_id, 'task_id':item['task_id'], 'arm':arm,
            'model_seed':config['seed'], 'world_seed':plan['world_seed'],
            'time_visibility':time_visibility, 'checkpoint_policy':checkpoint_policy,
            'projection_policy':projection_policy,
            'receipt_disclosure_policy':receipt_mode, 'receipt_mode':receipt_mode, 'replication':replication,
            'reasoning_budget_tokens':config['model']['reasoning_budget_tokens'],
            'terminal_model_responses':len(terminal_calls),
            'dispatched_without_terminal_usage':len(calls)-len(terminal_calls),
            'stop_reason': reason, 'declared_complete': complete, 'evaluation': 'not_run',
            'final_success': None, 'finished_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'model_calls': len(calls), 'known_total_tokens': infer.tokens if infer else 0,
            'unknown_usage_calls': len(calls) - len(known),
            'usage_by_role': {role: {
                'calls': sum(c['role'] == role for c in calls),
                'unknown_usage': sum(c['role'] == role and c['status'] != 'ok' for c in calls),
                'input_tokens': sum(c['input_tokens'] for c in known if c['role'] == role),
                'output_tokens': sum(c['output_tokens'] for c in known if c['role'] == role)}
                for role in ('agent', 'focus')},
            'api_requests': api_requests, 'prefix_api_requests': 0,
            'setup': setup, 'wall_seconds': work_wall, 'cleanup_wall_seconds': cleanup_wall,
            'full_wall_seconds': time.monotonic() - started, 'cleanup_confirmed': cleanup_confirmed,
            'cleanup_errors': cleanup_errors, 'bridge_cleanup': bridge_cleanup,
            'unknown_effect_requests': sum(e['effects_unknown'] for e in events if e['api_request_sent']),
            'api_execution_receipts': bridge.receipts if bridge else [],
            'history_formatting': formatting, 'python_session': session.state if session else None,
            'catalog_policy': 'public_names', 'history_policy': plan['history_policy'],
            'initial_public_task_sha256': item['known_public_task_sha256'],
            'automatic_retries': 0, 'reserved_scenarios_read': 0}
        if infer is not None:
            summary['checkpoint_control'] = infer.checkpoint_summary()
        summary['compact_receipts'] = receipt_metrics.summary()
        summary['receipt_disclosure'] = disclosure_summary
        summary['receipt_disclosure_contract_intact'] = bool(conversation is not None
            and not conversation.contract_failed and disclosure_error_type is None
            and sidecar_save_error_type is None and disclosure_summary is not None
            and disclosure_summary.get('disclosure_contract_intact') is True)
        summary['receipt_disclosure_error_type'] = disclosure_error_type
        summary['sidecar_save_error_type'] = sidecar_save_error_type
        summary['request_budget'] = budget.snapshot() if budget else None
        if budget is not None:
            write_json(trial / 'request_budget_events_private.json', budget.events)
        if adapter is not None:
            summary['projection_runtime'] = adapter.summary()
            summary['contract_feedback'] = adapter.feedback.summary()
            write_json(trial / 'projection_programs_private.json', adapter.program_rows)
            if adapter.host is not None:
                write_json(trial / 'projection_control_events_private.json', adapter.host.control_events)
                write_json(trial / 'projection_lookup_events_private.json', adapter.host.projection_events)
                write_json(trial / 'joined_field_events_private.json', adapter.host.field_events)
                write_json(trial / 'ordinary_cache_events_private.json', adapter.host.ordinary_cache_events)
        write_json(trial / 'summary.json', summary)
    return summary

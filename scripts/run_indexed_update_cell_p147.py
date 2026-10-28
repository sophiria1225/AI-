"""P147 fresh eight-cell worker with UPDATE-only structured transport.

Copied from the frozen P144R1 worker because it has no inference injection hook.
Only adapter/configuration imports, fresh stop/phase identity and honest
transport metadata differ. Task APIs, setup, action execution, terminal usage,
wall bounds and owned cleanup are unchanged. No CLI or model autolaunch.
"""
import datetime as dt
import time
import math
import signal
import threading
from contextlib import contextmanager

from api_error_comparison import ErrorPresentationProgram
from whole_task_state_update_p144 import initial_conversation
from indexed_update_inference_p147 import IndexedUpdateInference
from inline_checkpoint_execution import execute_inline_response
from checkpoint_attempt_usage import attempt_usage
from indexed_update_config_p147 import worker_config
from code_agent_interface import execute_response
from context_preservation import page_span
from contract_comparison import FeedbackProgram
from native_data_compute import selected_receipts
from persistent_api_python import PersistentApiPython
from preflight_public_api_live import RecordedBridge, confirm_initial_world
from public_api_result_transport import PublicResultTransport, TypedBridgeProcess
from public_display import CODE_TOOLS
from public_name_catalog import PublicNameCatalog
from run_context_comparison import BudgetStop, write_json
from reserved_confirmation_reference_provider import _close_owned


def _require(ok, label):
    if not ok:
        raise ValueError(label)


def _alarm_supported():
    _require(threading.current_thread() is threading.main_thread() and
             all(hasattr(signal, k) for k in ('SIGALRM', 'ITIMER_REAL', 'setitimer', 'getitimer')),
             'main_thread_posix_alarm_required')


@contextmanager
def _deadline(deadline):
    """Local setup/cleanup only; preserve a callable outer one-shot timer."""
    _alarm_supported()
    entered = time.monotonic()
    _require(type(deadline) in (int, float) and math.isfinite(deadline), 'finite_deadline_required')
    if deadline <= entered:
        raise TimeoutError('stage_deadline_before_operation')
    old_handler = signal.getsignal(signal.SIGALRM)
    old_delay, interval = signal.getitimer(signal.ITIMER_REAL)
    _require(interval == 0 and (old_delay == 0 or callable(old_handler)),
             'only_callable_outer_one_shot_timer_supported')
    outer_at = entered + old_delay if old_delay else None
    delivered = False

    def expired(signum, frame):
        nonlocal delivered
        now = time.monotonic()
        if outer_at is not None and not delivered and now >= outer_at:
            delivered = True
            old_handler(signum, frame)
        if now >= deadline:
            raise TimeoutError('stage_deadline')
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, deadline - time.monotonic()))

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(deadline-entered, old_delay) if old_delay else deadline-entered)
    try:
        yield
        if time.monotonic() > deadline:
            raise TimeoutError('stage_deadline_after_operation')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        remaining = max(0.000001, outer_at-time.monotonic()) if outer_at is not None and not delivered else 0
        signal.setitimer(signal.ITIMER_REAL, remaining)


def _process_stopped(process):
    if process is None:
        return True
    try:
        return process.poll() is not None
    except BaseException:
        return None  # Failed observation is not proof of absence.


def _cleanup_session(session, deadline):
    """Do not infer container removal from an attempted or interrupted close."""
    if session is None:
        return dict(owned_process_stopped=True, container_removed=True, errors=[], not_created=True)
    errors = []
    try:
        with _deadline(deadline):
            session.close()
    except BaseException as error:
        errors.append(type(error).__name__)
    process = getattr(session, 'process', None)
    # Only the retained owned CLI handle; container deletion remains separate.
    for operation, fraction in (('terminate', 0.5), ('kill', 1.0)):
        if process is not None and _process_stopped(process) is not True:
            try:
                getattr(process, operation)()
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    process.wait(timeout=remaining*fraction)
            except BaseException as error:
                errors.append(type(error).__name__)
    state = getattr(session, 'state', {})
    return dict(owned_process_stopped=_process_stopped(process),
        container_removed=state.get('container_removed') is True,
        errors=errors, not_created=False)


def _run_cell(storage, root, plan, original, tools, item, arm, run_id, *, checkpoint_representation_mode):
    config = worker_config(original, plan, item['task_id'], arm, run_id, checkpoint_representation_mode)
    checkpoint_policy = 'rolling_separate'
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
    bridge = recorded = raw = session = infer = feedback = None
    started = time.monotonic()
    setup = {'status': 'running'}
    spans, events, formatting = {}, [], {}
    api_requests, complete, reason = 0, False, 'not_started'
    bridge_cleanup = None
    stopped = lambda: (storage / '.runtime/P147.stop').exists()
    try:
        with _deadline(started + plan['max_setup_seconds']):
            if stopped():
                raise InterruptedError('explicit_P147_stop')
            raw = TypedBridgeProcess.__new__(TypedBridgeProcess)
            TypedBridgeProcess.__init__(raw, storage / '.runtime/appworld/venv/bin/python', appworld, trial,
                                     timeout_seconds=min(60, plan['max_setup_seconds']))
            recorded = RecordedBridge(raw, trial, started + plan['max_setup_seconds'], stop=stopped)
            bridge = PublicResultTransport(recorded)
            public = confirm_initial_world(bridge.request({'op': 'init', 'task_id': item['task_id'],
                'experiment': run_id, 'seed': plan['world_seed']}), item['public_task'])
            write_json(trial / 'public_task.json', public)
            conversation = initial_conversation(original, public)
            session = PersistentApiPython.__new__(PersistentApiPython)
            PersistentApiPython.__init__(session, storage, trial / 'python_session')
            if time.monotonic() - started >= plan['max_setup_seconds']:
                raise TimeoutError('setup_deadline')
            setup.update(status='initial_public_state_matched', wall_seconds=time.monotonic() - started)
            write_json(trial / 'setup.json', setup)
        inference_type = IndexedUpdateInference
        infer = inference_type(config, trial, conversation=conversation)
        feedback = FeedbackProgram(session.run, 'public_schema')
        presented = ErrorPresentationProgram(feedback, arm)
        task_deadline = infer.started + config['max_wall_seconds']

        def program(source, observations, channel, **kwargs):
            recorded.deadline = min(task_deadline, time.monotonic() + kwargs['timeout'])
            return presented(source, observations, channel, **kwargs)

        while not complete:
            if stopped():
                raise InterruptedError('explicit_P147_stop')
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
                if 'inline_transport' in row:
                    event['inline_transport'] = dict(row['inline_transport'])
                events.append(event)
                write_json(trial / 'spans.json', spans)
                write_json(trial / 'events.json', events)
                write_json(trial / 'progress.json', {'phase':'P147', 'arm': arm, 'task_id': item['task_id'],
                    'checkpoint_representation_mode':checkpoint_representation_mode, 'object_timing_mode':checkpoint_representation_mode,
                    'time_visibility':time_visibility, 'checkpoint_policy':checkpoint_policy,
                    'base_reasoning_budget_tokens':config['model']['reasoning_budget_tokens'],
                    'comparison_arm':config['comparison_arm'], 'update_transport':config['update_transport'],
                    'actor_reasoning_budget_tokens':config['actor_reasoning_budget_tokens'],
                    'first_focus_reasoning_budget_tokens':config['first_focus_reasoning_budget_tokens'],
                    'update_focus_reasoning_budget_tokens':config['update_focus_reasoning_budget_tokens'],
                    'calls':len(attempt_usage(infer)), 'tokens':infer.tokens, 'api_requests':api_requests,
                    'unknown_usage_calls':sum(c['status'] != 'ok' for c in attempt_usage(infer))})
                return sid

            inline = checkpoint_policy == 'rolling_inline'
            executor = execute_inline_response if inline else execute_response
            execution_options = {'offered': infer.current_offer,
                'finish_reason': infer.calls[-1]['finish_reason'],
                'usage_known': infer.calls[-1]['status'] == 'ok'} if inline else {}
            executed = executor(message, catalog, bridge, selected_receipts(list(spans), spans), record,
                out=trial, storage=storage, call_id=call_id,
                remaining_api=lambda: config['max_api_requests'] - api_requests,
                may_continue=lambda: time.monotonic() < task_deadline and not complete and not stopped(),
                remaining_wall=lambda: task_deadline - time.monotonic(), program=program,
                read_archive=lambda sid, offset: page_span(spans, sid, offset,
                                                           config['observation_page_characters']),
                **execution_options)
            rows, split = executed if inline else (executed, None)
            conversation.append(message, current_spans)
            write_json(trial / 'conversation_private.json', conversation.messages())
            if inline:
                infer.close_turn(split)
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
        elif (infer is not None and infer.calls and infer.calls[-1]['status'] != 'ok'
              and str(error) == 'model failure; usage unknown, no free retry'):
            reason = 'model_usage_unknown'
        if infer is None:
            setup['status'] = 'failed'
        write_json(trial / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        work_wall = time.monotonic() - infer.started if infer else 0
        setup.setdefault('wall_seconds', time.monotonic() - started)
        cleanup_started = time.monotonic()
        cleanup_end = cleanup_started + plan['max_cleanup_seconds']
        cleanup_errors = []
        try:
            python_cleanup = _cleanup_session(session, cleanup_end)
        except BaseException as error:
            python_cleanup = dict(owned_process_stopped=None, container_removed=False,
                errors=[type(error).__name__], not_created=session is None)
        cleanup_errors.extend(python_cleanup['errors'])
        bridge_detail = None
        if raw is not None:
            try:
                with _deadline(cleanup_end):
                    bridge_cleanup, bridge_detail = _close_owned(raw, recorded, cleanup_end, time.monotonic)
            except BaseException as error:
                cleanup_errors.append(type(error).__name__)
        cleanup_wall = time.monotonic() - cleanup_started
        all_owned_stopped = (python_cleanup['owned_process_stopped'] is True and
            python_cleanup['container_removed'] is True and
            _process_stopped(getattr(raw, 'process', None)) is True)
        cleanup_confirmed = (not cleanup_errors and session is not None and all_owned_stopped
            and isinstance(bridge_cleanup, dict) and bridge_cleanup.get('graceful') is True
            and bridge_cleanup.get('process_stopped') is True
            and bridge_cleanup.get('transport_failed') is False
            and isinstance(bridge_detail, dict) and bridge_detail.get('within_deadline') is True
            and cleanup_wall <= plan['max_cleanup_seconds'])
        if not cleanup_confirmed and reason not in ('setup_failure', 'user_stop'):
            reason = 'cleanup_error'
        terminal_calls = infer.calls if infer else []
        write_json(trial / 'terminal_usage.json', terminal_calls)
        calls = attempt_usage(infer)
        known = [c for c in calls if c['status'] == 'ok']
        for name, value in (('usage', calls), ('spans', spans), ('events', events), ('setup', setup)):
            write_json(trial / (name + '.json'), value)
        summary = {'phase':'P147', 'run_id':run_id, 'task_id':item['task_id'], 'arm':arm,
            'checkpoint_representation_mode':checkpoint_representation_mode, 'object_timing_mode':checkpoint_representation_mode, 'model_seed':config['seed'],
            'checkpoint_timing':config['checkpoint_timing'],
            'checkpoint_representation':config['checkpoint_representation'],
            'time_visibility':time_visibility, 'checkpoint_policy':checkpoint_policy,
            'base_reasoning_budget_tokens':config['model']['reasoning_budget_tokens'],
            'comparison_arm':config['comparison_arm'], 'update_transport':config['update_transport'],
            'actor_reasoning_budget_tokens':config['actor_reasoning_budget_tokens'],
            'first_focus_reasoning_budget_tokens':config['first_focus_reasoning_budget_tokens'],
            'update_focus_reasoning_budget_tokens':config['update_focus_reasoning_budget_tokens'],
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
            'bridge_cleanup_detail':bridge_detail, 'python_cleanup':python_cleanup,
            'all_owned_processes_stopped':all_owned_stopped,
            'unknown_effect_requests': sum(e['effects_unknown'] for e in events if e['api_request_sent']),
            'api_execution_receipts': bridge.receipts if bridge else [],
            'history_formatting': formatting, 'python_session': getattr(session, 'state', None),
            'catalog_policy': 'public_names', 'history_policy': plan['history_policy'],
            'initial_public_task_sha256': item['known_public_task_sha256'],
            'automatic_retries': 0, 'reserved_scenarios_read': 0}
        if infer is not None:
            summary['checkpoint_control'] = infer.checkpoint_summary()
            summary['prefix_exposure_control'] = infer.exposure_summary()
            summary['checkpoint_representation_control'] = infer.representation_summary()
            summary['delta_envelope_control'] = infer.envelope_summary()
            summary['state_update_control'] = infer.state_update_summary()
            summary['indexed_update_transport'] = infer.schema_transport_summary()
        if feedback is not None:
            summary['contract_feedback'] = feedback.summary()
        write_json(trial / 'summary.json', summary)
    return summary


def run_cell(storage, root, plan, original, tools, item, arm, run_id, *, checkpoint_representation_mode):
    _alarm_supported()
    _require(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'unarmed_process_alarm_required')
    from inference_timeout_handler import inference_timeout_handler
    with inference_timeout_handler():
        return _run_cell(storage, root, plan, original, tools, item, arm, run_id,
                         checkpoint_representation_mode=checkpoint_representation_mode)

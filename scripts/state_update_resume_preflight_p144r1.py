"""Fresh native-count preflight of all twelve original templates; no generation.

Adapted from P144 preflight/activation only: new output namespace, frozen
continuation source graph and new owned server. Scientific payloads unchanged.
"""
import datetime as dt
import math
import subprocess
import time
from api_error_comparison import task_snapshot
from budget_observation import notification
from whole_task_state_update_p144 import MODES as POLICIES, config_for, make_notification, initial_conversation
from budget_signal import digest
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from fixed_budget_local_llama import count_input as count_summary_input, payload_for as summary_payload
from state_update_resume_server_p144r1 import live_identity
from public_display import CODE_TOOLS
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import read, sha
from run_state_update_resume_p144r1 import sources, frozen_hashes
PREFLIGHT = 'reports/P144R1_initial_checks.json'
ACTIVATION = 'reports/P144R1_activation_v01.json'

def preflight(storage, root):
    folder = storage / 'records/context_pilot/P144R1_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P144R1_preflight_attempts')
    if (storage / '.runtime/P144R1.stop').exists():
        raise InterruptedError('explicit_P144R1_stop_before_preflight')
    check_resume(storage)
    plan, original, _, prepared = sources(storage, root)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 150)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P144R1_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'input_count_requests': 0, 'summary_input_count_requests': 0, 'failed_input_count_requests': 0,
        'representation_actor_input_count_requests': 0, 'representation_transport': [],
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_twelve_inputs_checked': False}
    try:
        for item in prepared:
            row = {'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in POLICIES:
                if (storage / '.runtime/P144R1.stop').exists():
                    raise InterruptedError('explicit_P144R1_stop')
                remaining = 150 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P144R1_preflight_deadline')
                base, formatting = initial_conversation(original, item['public_task']).for_model()
                if formatting != {'text_fallback_turns': 0, 'paged_spans': 0}:
                    raise ValueError('unexpected_initial_formatting')
                config = config_for(original, plan, item['task_id'], arm)
                state = task_snapshot(config, [], 0, 0)
                supplied, visible = make_notification(base, state, arm, wall_limit=plan["max_wall_seconds"])
                path = folder / (item['source_run'] + '_' + arm + '_private.json')
                write_json(path, supplied)
                entry = {'base_messages_sha256': digest(base), 'model_messages_sha256': digest(supplied),
                         'input_sha256': sha(path), 'measured_state': state, 'visible_state': visible}
                row['conditions'][arm] = entry
                cfg = {**config['model'], 'temperature': original['agent_temperature'],
                       'seed': plan['model_seed'], 'num_predict': original['max_output_tokens'],
                       'cache_prompt': False}
                request_path = folder / (item['source_run'] + '_' + arm + '_request_private.json')
                write_json(request_path, payload_for(cfg, supplied, CODE_TOOLS))
                entry['count_request_sha256'] = sha(request_path)
                entry['reasoning_budget_tokens'] = cfg['reasoning_budget_tokens']
                entry['tool_choice'] = cfg['tool_choice']
                result['input_count_requests'] += 1
                try:
                    entry.update(count_input(cfg, supplied, CODE_TOOLS, timeout=min(30, remaining)))
                except Exception:
                    result['failed_input_count_requests'] += 1
                    raise
                entry['admission'] = admission(plan['max_total_tokens'], entry['input_tokens'],
                                               cfg['num_predict'], cfg['num_ctx'], 'residual')
                if not entry['admission']['admitted']:
                    raise ValueError('initial_request_does_not_fit')
                write_json(folder / 'status.json', result)
            entries = [row['conditions'][arm] for arm in POLICIES]
            if any(e['model_messages_sha256'] != entries[0]['model_messages_sha256']
                   or e['base_messages_sha256'] != entries[0]['base_messages_sha256']
                   or e['visible_state'] != entries[0]['visible_state']
                   or e['input_tokens'] != entries[0]['input_tokens'] for e in entries):
                raise ValueError('all_three_initial_inputs_must_match')
            requests = [read(folder / (item['source_run'] + '_' + arm + '_request_private.json')) for arm in POLICIES]
            if any(request != requests[0] for request in requests) or requests[0]['tool_choice'] != 'auto':
                raise ValueError('same_initial_request_and_auto_tool_choice_required')
            if 'wall_seconds_at_snapshot' in entries[0]['visible_state']['remaining']:
                raise ValueError('hidden_time_was_exposed')
        # Six focus templates and three installed actor views; no generation.
        from checkpoint_state_update_preflight_p144 import synthetic_transport_cases
        for case in synthetic_transport_cases():
            if (storage / '.runtime/P144R1.stop').exists():
                raise InterruptedError('explicit_P144R1_stop')
            remaining = 150 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('P144R1_preflight_deadline')
            actor = case['role'] == 'agent'
            supplied = (notification(case['messages'], task_snapshot(config, [], 0, 0),
                                     'not_exposed')[0] if actor else case['messages'])
            cfg = {**config['model'], 'temperature': config['agent_temperature'] if actor
                   else config['draft_temperature'], 'seed': plan['model_seed'],
                   'num_predict': config['max_output_tokens'], 'cache_prompt': not actor}
            transport = payload_for if actor else summary_payload
            counter = count_input if actor else count_summary_input
            path = folder / (case['name'] + '_request_private.json')
            write_json(path, transport(cfg, supplied, case['tools']))
            entry = {'name': case['name'], 'role': case['role'], 'request_sha256': sha(path),
                     'synthetic_only': True}
            result['representation_transport'].append(entry)
            result['representation_actor_input_count_requests' if actor else 'summary_input_count_requests'] += 1
            try:
                entry.update(counter(cfg, supplied, case['tools'], timeout=min(30, remaining)))
            except Exception:
                result['failed_input_count_requests'] += 1
                raise
        if time.monotonic() - started > 150:
            raise TimeoutError('P144R1_preflight_deadline')
        result.update(status='complete', all_twelve_inputs_checked=True)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - started
        write_json(folder / 'status.json', result)
        write_json(target, result)
    return result


def validate_preflight(storage, root, pre, plan, original, prepared):
    """Bind saved native counts to the exact independently reconstructed payloads."""
    fixed = dict(phase='P144R1_preflight', status='complete', all_twelve_inputs_checked=True,
        input_count_requests=12, summary_input_count_requests=6, representation_actor_input_count_requests=3,
        failed_input_count_requests=0, model_generations=0, environment_api_requests=0,
        evaluator_calls=0, reserved_scenarios_read=0)
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if (any(type(pre.get(k)) is not type(v) or pre[k] != v for k,v in fixed.items())
            or pre.get('git_commit') != head
            or type(pre.get('wall_seconds')) not in (int,float)
            or not math.isfinite(pre['wall_seconds']) or not 0 <= pre['wall_seconds'] <= 150
            or type(pre.get('representation_transport')) is not list or len(pre['representation_transport']) != 9
            or pre['source_hashes'] != frozen_hashes(root)
            or pre.get('research_resume') != check_resume(storage)
            or len(pre.get('rows', [])) != 4 or len(prepared) != 4):
        raise ValueError('P144R1_preparation_incomplete_or_stale')
    folder = storage / 'records/context_pilot/P144R1_preflight_v01'
    if read(folder / 'status.json') != pre:
        raise ValueError('saved_preflight_report_and_status_differ')
    for item, row in zip(prepared, pre['rows'], strict=True):
        if (row['task_id'] != item['task_id'] or row['source_run'] != item['source_run']
                or set(row['conditions']) != set(POLICIES)):
            raise ValueError('all_twelve_preflight_identities_required')
        payloads, counts = [], []
        for mode in POLICIES:
            config = config_for(original, plan, item['task_id'], mode)
            base, _ = initial_conversation(original, item['public_task']).for_model()
            state = task_snapshot(config, [], 0, 0)
            supplied, visible = make_notification(base, state, mode, wall_limit=plan['max_wall_seconds'])
            cfg = {**config['model'], 'temperature': original['agent_temperature'],
                'seed': plan['model_seed'], 'num_predict': original['max_output_tokens'], 'cache_prompt': False}
            payload = payload_for(cfg, supplied, CODE_TOOLS)
            stem = item['source_run'] + '_' + mode
            message_path, request_path = folder/(stem+'_private.json'), folder/(stem+'_request_private.json')
            entry = row['conditions'][mode]
            if (type(entry.get('input_tokens')) is not int or entry['input_tokens'] <= 0
                    or entry.get('base_messages_sha256') != digest(base)
                    or entry.get('model_messages_sha256') != digest(supplied)
                    or digest(entry.get('measured_state')) != digest(state)
                    or digest(entry.get('visible_state')) != digest(visible)
                    or entry.get('input_sha256') != sha(message_path) or read(message_path) != supplied
                    or entry.get('count_request_sha256') != sha(request_path) or read(request_path) != payload
                    or entry.get('reasoning_budget_tokens') != -1 or entry.get('tool_choice') != 'auto'):
                raise ValueError('preflight_count_or_payload_changed')
            expected = admission(plan['max_total_tokens'], entry['input_tokens'],
                                 cfg['num_predict'], cfg['num_ctx'], 'residual')
            if entry['admission'] != expected or not expected['admitted']:
                raise ValueError('preflight_admission_changed')
            payloads.append(payload); counts.append(entry['input_tokens'])
        if any(p != payloads[0] for p in payloads) or len(set(counts)) != 1:
            raise ValueError('three_arm_initial_input_mismatch')
    from checkpoint_state_update_preflight_p144 import synthetic_transport_cases
    cases = synthetic_transport_cases()
    if len(cases) != 9 or sum(c['role']=='focus' for c in cases) != 6:
        raise ValueError('nine_fixed_representation_templates_required')
    for case, entry in zip(cases, pre['representation_transport'], strict=True):
        actor = case['role'] == 'agent'
        supplied = (notification(case['messages'], task_snapshot(config, [], 0, 0),
                                 'not_exposed')[0] if actor else case['messages'])
        cfg = {**config['model'], 'temperature': config['agent_temperature'] if actor else config['draft_temperature'],
            'seed': plan['model_seed'], 'num_predict': config['max_output_tokens'], 'cache_prompt': not actor}
        transport = payload_for if actor else summary_payload
        path = folder/(case['name']+'_request_private.json')
        if (entry['name'] != case['name'] or entry['role'] != case['role']
                or entry['synthetic_only'] is not True or entry['request_sha256'] != sha(path)
                or read(path) != transport(cfg, supplied, case['tools'])
                or type(entry['input_tokens']) is not int or entry['input_tokens'] <= 0):
            raise ValueError('fixed_representation_transport_changed')


def activate(storage, root):
    if (root / ACTIVATION).exists():
        raise FileExistsError('preserve_P144R1_activation')
    if (storage / '.runtime/P144R1.stop').exists():
        raise InterruptedError('explicit_P144R1_stop_before_activation')
    plan, original, _, prepared = sources(storage, root)
    pre = read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    write_json(root / ACTIVATION, {'phase': 'P144R1', 'source_hashes': pre['source_hashes'],
        'git_commit': pre['git_commit'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_twelve_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def validate_activation(storage, root, freeze, pre):
    if (freeze.get('phase') != 'P144R1'
            or freeze.get('all_twelve_conditions_frozen_before_generation') is not True
            or freeze.get('git_commit') != pre['git_commit']
            or freeze.get('source_hashes') != frozen_hashes(root)
            or freeze.get('preflight_sha256') != sha(root / PREFLIGHT)
            or freeze.get('research_resume') != check_resume(storage)):
        raise ValueError('frozen_P144R1_sources_or_resumption_changed')



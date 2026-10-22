"""Fixed P68 matched fresh native comparison; no historical future receipts."""
from importlib.metadata import distributions

from inspect_appworld_api_schemas import load_public_tools
from public_name_comparison import can_continue_batch as ordinary_continue
from run_handoff_factors import ROOT, read, sha
from run_native_appworld import NATIVE_PROMPT, GENERAL_GUIDANCE

PLAN = 'configs/P68_export_completion_v01.json'
ORDER = [['6104387_1', 'native', 'P68_01_EXPORT_NATIVE'],
         ['6104387_1', 'controlled', 'P68_02_EXPORT_CONTROLLED']]


def validate(plan, original):
    expected = {'phase': 'P68', 'source_config': 'configs/P25_guidance_transfer_v01.json',
        'source_run': 'P25_04_GUIDED', 'task_ids': ['6104387_1'],
        'arms': ['native', 'controlled'], 'run_order': ORDER,
        'seed': 42, 'max_calls': 80, 'max_total_tokens': 450000, 'max_wall_seconds': 1800,
        'max_output_tokens': 4096, 'api_budget_by_task': {'6104387_1': 80},
        'max_setup_seconds': 120, 'max_evaluation_seconds': 180, 'max_idle_wait_seconds': 60,
        'server_max_lifetime_seconds': 5280, 'server_readiness_seconds': 300, 'worker_timeout_seconds': 4800,
        'output_reservation': 'fixed', 'model_usage_receipt': 'streaming_terminal_usage_required',
        'first_call_cache_prompt': False, 'same_arm_later_cache_prompt': True,
        'notification': 'same_static_limits_and_P25_generic_native_guidance',
        'max_controller_checks_per_condition': 80, 'max_public_events_per_check': 4000,
        'max_controller_completion_attempts': 1,
        'controller_check_boundary': 'after_whole_native_model_message_execution_before_next_generation',
        'controller_action': {'app': 'supervisor', 'api': 'complete_task', 'args': {'status': 'success'}},
        'unknown_or_unsupported_policy': 'continue_ordinary_agent_without_extra_hint_or_request',
        'controller_completion_failure_policy': 'stop_condition_and_remaining_schedule_without_retry',
        'reserved_scenarios_read': 0, 'novel_method_claim': False}
    if any(plan.get(k) != v for k, v in expected.items()): raise ValueError('fixed P68 protocol changed')
    for k in ('seed', 'max_calls', 'max_total_tokens', 'max_wall_seconds', 'max_output_tokens'):
        if original[k] != plan[k]: raise ValueError('P25 budget/seed changed')
    if original['max_api_requests'] != 80 or original['general_guidance_version'] != 'appworld_public_rules_v1':
        raise ValueError('ordinary API budget/guidance changed')


def interface(config):
    if config['general_guidance_version'] != 'appworld_public_rules_v1':
        raise ValueError('fixed ordinary native guidance required')
    return NATIVE_PROMPT + GENERAL_GUIDANCE + (
        f'\nTask limits are {config["max_calls"]} model calls, '
        f'{config["max_total_tokens"]} full input plus output tokens, '
        f'{config["max_wall_seconds"]} seconds and {config["max_api_requests"]} '
        'environment API calls, including completion. Maximum output per model call '
        f'is {config["max_output_tokens"]} tokens. All original task requirements apply. '
        'No extra budget or automatic retry will be granted.\n')


def sources(storage):
    plan = read(ROOT / PLAN); original = read(ROOT / plan['source_config']); validate(plan, original)
    if sha(ROOT / plan['source_config']) != plan['source_config_sha256']:
        raise ValueError('original native config changed')
    for name, digest in plan['source_code_sha256'].items():
        if sha(ROOT / name) != digest: raise ValueError('closed checker/guidance changed')
    if sha(ROOT / 'reports/P67_public_export_scope.json') != plan['public_scope_sha256']:
        raise ValueError('closed public scope changed')
    packages = storage / '.runtime/appworld/venv/lib/python3.12/site-packages'
    versions = [d.version for d in distributions(path=[str(packages)])
                if d.metadata['Name'].lower() == 'appworld']
    if versions != [original['appworld_version']]: raise ValueError('AppWorld version changed')
    for app, digest in plan['public_api_implementation_sha256'].items():
        if sha(packages / 'appworld/apps' / app / 'apis.py') != digest:
            raise ValueError('public API semantics changed')
    trial = storage / 'records/context_pilot' / plan['source_run']
    for name, digest in plan['source_files_sha256'].items():
        if sha(trial / name) != digest: raise ValueError('known initial source changed')
    provenance = read(trial / 'provenance.json')
    data = storage / '.runtime/appworld/r18_probe_01/data'
    tools, schema_hashes, _ = load_public_tools(data)
    tid = plan['task_ids'][0]
    if (schema_hashes != provenance['public_schema_hashes']
            or sha(data / 'tasks' / tid / 'specs.json') != provenance['spec_sha256']):
        raise ValueError('known task or public schemas changed')
    task = read(trial / 'public_task.json'); initial = read(trial / 'boundaries/manifests/initial.json')
    if task['ground_truth_loaded'] or initial['state']['model_calls'] or initial['state']['api_requests']:
        raise ValueError('public task start only; no future state')
    hashes = {k: v['sha256'] for k, v in initial['files'].items() if k.startswith('dbs/')}
    if len(hashes) != 13: raise ValueError('missing initial database identities')
    return plan, original, {tid: {'public_task': task, 'initial_database_hashes': hashes}}, tools


def can_continue_batch(summary):
    if summary.get('unknown_effect_events'): return False
    if summary['stop_reason'] == 'controller_declared_complete':
        return (summary['setup']['status'] == 'matched_public_task_start' and summary['declared_complete']
            and not summary['unknown_effect_requests'] and summary['controller_completion_attempts'] == 1)
    return ordinary_continue(summary)

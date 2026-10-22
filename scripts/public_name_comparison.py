"""Fixed P64 fresh-task ordinary Python interfaces and public source identity."""
import copy
from importlib.metadata import distributions

from code_agent_interface import CODE_TOOLS
from inspect_appworld_api_schemas import load_public_tools
from run_handoff_factors import ROOT, read, sha
from stateful_code_prompts import stateful_system_prompt

PLAN = 'configs/P64_public_name_comparison_v01.json'
ARMS = ('documented', 'named')
ORDER = [
    ['34d9492_1', 'documented', 'P64_01_PHOTO_DOCUMENTED'],
    ['34d9492_1', 'named', 'P64_02_PHOTO_NAMED'],
    ['3c13f5a_1', 'named', 'P64_03_BILL_NAMED'],
    ['3c13f5a_1', 'documented', 'P64_04_BILL_DOCUMENTED'],
]


def validate(plan, original):
    expected = {'phase': 'P64', 'arms': list(ARMS), 'run_order': ORDER,
        'source_config': 'configs/P29_stateful_code_v01.json',
        'source_runs': ['P29_01_CODE', 'P29_02_CODE'], 'task_ids': ['34d9492_1', '3c13f5a_1'],
        'seed': 42, 'max_calls': 80, 'max_total_tokens': 450000,
        'max_wall_seconds': 1800, 'max_output_tokens': 4096,
        'api_budget_by_task': {'34d9492_1': 160, '3c13f5a_1': 80},
        'max_setup_seconds': 120, 'max_evaluation_seconds': 180, 'max_idle_wait_seconds': 60,
        'server_max_lifetime_seconds': 10080, 'server_readiness_seconds': 300,
        'worker_timeout_seconds': 9600, 'output_reservation': 'fixed',
        'model_usage_receipt': 'streaming_terminal_usage_required',
        'first_call_cache_prompt': False, 'same_arm_later_cache_prompt': True,
        'notification': 'static_common_limits_no_live_wall_snapshot',
        'reserved_scenarios_read': 0, 'novel_method_claim': False}
    if any(plan.get(k) != v for k, v in expected.items()):
        raise ValueError('fixed P64 conditions or bounds changed')
    for name in ('seed', 'max_calls', 'max_total_tokens', 'max_wall_seconds', 'max_output_tokens'):
        if original[name] != plan[name]: raise ValueError('P29 common budget or seed changed')
    if any(original['api_budget_by_task'][t] != b for t, b in plan['api_budget_by_task'].items()):
        raise ValueError('P29 API budget changed')


def sources(storage):
    plan = read(ROOT / PLAN)
    original = read(ROOT / 'configs/P29_stateful_code_v01.json')
    validate(plan, original)
    packages = storage / '.runtime/appworld/venv/lib/python3.12/site-packages'
    versions = [d.version for d in distributions(path=[str(packages)])
                if d.metadata['Name'].lower() == 'appworld']
    if versions != [original['appworld_version']]: raise ValueError('AppWorld version changed')
    data = storage / '.runtime/appworld/r18_probe_01/data'
    tools, schema_hashes, _ = load_public_tools(data)
    tasks = {}
    for n, (tid, rid) in enumerate(zip(plan['task_ids'], plan['source_runs'])):
        trial = storage / 'records/context_pilot' / rid
        for name in ('public_task', 'provenance'):
            if sha(trial / (name + '.json')) != plan['source_' + name + '_sha256'][n]:
                raise ValueError('original public source changed')
        provenance = read(trial / 'provenance.json')
        if (schema_hashes != provenance['public_schema_hashes']
                or sha(data / 'tasks' / tid / 'specs.json') != provenance['spec_sha256']):
            raise ValueError('known task or public schemas changed')
        task = read(trial / 'public_task.json')
        if task['ground_truth_loaded']: raise ValueError('public task only')
        initial = trial / 'boundaries/manifests/initial.json'
        if sha(initial) != plan['source_initial_boundary_sha256'][n]:
            raise ValueError('original initial state identity changed')
        manifest = read(initial)
        if manifest['state']['model_calls'] or manifest['state']['api_requests']:
            raise ValueError('task start only; no future state')
        tasks[tid] = {'public_task': task, 'initial_database_hashes': {
            k: v['sha256'] for k, v in manifest['files'].items() if k.startswith('dbs/')}}
        if not tasks[tid]['initial_database_hashes']: raise ValueError('missing original initial databases')
    return plan, original, tasks, tools


def interface(arm, config):
    if arm not in ARMS: raise ValueError('unknown ordinary admission policy')
    prompt = stateful_system_prompt(config)
    definitions = copy.deepcopy(CODE_TOOLS)
    if arm == 'named':
        changes = [
            ('calls one discovered public API', 'calls one registered public API by its exact name'),
            ('Initially only\napi_docs and supervisor APIs are available. Discover APIs with',
             'Exact names of registered public APIs may be called before reading their\n'
             'documentation. Unregistered or private APIs are unavailable. Initially\n'
             'only api_docs and supervisor definitions are visible. Discover APIs with'),
            ('After discovery, you may use the API within the same program.',
             'Documentation is optional when you already know the exact public API name\n'
             'and its arguments; it is available when you need details.'),
        ]
        for before, after in changes:
            if prompt.count(before) != 1: raise ValueError('original capability wording changed')
            prompt = prompt.replace(before, after)
        old = definitions[0]['function']['description']
        if old.count('discovered simulated APIs') != 1: raise ValueError('tool description changed')
        definitions[0]['function']['description'] = old.replace(
            'discovered simulated APIs', 'registered public simulated APIs')
    prompt += (f'\nTask limits are {config["max_calls"]} model calls, '
        f'{config["max_total_tokens"]} full input plus output tokens, '
        f'{config["max_wall_seconds"]} seconds and {config["max_api_requests"]} '
        'environment API calls, including completion. Maximum output per model call '
        f'is {config["max_output_tokens"]} tokens. All original task requirements apply. '
        'No extra budget or automatic retry will be granted.\n')
    return prompt, definitions


def can_continue_batch(summary):
    return (summary['setup']['status'] == 'matched_public_task_start'
        and not summary['unknown_effect_requests']
        and summary['stop_reason'] in (
            'agent_declared_complete', 'call_limit', 'wall_limit', 'api_request_limit',
            'token_reservation_limit', 'context_limit',
            'model_usage_unknown', 'model_response_unusable'))

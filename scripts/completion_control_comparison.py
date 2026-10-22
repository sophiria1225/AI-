"""Fixed P66 budget and source identity; no future public receipts enter execution."""
from public_name_comparison import sources as baseline_sources, can_continue_batch as baseline_continue
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P66_ordinary_completion_v01.json'
ORDER = [['34d9492_1', 'documented', 'P66_01_PHOTO_DOCUMENTED'],
         ['34d9492_1', 'named', 'P66_02_PHOTO_NAMED']]


def validate(plan, original):
    expected = {'phase': 'P66', 'source_config': 'configs/P29_stateful_code_v01.json',
        'task_ids': ['34d9492_1'], 'arms': ['documented', 'named'], 'run_order': ORDER,
        'reference_runs': ['P64_01_PHOTO_DOCUMENTED', 'P64_02_PHOTO_NAMED'],
        'seed': 42, 'max_calls': 80, 'max_total_tokens': 450000, 'max_wall_seconds': 1800,
        'max_output_tokens': 4096, 'api_budget_by_task': {'34d9492_1': 160},
        'max_setup_seconds': 120, 'max_evaluation_seconds': 180, 'max_idle_wait_seconds': 60,
        'server_max_lifetime_seconds': 5280, 'server_readiness_seconds': 300, 'worker_timeout_seconds': 4800,
        'output_reservation': 'fixed', 'model_usage_receipt': 'streaming_terminal_usage_required',
        'first_call_cache_prompt': False, 'same_arm_later_cache_prompt': True,
        'notification': 'unchanged_P64_static_limits_and_capability_guidance',
        'max_controller_checks_per_condition': 80, 'max_public_events_per_check': 4000,
        'max_controller_completion_attempts': 1,
        'controller_check_boundary': 'after_whole_model_message_execution_before_next_generation',
        'controller_action': {'app': 'supervisor', 'api': 'complete_task', 'args': {'status': 'success'}},
        'unknown_or_unsupported_policy': 'continue_ordinary_agent_without_extra_hint_or_request',
        'controller_completion_failure_policy': 'stop_condition_and_remaining_schedule_without_retry',
        'reserved_scenarios_read': 0, 'novel_method_claim': False}
    if any(plan.get(k) != v for k, v in expected.items()): raise ValueError('fixed P66 protocol changed')
    for k in ('seed', 'max_calls', 'max_total_tokens', 'max_wall_seconds', 'max_output_tokens'):
        if plan[k] != original[k]: raise ValueError('original budget/seed differs')
    if plan['api_budget_by_task']['34d9492_1'] != original['api_budget_by_task']['34d9492_1']:
        raise ValueError('original API budget differs')


def sources(storage):
    _, original, tasks, tools = baseline_sources(storage)
    plan = read(ROOT / PLAN); validate(plan, original)
    for path, digest in plan['source_code_sha256'].items():
        if sha(ROOT / path) != digest: raise ValueError('public checker/interface changed')
    for name, key in [('reports/P64_public_name_audit.json', 'reference_audit_sha256'),
                      ('reports/P65_public_move_scope.json', 'public_scope_sha256')]:
        if sha(ROOT / name) != plan[key]: raise ValueError('closed reference changed')
    audit = read(ROOT / 'reports/P64_public_name_audit.json')
    if audit['audit_errors'] or not audit['server_stopped'] or audit['owned_server_processes_present']:
        raise ValueError('closed P64 reference audit required')
    if sha(ROOT / 'reports/P64_public_name_comparison.json') != audit['source_report_sha256']:
        raise ValueError('closed baseline raw report changed')
    scope = read(ROOT / 'reports/P65_public_move_scope.json')
    for app, digest in scope['public_implementation_sha256'].items():
        path = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps' / app / 'apis.py'
        if sha(path) != digest: raise ValueError('public API semantics changed')
    return plan, original, {'34d9492_1': tasks['34d9492_1']}, tools


def can_continue_batch(summary):
    if summary.get('unknown_effect_events'): return False
    if summary['stop_reason'] == 'controller_declared_complete':
        return (summary['setup']['status'] == 'matched_public_task_start'
                and summary['declared_complete'] and not summary['unknown_effect_requests']
                and summary['controller_completion_attempts'] == 1)
    return baseline_continue(summary)

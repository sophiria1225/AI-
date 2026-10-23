"""Fixed P71 terminal-state diagnostic; unknown tokens never license effects."""

SOURCE_TASKS = (
    ('P71_01_DETAILS_OMITTED_KEEP', '34d9492_1'),
    ('P71_02_FULL_KEEP', '3c13f5a_1'),
    ('P71_02_DETAILS_OMITTED_KEEP', '3c13f5a_1'),
    ('P71_02_DETAILS_AND_LISTINGS_OMITTED_KEEP', '3c13f5a_1'),
    ('P71_04_FULL_KEEP', '6104387_1'),
    ('P71_04_DETAILS_OMITTED_KEEP', '6104387_1'),
    ('P71_04_DETAILS_AND_LISTINGS_OMITTED_KEEP', '6104387_1'),
)


def fixed_cases(plan):
    expected = {
        'phase': 'P72', 'batch_id': 'P72_public_completion_scope_v01',
        'source_runs': [s for s, _ in SOURCE_TASKS],
        'source_task_ids': dict(SOURCE_TASKS),
        'completion_reference': 'P71_01_DETAILS_AND_LISTINGS_OMITTED_KEEP',
        'arms': ['no_completion', 'append_completion'],
        'completion_action': {'name': 'supervisor__complete_task', 'arguments': '{"status": "success"}'},
        'environment_seed': 42, 'max_cases': 14,
        'max_api_requests_per_case': 120, 'max_total_api_requests': 1680,
        'max_execution_seconds_per_case': 120, 'max_cleanup_seconds_per_case': 45,
        'max_evaluation_seconds_per_case': 180, 'max_batch_seconds': 1800,
        'expected_replay_api_requests': 702, 'expected_intervention_api_requests': 7,
        'model_generations': 0, 'reserved_scenarios_read': 0,
        'source_outcome_scope_sha256': '7829aeb42e7852cfd8a78390a05044146b72ea31269998f6fee24053f51afaa0',
        'source_audit_sha256': '25f99601a1a53fc0e9f58f9ab6ccbe06744fcbb6348657c8c2eb47ddab3c9e0e',
    }
    if any(plan.get(k) != v for k, v in expected.items()):
        raise ValueError('outside fixed all-uncompleted P71 diagnostic')
    return [dict(source_run=source, task_id=task, arm=arm,
                 run_id=f'P72_{number:02d}_{arm.upper()}')
            for number, (source, task, arm) in enumerate(
                [(source, task, arm) for source, task in SOURCE_TASKS for arm in plan['arms']], 1)]


def verify_complete_selection(audit, plan):
    fixed_cases(plan)
    if (audit['phase'] != 'P71' or audit['batch_status'] != 'complete'
            or audit['audit_errors'] or audit['record_status_counts'] != {'evaluated': 12}
            or not audit['all_planned_cells_accounted'] or len(audit['rows']) != 12
            or len({r['run_id'] for r in audit['rows']}) != 12):
        raise ValueError('complete closed source cohort required')
    # Selection is based on sent completion requests, never on a hidden score.
    selected = [(r['run_id'], r['task_id']) for r in audit['rows']
                if r['sent_api_names'].get('supervisor__complete_task', 0) == 0]
    if selected != list(SOURCE_TASKS):
        raise ValueError('all uncompleted sources must be retained in fixed order')


def verify_source_usage(summary, usage, events):
    if (summary['unknown_effect_requests'] or any(e['effects_unknown'] for e in events)
            or summary['model_calls'] != len(usage)
            or summary['stop_reason'] in ('runtime_error', 'cleanup_error', 'setup_failure')
            or summary['setup']['status'] != 'matched_observable_prefix'):
        raise ValueError('unknown effects or invalid source execution cannot be replayed')
    unknown = [u for u in usage if u['status'] != 'ok']
    if len(unknown) != summary['unknown_usage_calls']:
        raise ValueError('source unknown-use accounting differs')
    if unknown:
        last = unknown[0]
        if (len(unknown) != 1 or last != usage[-1]
                or summary['stop_reason'] not in ('wall_limit_during_model_call', 'model_usage_unknown')
                or any(e['call'] == last['id'] for e in events)
                or any(last[k] is not None for k in ('input_tokens', 'output_tokens'))):
            raise ValueError('unknown generation must be terminal, unexecuted and unimputed')
    return len(unknown)

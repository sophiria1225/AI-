"""P122: fixed seed sensitivity of the unchanged P120 checkpoint controls.

Three repetitions are descriptive, conditional on four known tasks. They do
not establish statistical noninferiority, unseen-task transfer, or novelty.
"""
from statistics import mean, median, stdev

from whole_task_required_inline_checkpoint import (
    POLICIES, ERROR_POLICY, initial_conversation, make_notification,
    original_worker_config, summarize as summarize_repetition,
    validate_plan as validate_original_plan,
)
from receipt_reasoning_history import require

SEEDS = (57, 157, 257)
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')


def run_order():
    return [(rep, number, policy) for rep in range(1, 4) for number in range(1, 5)
            for policy in (POLICIES if (number + rep) % 2 == 0 else POLICIES[::-1])]


def cell_id(repetition, number, policy):
    require(type(repetition) is int and repetition in range(1, 4)
            and type(number) is int and number in range(1, 5) and policy in POLICIES,
            'outside_fixed_P122_comparison')
    return f'BOC_P122_R{repetition:02d}_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, checkpoint_policy):
    require(plan.get('experiment') == 'P122' and task_id in TASKS,
            'new_P122_plan_and_known_task_required')
    number = TASKS.index(task_id) + 1
    matches = [rep for rep in range(1, 4) if run_id == cell_id(rep, number, checkpoint_policy)]
    require(len(matches) == 1 and plan.get('model_seeds') == list(SEEDS),
            'fixed_P122_seed_and_run_identity_required')
    rep = matches[0]
    config = original_worker_config(original, {**plan, 'model_seed': SEEDS[rep - 1]},
                                    task_id, arm, run_id, 'auto')
    require(config['draft_temperature'] == 0.7
            and plan.get('inline_checkpoint_requirement') == 'required_when_run_python',
            'unchanged_P120_checkpoint_controls_required')
    config.update(checkpoint_policy=checkpoint_policy, read_views_enabled=False,
                  replication_index=rep,
                  inline_checkpoint_requirement='required_when_run_python'
                  if checkpoint_policy == 'inline_checkpoint' else 'not_applicable')
    return config


def config_for(original, plan, task_id, policy, repetition):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(repetition, TASKS.index(task_id) + 1, policy), policy)


def validate_plan(plan):
    expected = dict(experiment='P122', batch_id='P122_batch_v01', repetitions=3,
        model_seeds=list(SEEDS), model_seed=57, max_cells=24, max_model_calls=1920,
        max_reserved_tokens=10800000, max_reserved_environment_api_requests=2400,
        server_max_lifetime_seconds=64800, max_summary_calls_in_batch=12,
        required_closed_diagnostic='reports/P120_pair_controls.json',
        required_predecessor_phase='P120',
        primary_question='required_inline_checkpoint_seed_sensitivity_on_all_four_known_tasks',
        prior_P120_pooled_into_primary_analysis=False,
        aggregate_after_all_24_slots_and_server_close=True,
        inferential_noninferiority_claim=False, confidence_intervals_reported=False,
        statistical_significance_claim=False, adaptive_extension=False)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in expected.items()),
            'fixed_P122_replication_scope_changed')
    shadow = {**plan, 'experiment': 'P120', 'batch_id': 'P120_batch_v01',
        'repetitions': 1, 'max_cells': 8, 'max_model_calls': 640,
        'max_reserved_tokens': 3600000, 'max_reserved_environment_api_requests': 800,
        'server_max_lifetime_seconds': 21600, 'max_summary_calls_in_batch': 4,
        'required_closed_diagnostic': 'reports/P119_pair_controls.json',
        'required_predecessor_phase': 'P119',
        'primary_question': 'ordinary_required_inline_versus_separate_checkpoint_whole_task_cost'}
    validate_original_plan(shadow)
    for rel in ('configs/P120_whole_task_required_inline_checkpoint_v01.json',
                'reports/P120_comparison.json', 'reports/P120_server_session.json',
                'reports/P120_pair_controls.json',
                'docs/experiments/P122_checkpoint_replication.md'):
        value = plan.get('source_sha256', {}).get(rel)
        require(type(value) is str and len(value) == 64
                and all(c in '0123456789abcdef' for c in value),
                'P120_and_new_replication_sources_must_be_bound')


def describe(values):
    return {'n': len(values), 'values': values,
            'mean': mean(values) if values else None,
            'median': median(values) if values else None,
            'minimum': min(values) if values else None,
            'maximum': max(values) if values else None,
            'sample_standard_deviation': stdev(values) if len(values) > 1 else None}


def summarize(rows, errors):
    expected = {(rep, TASKS[number - 1], policy) for rep, number, policy in run_order()}
    actual = [(r['repetition'], r['task_id'], r['checkpoint_policy']) for r in rows]
    require(len(actual) == len(set(actual)) == 24 and set(actual) == expected,
            'all_24_P122_slots_required')
    indexed = {(r['repetition'], r['task_id'], r['checkpoint_policy']): r for r in rows}
    repetitions = []
    for rep, seed in enumerate(SEEDS, 1):
        subset = [r for r in rows if r['repetition'] == rep]
        require(all(r['model_seed'] == seed for r in subset), 'P122_row_seed_changed')
        repetitions.append({'repetition': rep, 'model_seed': seed,
                            **summarize_repetition(subset, errors)})
    tasks = []
    for task in TASKS:
        pairs = []
        for rep, seed in enumerate(SEEDS, 1):
            a, b = [indexed[rep, task, policy] for policy in POLICIES]
            evaluated = a['record_status'] == b['record_status'] == 'evaluated'
            known = all(type(r.get('known_total_tokens')) is int
                        and r.get('unknown_usage_calls') == 0 for r in (a, b))
            difference = b['known_total_tokens'] - a['known_total_tokens'] if known else None
            both_success = evaluated and a['success'] is True and b['success'] is True
            pairs.append({'repetition': rep, 'model_seed': seed,
                'both_evaluated': evaluated, 'both_usage_known': known,
                'separate_success': a.get('success'), 'inline_success': b.get('success'),
                'both_successful': both_success,
                'success_lost': evaluated and a['success'] is True and b['success'] is False,
                'difference_tokens': difference,
                'difference_percent_of_separate': 100 * difference / a['known_total_tokens']
                    if known and a['known_total_tokens'] > 0 else None,
                'separate_installed': a.get('checkpoint_installed'),
                'inline_installed': b.get('checkpoint_installed')})
        exact = all(p['both_usage_known'] for p in pairs)
        preserved = all(p['both_successful'] for p in pairs)
        tasks.append({'task_id': task, 'pairs': pairs, 'all_three_cost_pairs_exact': exact,
            'both_successful_in_all_three_pairs': preserved,
            'available_cost_differences': describe([p['difference_tokens'] for p in pairs if p['both_usage_known']]),
            'all_three_cost_differences': describe([p['difference_tokens'] for p in pairs]) if exact else None,
            'all_three_percentage_differences': describe([p['difference_percent_of_separate'] for p in pairs])
                if exact and all(p['difference_percent_of_separate'] is not None for p in pairs) else None,
            'success_preserving_reduction_in_all_three': bool(exact and preserved
                and all(p['difference_tokens'] < 0 and p['inline_installed'] is True for p in pairs))})
    complete = all(r['all_eight_complete_with_known_usage'] for r in repetitions)
    return {'planned_rows': 24, 'unique_known_tasks': 4, 'repetitions': 3,
        'model_seeds': list(SEEDS), 'repetition_summaries': repetitions, 'task_summaries': tasks,
        'all_24_complete_with_known_usage': complete,
        'replication_gate_met': bool(complete and not errors
            and all(r['development_gate_met'] for r in repetitions)
            and tasks[0]['success_preserving_reduction_in_all_three']),
        'photo_reduction_repeated_with_success': tasks[0]['success_preserving_reduction_in_all_three'],
        'prior_P120_pooled_into_primary_analysis': False, 'inferential_noninferiority_claim': False,
        'statistical_significance_claim': False, 'confidence_intervals_reported': False,
        'novel_method_claim': False, 'general_quality_preservation_claim': False,
        'interpretation': 'Three fixed-seed repetitions on four known tasks, with all failures and inactive controls retained. '
            'Descriptive ranges and standard deviations are conditional on these tasks and seeds. '
            'No random-task sampling, confidence-interval coverage, statistical noninferiority or unseen-task transfer is established.'}

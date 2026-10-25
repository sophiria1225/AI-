from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from whole_task_checkpoint_replication import (
    SEEDS, TASKS, POLICIES, cell_id, run_order, config_for, validate_plan, summarize,
)
from whole_task_required_inline_checkpoint import worker_config as prior_config

ROOT = Path(__file__).resolve().parents[1]


def synthetic_plan():
    plan = json.loads((ROOT / 'configs/P120_whole_task_required_inline_checkpoint_v01.json').read_text())
    plan.update(experiment='P122', batch_id='P122_batch_v01', repetitions=3,
        model_seeds=list(SEEDS), max_cells=24, max_model_calls=1920,
        max_reserved_tokens=10800000, max_reserved_environment_api_requests=2400,
        server_max_lifetime_seconds=64800, max_summary_calls_in_batch=12,
        required_closed_diagnostic='reports/P120_pair_controls.json',
        required_predecessor_phase='P120',
        primary_question='required_inline_checkpoint_seed_sensitivity_on_all_four_known_tasks',
        prior_P120_pooled_into_primary_analysis=False,
        aggregate_after_all_24_slots_and_server_close=True,
        inferential_noninferiority_claim=False, confidence_intervals_reported=False,
        statistical_significance_claim=False, adaptive_extension=False)
    for name in ('configs/P120_whole_task_required_inline_checkpoint_v01.json',
                 'reports/P120_comparison.json', 'reports/P120_server_session.json',
                 'reports/P120_pair_controls.json', 'docs/experiments/P122_checkpoint_replication.md'):
        plan['source_sha256'][name] = 'a' * 64
    return plan


def rows():
    return [{'run_id': cell_id(rep, n, policy), 'repetition': rep, 'model_seed': SEEDS[rep - 1],
             'task_id': TASKS[n - 1], 'checkpoint_policy': policy,
             'record_status': 'evaluated', 'success': True, 'unknown_usage_calls': 0,
             'checkpoint_installed': policy == 'inline_checkpoint',
             'request_checks': [{'inline_offered': policy == 'inline_checkpoint'}],
             'known_total_tokens': 100 if policy == 'single_checkpoint' else 100 - 5 * rep}
            for rep, n, policy in run_order()]


class CheckpointReplicationTests(unittest.TestCase):
    def test_fixed_schedule_covers_each_task_and_seed_and_reverses_middle_order(self):
        order = run_order()
        self.assertEqual(len(order), 24)
        self.assertEqual(len({cell_id(*r) for r in order}), 24)
        self.assertEqual(order[:2], [(1, 1, POLICIES[0]), (1, 1, POLICIES[1])])
        self.assertEqual(order[8:10], [(2, 1, POLICIES[1]), (2, 1, POLICIES[0])])
        for rep in range(1, 4):
            self.assertEqual({(n, p) for r, n, p in order if r == rep},
                             {(n, p) for n in range(1, 5) for p in POLICIES})

    def test_seed_extensions_and_quality_claims_cannot_change_after_fixing(self):
        plan = synthetic_plan()
        validate_plan(plan)
        for key, value in [('model_seeds', [57, 158, 257]), ('repetitions', 4),
                           ('adaptive_extension', True), ('prior_P120_pooled_into_primary_analysis', True),
                           ('max_cells', 16), ('server_max_lifetime_seconds', 86400),
                           ('inferential_noninferiority_claim', True), ('trigger_input_tokens', 8192)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan, key: value})

    def test_actual_worker_controls_match_P120_for_each_prespecified_seed(self):
        original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
        original['api_budget_by_task'] = {t: 160 if i == 0 else 80 for i, t in enumerate(TASKS)}
        plan = synthetic_plan()
        prior = json.loads((ROOT / 'configs/P120_whole_task_required_inline_checkpoint_v01.json').read_text())
        for rep, n, policy in run_order():
            actual = config_for(original, plan, TASKS[n - 1], policy, rep)
            expected = prior_config(original, {**prior, 'model_seed': SEEDS[rep - 1]},
                TASKS[n - 1], 'error_exception', f'BOC_P120_{n:02d}_{policy.upper()}', policy)
            self.assertEqual(actual.pop('replication_index'), rep)
            self.assertEqual(actual, expected)

    def test_descriptive_pair_statistics_keep_all_three_seeds(self):
        result = summarize(rows(), [])
        self.assertTrue(result['replication_gate_met'])
        photo = result['task_summaries'][0]
        self.assertEqual(photo['all_three_cost_differences'], {
            'n': 3, 'values': [-5, -10, -15], 'mean': -10, 'median': -10,
            'minimum': -15, 'maximum': -5, 'sample_standard_deviation': 5.0})
        self.assertFalse(result['statistical_significance_claim'])
        self.assertFalse(result['inferential_noninferiority_claim'])

    def test_one_success_loss_fails_even_if_total_cost_is_lower(self):
        data = rows()
        bad = next(r for r in data if r['repetition'] == 2 and r['task_id'] == TASKS[3]
                   and r['checkpoint_policy'] == 'inline_checkpoint')
        bad.update(success=False, known_total_tokens=1)
        result = summarize(data, [])
        self.assertFalse(result['replication_gate_met'])
        self.assertTrue(result['task_summaries'][3]['pairs'][1]['success_lost'])
        self.assertTrue(result['photo_reduction_repeated_with_success'])

    def test_one_unknown_cost_keeps_primary_three_pair_statistic_unknown(self):
        data = rows()
        next(r for r in data if r['repetition'] == 3 and r['task_id'] == TASKS[0]
             and r['checkpoint_policy'] == 'inline_checkpoint')['unknown_usage_calls'] = 1
        result = summarize(data, [])
        self.assertFalse(result['replication_gate_met'])
        self.assertIsNone(result['task_summaries'][0]['all_three_cost_differences'])
        self.assertEqual(result['task_summaries'][0]['available_cost_differences']['n'], 2)
        self.assertFalse(result['photo_reduction_repeated_with_success'])

    def test_missing_duplicate_or_wrong_seed_is_rejected(self):
        for data in [rows()[:-1], rows()[:-1] + [deepcopy(rows()[0])]]:
            with self.assertRaises(ValueError): summarize(data, [])
        data = rows(); data[0]['model_seed'] = 58
        with self.assertRaises(ValueError): summarize(data, [])

    def test_unrun_slots_and_inactive_controls_do_not_pass(self):
        data = rows()
        data[-1].update(record_status='not_run', success=None, known_total_tokens=None,
                        unknown_usage_calls=None, checkpoint_installed=None)
        self.assertFalse(summarize(data, [])['replication_gate_met'])
        data = rows()
        for row in data: row['checkpoint_installed'] = False
        self.assertFalse(summarize(data, [])['replication_gate_met'])
        self.assertFalse(summarize(data, [])['photo_reduction_repeated_with_success'])


if __name__ == '__main__':
    unittest.main()

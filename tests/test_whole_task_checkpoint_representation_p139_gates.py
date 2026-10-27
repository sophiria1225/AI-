"""Handwritten scientific counterexamples; no study execution or task values."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whole_task_checkpoint_representation_p139 import (MODES, TASKS, representation_prefix_match,
                                                       summarize)


def prefix(timing):
    n = 8 if timing == 'threshold' else 7
    return dict(after_model_calls=n, previous_cutoff=10, candidate_cutoff=16,
        accumulated_exposure=1000, previous_focus_cost=800,
        first_checkpoint=dict(opportunity_index=1, cutoff=10,
            summary_note_sha256='a'*64, summary_notes_sha256='b'*64, after_model_calls=4,
            fragment_budget=dict(fragment_count=1, body_characters=100,
                body_sha256='c'*64, field_item_counts={k: 1 for k in
                    ('completed', 'usable_state', 'remaining', 'uncertainties')})),
        prior_request_output_sequence=[dict(call_id=f'call_{i+1:03d}',
            role='focus' if i == 3 else 'agent', status='ok', request_sha256='d'*64,
            known_assistant_message_sha256='e'*64) for i in range(n)],
        all_prior_terminal_usage_known=True, prior_summary_notes_sha256='b'*64)


def rows():
    costs = dict(zip(MODES, (1000, 900, 850, 700)))
    result = []
    for task in TASKS:
        for mode in MODES:
            timing, representation = mode.split('_')
            result.append(dict(task_id=task, checkpoint_representation_mode=mode,
                record_status='evaluated', success=True, unknown_usage_calls=0,
                known_total_tokens=costs[mode], prefix_exposure_contract_failed=False,
                prefix_exposure_accounting_complete=True,
                checkpoint_representation_contract_failed=False,
                checkpoint_representation_accounting_complete=True,
                actual_decision_differences_from_threshold=int(timing == 'exposure'),
                actual_decision_differences_from_exposure=int(timing == 'threshold'),
                actual_delta_known_actor_calls=2 if representation == 'delta' else 0,
                representation_second_opportunity=prefix(timing)))
    return result


def comparison(result, name):
    return next(c for c in result['comparisons'] if c['name'] == name)


class RepresentationGateTests(unittest.TestCase):
    def test_positive_full_factorial_keeps_all_five_comparisons(self):
        result = summarize(rows(), [])
        self.assertEqual(result['planned_rows'], 16)
        self.assertEqual(result['independent_tasks'], 4)
        self.assertTrue(result['primary_utility_gate_met'])
        self.assertTrue(result['combination_development_gate_met'])
        self.assertEqual(len(result['comparisons']), 5)
        self.assertTrue(all(c['comparison_gate_met'] for c in result['comparisons']))
        self.assertFalse(result['novel_method_claim'])
        self.assertFalse(result['independent_replication_claim'])

    def test_primary_pass_does_not_hide_failure_against_one_additional_control(self):
        data = rows()
        for r in data:
            if r['checkpoint_representation_mode'] == 'threshold_delta':
                r['known_total_tokens'] = 600
        result = summarize(data, [])
        self.assertTrue(result['primary_utility_gate_met'])
        self.assertFalse(result['combination_development_gate_met'])
        self.assertFalse(comparison(result, 'timing_with_delta')['comparison_gate_met'])

    def test_missing_duplicate_or_replaced_slot_is_rejected(self):
        for data in (rows()[:-1], rows()[:-1]+[rows()[0]], rows()+[rows()[0]]):
            with self.assertRaises(ValueError): summarize(data, [])

    def test_all_unstarted_rows_remain_sixteen_with_exact_null_totals(self):
        data = rows()
        for r in data:
            r.update(record_status='not_run', success=None, unknown_usage_calls=None,
                known_total_tokens=None, prefix_exposure_accounting_complete=None,
                checkpoint_representation_accounting_complete=None,
                actual_delta_known_actor_calls=None, representation_second_opportunity=None)
        result = summarize(data, [])
        self.assertEqual(result['usage_count_missing_conditions'], 16)
        self.assertEqual(result['recorded_unknown_usage_calls'], 0)
        self.assertTrue(all(v is None for v in result['total_tokens_by_mode'].values()))
        self.assertTrue(all(c['all_task_token_difference'] is None and
                            c['common_success_token_difference'] is None for c in result['comparisons']))
        self.assertFalse(result['development_gate_met'])

    def test_known_subtotal_and_unknown_are_separate_and_no_exact_difference_is_imputed(self):
        data = rows(); data[-1]['unknown_usage_calls'] = 1
        result = summarize(data, [])
        self.assertEqual(result['known_token_subtotals_by_mode']['exposure_delta'], 2800)
        self.assertEqual(result['recorded_unknown_usage_calls'], 1)
        self.assertTrue(all(v is None for v in result['total_tokens_by_mode'].values()))
        primary = comparison(result, 'primary_utility')
        self.assertIsNone(primary['all_task_token_difference'])
        self.assertIsNone(primary['common_success_token_difference'])
        self.assertFalse(result['primary_utility_gate_met'])

    def test_equal_success_counts_with_task_swap_still_fails_quality_preservation(self):
        data = rows()
        for r in data:
            if (r['task_id'], r['checkpoint_representation_mode']) in (
                (TASKS[0], 'threshold_recursive'), (TASKS[1], 'exposure_delta')):
                r['success'] = False
        result = summarize(data, [])
        self.assertEqual(result['success_counts']['threshold_recursive'], 3)
        self.assertEqual(result['success_counts']['exposure_delta'], 3)
        self.assertEqual(sum(p['success_lost'] for p in comparison(result, 'primary_utility')['pairs']), 1)
        self.assertFalse(result['primary_utility_gate_met'])

    def test_cheap_failed_task_is_in_whole_cost_but_cannot_pass_quality_gate(self):
        data = rows(); data[-1].update(success=False, known_total_tokens=1)
        result = summarize(data, [])
        self.assertLess(comparison(result, 'primary_utility')['all_task_token_difference'], 0)
        self.assertFalse(result['primary_utility_gate_met'])

    def test_empty_common_success_has_null_not_zero_effect(self):
        data = rows()
        for r in data: r['success'] = False
        result = summarize(data, [])
        for c in result['comparisons']:
            self.assertEqual(c['common_success_tasks'], [])
            self.assertIsNone(c['common_success_token_difference'])
            self.assertFalse(c['comparison_gate_met'])

    def test_cost_reduction_only_on_both_failed_task_does_not_pass_common_condition(self):
        data = rows()
        for r in data:
            if r['checkpoint_representation_mode'] == 'exposure_delta':
                r['known_total_tokens'] = 1000
            if r['task_id'] == TASKS[-1]:
                r['success'] = False
                if r['checkpoint_representation_mode'] == 'exposure_delta': r['known_total_tokens'] = 1
        result = summarize(data, [])
        p = comparison(result, 'primary_utility')
        self.assertLess(p['all_task_token_difference'], 0)
        self.assertEqual(p['common_success_token_difference'], 0)
        self.assertFalse(p['comparison_gate_met'])

    def test_delta_installation_or_unknown_dispatch_without_known_actor_exposure_is_not_activity(self):
        data = rows()
        for r in data:
            r['actual_delta_known_actor_calls'] = 0
            r['delta_installations'] = 1
            r['actual_delta_unknown_actor_calls'] = 2
        result = summarize(data, [])
        self.assertFalse(comparison(result, 'representation_at_exposure')['comparison_gate_met'])
        self.assertFalse(comparison(result, 'representation_at_threshold')['comparison_gate_met'])
        self.assertFalse(result['combination_development_gate_met'])

    def test_shadow_timing_difference_without_actual_dispatch_is_not_activity(self):
        data = rows()
        for r in data:
            r['actual_decision_differences_from_threshold'] = 0
            r['decision_differences_from_threshold'] = 10
        result = summarize(data, [])
        self.assertFalse(comparison(result, 'timing_with_delta')['comparison_gate_met'])
        self.assertFalse(comparison(result, 'timing_with_recursive')['comparison_gate_met'])

    def test_prefix_absence_divergence_and_unknown_are_not_matching_representation_boundaries(self):
        for change in ('missing', 'different', 'unknown', 'first_absent'):
            data = rows(); r = data[-1]
            if change == 'missing': r['representation_second_opportunity'] = None
            elif change == 'different': r['representation_second_opportunity']['candidate_cutoff'] += 2
            elif change == 'unknown': r['representation_second_opportunity']['all_prior_terminal_usage_known'] = False
            else: r['representation_second_opportunity']['first_checkpoint'] = None
            result = summarize(data, [])
            self.assertFalse(comparison(result, 'representation_at_exposure')['comparison_gate_met'])
            self.assertFalse(result['combination_development_gate_met'])

    def test_prefix_mismatch_on_activated_failed_task_is_not_discarded(self):
        data = rows()
        for r in data:
            if r['task_id'] == TASKS[-1] and r['checkpoint_representation_mode'].startswith('exposure'):
                r['success'] = False
        data[-1]['representation_second_opportunity']['candidate_cutoff'] += 2
        result = summarize(data, [])
        c = comparison(result, 'representation_at_exposure')
        self.assertFalse(c['all_activated_representation_prefixes_match'])
        self.assertFalse(c['comparison_gate_met'])

    def test_boolean_usage_tokens_success_and_activity_do_not_count_as_numeric_evidence(self):
        for key in ('unknown_usage_calls', 'known_total_tokens', 'success'):
            data = rows()
            data[-1][key] = 1 if key == 'success' else (False if key == 'unknown_usage_calls' else True)
            self.assertFalse(summarize(data, [])['primary_utility_gate_met'])
        for key in ('actual_delta_known_actor_calls', 'actual_decision_differences_from_threshold'):
            data = rows()
            for r in data: r[key] = True
            result = summarize(data, [])
            name = 'representation_at_exposure' if key == 'actual_delta_known_actor_calls' else 'timing_with_delta'
            self.assertFalse(comparison(result, name)['comparison_gate_met'])

    def test_exact_contract_flags_are_required(self):
        for key, bad in (('prefix_exposure_contract_failed', 0),
                         ('prefix_exposure_accounting_complete', 1),
                         ('checkpoint_representation_contract_failed', 0),
                         ('checkpoint_representation_accounting_complete', 1)):
            data = rows(); data[-1][key] = bad
            self.assertFalse(summarize(data, [])['primary_utility_gate_met'])

    def test_audit_errors_cannot_be_suppressed_by_falsey_nonlist(self):
        self.assertFalse(summarize(rows(), ['synthetic audit failure'])['development_gate_met'])
        for errors in (False, None, '', 0):
            with self.assertRaises(ValueError): summarize(rows(), errors)

    def test_prefix_nested_bool_integer_coercion_is_not_equality(self):
        a, b = deepcopy(rows()[2]), deepcopy(rows()[3])
        b['representation_second_opportunity']['first_checkpoint']['opportunity_index'] = True
        self.assertFalse(representation_prefix_match(a, b))
        a['representation_second_opportunity']['first_checkpoint']['opportunity_index'] = True
        self.assertFalse(representation_prefix_match(a, b))

    def test_empty_first_checkpoint_is_not_evidence_of_an_accepted_summary(self):
        a, b = deepcopy(rows()[2]), deepcopy(rows()[3])
        for r in (a, b):
            r['representation_second_opportunity']['first_checkpoint'] = {}
        self.assertFalse(representation_prefix_match(a, b))

    def test_empty_request_prefix_is_not_evidence_of_matched_paid_prefix(self):
        a, b = deepcopy(rows()[2]), deepcopy(rows()[3])
        for r in (a, b):
            r['representation_second_opportunity']['prior_request_output_sequence'] = []
        self.assertFalse(representation_prefix_match(a, b))


if __name__ == '__main__':
    unittest.main()

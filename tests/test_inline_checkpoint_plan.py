from copy import deepcopy
import json
from pathlib import Path
import unittest

from build_inline_checkpoint_summary import aggregate
from inline_checkpoint_preflight import synthetic_transport_cases
from inline_checkpoint_history import BOUNDARY
from whole_task_inline_checkpoint import run_order, cell_id, summarize, validate_plan


def synthetic_plan():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / 'configs/P118_whole_task_single_checkpoint_v01.json').read_text())
    plan.update(experiment='P119', batch_id='P119_batch_v01',
        checkpoint_policies=['single_checkpoint', 'inline_checkpoint'],
        primary_question='ordinary_inline_versus_separate_checkpoint_whole_task_cost',
        required_closed_diagnostic='reports/P118_pair_controls.json', required_predecessor_phase='P118',
        inline_metadata_policy='optional_exactly_one_run_python_old_closed_prefix_only',
        inline_transport_display='remove_metadata_from_both_next_input_candidates_preserve_raw_archive',
        inline_installation='after_current_turn_closes_and_next_input_is_strictly_shorter',
        same_call_results_summarized=False, separate_semantic_judge=False)
    for name in ('scripts/inline_checkpoint_history.py', 'scripts/inline_checkpoint_inference.py',
                 'scripts/inline_checkpoint_protocol.py', 'scripts/inline_checkpoint_execution.py',
                 'scripts/audit_inline_checkpoint_trace.py', 'reports/P118_comparison.json',
                 'reports/P118_server_session.json', 'reports/P118_pair_controls.json',
                 'docs/experiments/P119_whole_task_inline_checkpoint.md'):
        plan['source_sha256'][name] = 'a' * 64
    return plan


def rows():
    return [{'run_id': cell_id(n, p), 'task_id': f'synthetic-{n}', 'checkpoint_policy': p,
             'record_status': 'evaluated', 'success': True, 'unknown_usage_calls': 0,
             'known_total_tokens': 100 if p == 'single_checkpoint' else 95}
            for n, p in run_order()]


class InlineCheckpointPlanTests(unittest.TestCase):
    def test_controls_are_fixed_and_same_call_prediction_or_free_judging_is_excluded(self):
        plan = synthetic_plan()
        validate_plan(plan)
        for key, value in [('max_summary_opportunities_per_cell', 2), ('trigger_input_tokens', 8192),
                           ('same_call_results_summarized', True), ('separate_semantic_judge', True),
                           ('novel_method_claim', True), ('reserved_scenarios_read', 1),
                           ('checkpoint_policies', ['full', 'inline_checkpoint'])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan, key: value})

    def test_quality_loss_unknown_or_missing_slot_cannot_pass(self):
        data = rows()
        self.assertTrue(summarize(data, [])['development_gate_met'])
        lost = deepcopy(data)
        next(r for r in lost if r['checkpoint_policy'] == 'inline_checkpoint')['success'] = False
        self.assertFalse(summarize(lost, [])['development_gate_met'])
        unknown = deepcopy(data); unknown[0]['unknown_usage_calls'] = 1
        result = summarize(unknown, [])
        self.assertFalse(result['development_gate_met'])
        self.assertIsNone(result['inline_checkpoint_minus_single_checkpoint_whole_task_tokens'])
        with self.assertRaises(ValueError): summarize(data[:-1], [])

    def test_lower_failed_task_cost_cannot_hide_more_expensive_paired_successes(self):
        data = rows()
        for row in data:
            if row['task_id'] == 'synthetic-1':
                row['success'] = False
                row['known_total_tokens'] = 100 if row['checkpoint_policy'] == 'single_checkpoint' else 1
            else:
                row['known_total_tokens'] = 100 if row['checkpoint_policy'] == 'single_checkpoint' else 101
        result = summarize(data, [])
        self.assertLess(result['inline_checkpoint_minus_single_checkpoint_whole_task_tokens'], 0)
        self.assertGreater(result['paired_successful_token_difference'], 0)
        self.assertFalse(result['development_gate_met'])

    def test_materials_keep_unknown_and_unrun_slots(self):
        data = rows(); data[0]['unknown_usage_calls'] = 1
        self.assertIsNone(aggregate(data)['exact_all_condition_tokens'])
        data[0].update(known_total_tokens=None, unknown_usage_calls=None, success=None, record_status='not_run')
        self.assertEqual(aggregate(data)['accounted_conditions'], 7)
        self.assertIsNone(aggregate(data)['exact_all_condition_tokens'])

    def test_three_synthetic_transport_cases_do_not_execute_code_or_predict_current_result(self):
        cases = synthetic_transport_cases()
        self.assertEqual([c['name'] for c in cases],
                         ['inline_offer', 'ordinary_after_inline', 'compacted_after_inline'])
        self.assertTrue(any(m.get('content') == BOUNDARY for m in cases[0]['messages']))
        self.assertIn('checkpoint', cases[0]['tools'][0]['function']['parameters']['properties'])
        self.assertEqual(cases[1]['messages'][-1], cases[2]['messages'][-1])
        for case in cases[1:]:
            self.assertNotIn('checkpoint', case['tools'][0]['function']['parameters']['properties'])
            for message in case['messages']:
                for call in message.get('tool_calls') or []:
                    self.assertNotIn('checkpoint', json.loads(call['function']['arguments']))


if __name__ == '__main__':
    unittest.main()

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_single_checkpoint_summary import aggregate
from whole_task_single_checkpoint import run_order, cell_id, summarize, validate_plan


def synthetic_plan():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / 'configs/P111_whole_task_receipt_history_v01.json').read_text())
    plan.update(experiment='P118', batch_id='P118_batch_v01',
        checkpoint_policies=['full', 'single_checkpoint'], max_cells=8, max_model_calls=640,
        max_reserved_tokens=3600000, max_reserved_environment_api_requests=800,
        server_max_lifetime_seconds=21600,
        primary_question='ordinary_single_checkpoint_including_shared_control_cost',
        required_closed_diagnostic='reports/P117_public_metadata_observations.json',
        required_predecessor_phase='P114', trigger_input_tokens=16384, retained_recent_turns=2,
        max_summary_characters=8192, max_summary_opportunities_per_cell=1,
        max_summary_calls_in_batch=4, shared_model_call_and_token_budget=True,
        summary_output_cap=4096, summary_temperature=0.7,
        invalid_summary_policy='keep_original_no_retry_charge_known_cost',
        unknown_summary_usage_policy='stop_without_retry', novel_method_claim=False)
    for name in ('scripts/single_checkpoint_history.py', 'scripts/single_checkpoint_inference.py',
                 'reports/P114_comparison.json', 'reports/P114_server_session.json',
                 'reports/P117_public_metadata_observations.json', 'docs/P14_findings.md',
                 'docs/counterfactual_adaptation_prior_scope_20261025.md',
                 'docs/experiments/P118_whole_task_single_checkpoint.md'):
        plan['source_sha256'][name] = 'a' * 64  # Synthetic validator input, never a run plan.
    return plan


def synthetic_rows():
    return [{'run_id': cell_id(n, p), 'task_id': f'synthetic-{n}', 'checkpoint_policy': p,
             'record_status': 'evaluated', 'success': True, 'unknown_usage_calls': 0,
             'known_total_tokens': 100 if p == 'full' else 95}
            for n, p in run_order()]


class SingleCheckpointPlanTests(unittest.TestCase):
    def test_shared_limits_trigger_no_retry_and_holdout_scope_are_fixed(self):
        plan = synthetic_plan()
        validate_plan(plan)
        for key, value in [('max_summary_opportunities_per_cell', 2), ('trigger_input_tokens', 8192),
                           ('shared_model_call_and_token_budget', False), ('novel_method_claim', True),
                           ('reserved_scenarios_read', 1), ('summary_temperature', 1.0)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan, key: value})

    def test_cheap_failure_or_unknown_cannot_satisfy_ordinary_control_criterion(self):
        rows = synthetic_rows()
        self.assertTrue(summarize(rows, [])['development_gate_met'])
        lost = deepcopy(rows)
        next(r for r in lost if r['checkpoint_policy'] == 'single_checkpoint')['success'] = False
        self.assertFalse(summarize(lost, [])['development_gate_met'])
        unknown = deepcopy(rows)
        unknown[0]['unknown_usage_calls'] = 1
        result = summarize(unknown, [])
        self.assertFalse(result['development_gate_met'])
        self.assertIsNone(result['single_checkpoint_minus_full_whole_task_tokens'])
        self.assertFalse(result['novel_method_claim'])
        with self.assertRaises(ValueError):
            summarize(rows[:-1], [])

    def test_reporting_does_not_turn_unknown_or_unrun_slots_into_zero_cost(self):
        rows = synthetic_rows()
        self.assertEqual(aggregate(rows)['exact_all_condition_tokens'], 780)
        rows[0]['unknown_usage_calls'] = 1
        self.assertIsNone(aggregate(rows)['exact_all_condition_tokens'])
        rows[0].update(known_total_tokens=None, unknown_usage_calls=None, success=None, record_status='not_run')
        total = aggregate(rows)
        self.assertFalse(total['all_conditions_accounted'])
        self.assertEqual(total['accounted_conditions'], 7)
        self.assertIsNone(total['exact_all_condition_tokens'])


if __name__ == '__main__':
    unittest.main()

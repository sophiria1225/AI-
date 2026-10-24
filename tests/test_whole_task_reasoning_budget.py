import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixed_budget_inference import FixedBudgetInference
from fixed_budget_local_llama import count_input, model_call, payload_for
from local_llama import payload_for as original_payload
from whole_task_reasoning_budget import (POLICIES, BUDGETS, REQUIRED_SOURCES, cell_id,
    config_for, run_order, summarize, validate_plan)
from protocol_stable_history import StableReferenceConversation

ROOT = Path(__file__).resolve().parents[1]


def plan():
    return json.loads((ROOT / 'configs/P88_whole_task_reasoning_budget_v01.json').read_text())


def rows():
    return [dict(run_id=cell_id(n, p), task_id=str(n), reasoning_policy=p,
        record_status='evaluated', success=True, unknown_usage_calls=0, known_total_tokens=cost)
        for n in range(1, 5) for p, cost in zip(POLICIES, (100, 80))]


def model_config(budget=2048, output=4096):
    return dict(model='synthetic', temperature=1.0, seed=57, num_predict=output,
                reasoning_budget_tokens=budget, call_timeout_seconds=600)


class WholeTaskReasoningBudgetTests(unittest.TestCase):
    def test_all_four_tasks_get_both_new_conditions_with_alternating_order(self):
        order = run_order()
        self.assertEqual(len(order), 8)
        self.assertEqual(len({cell_id(*x) for x in order}), 8)
        self.assertEqual(order[:4], [(1, 'unlimited'), (1, 'half'), (2, 'half'), (2, 'unlimited')])
        for n, p in [(True, 'half'), (0, 'half'), (5, 'half'), (1, 'other')]:
            with self.assertRaises(ValueError): cell_id(n, p)

    def test_scope_rejects_tuning_extra_tasks_and_unbound_closed_diagnostic(self):
        p = plan(); validate_plan(p)
        for key, value in [('max_cells', 10), ('model_seed', 58), ('reasoning_budget_tokens', [-1, 1024]),
                           ('threshold_search', True), ('time_visibility', 'measured'), ('repetitions', 2)]:
            with self.assertRaises(ValueError): validate_plan(p | {key: value})
        for name in REQUIRED_SOURCES:
            changed = copy.deepcopy(p); changed['source_sha256'].pop(name)
            with self.assertRaises(ValueError): validate_plan(changed)
        total = sum(p[k] for k in ('max_setup_seconds', 'max_wall_seconds', 'max_cleanup_seconds',
                                   'max_idle_wait_seconds', 'max_evaluation_seconds')) * 8
        self.assertLess(total + 1200, p['server_max_lifetime_seconds'])

    def test_payload_differs_only_in_budget_and_keeps_fixed_budget_at_small_output_cap(self):
        messages = [{'role': 'user', 'content': 'synthetic task'}]
        for output in (4096, 10):
            baseline = original_payload(model_config(-1, output), messages, [])
            for budget in (-1, 2048):
                actual = payload_for(model_config(budget, output), messages, [])
                self.assertEqual(actual.pop('reasoning_budget_tokens'), budget)
                self.assertEqual(actual, baseline)

    def test_missing_or_conflicting_controls_are_rejected_before_io(self):
        cases = [model_config(v) for v in (True, 0, 1024, -2, None)]
        cases += [model_config() | {key: value} for key, value in [
            ('thinking_mode', 'disabled'), ('thinking_budget_tokens', 2048),
            ('reasoning_effort', 'none'), ('reasoning_control', False), ('reasoning_budget_message', '')]]
        with patch('fixed_budget_local_llama.post') as post:
            for config in cases:
                with self.assertRaises(ValueError): count_input(config, [], [])
            post.assert_not_called()

    def test_counting_and_generation_transmit_same_explicit_control(self):
        raw = dict(choices=[{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'ok'}}],
                   usage={'prompt_tokens': 20, 'completion_tokens': 3, 'total_tokens': 23})
        sent = []
        def fake(config, endpoint, payload, timeout):
            sent.append((endpoint, copy.deepcopy(payload), timeout))
            return {'input_tokens': 20} if endpoint.endswith('input_tokens') else raw
        with tempfile.TemporaryDirectory() as temp, patch('fixed_budget_local_llama.post', side_effect=fake), \
             patch('fixed_budget_local_llama.signal.alarm'):
            config = model_config(); messages = [{'role': 'user', 'content': 'synthetic'}]
            self.assertEqual(count_input(config, messages, [])['input_tokens'], 20)
            response = model_call(config, messages, Path(temp), 50, [])
            saved = json.loads((Path(temp) / 'request.json').read_text())
        self.assertEqual(sent[0][1], sent[1][1])
        self.assertEqual(saved['reasoning_budget_tokens'], 2048)
        self.assertEqual(response['input_tokens'], 20)
        self.assertEqual(response['output_tokens'], 3)
        self.assertEqual(sent[1][2], 50)

    def test_transport_failure_preserves_unknown_usage_and_run_deadline_scope(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch('fixed_budget_local_llama.post', side_effect=TimeoutError('synthetic')), \
             patch('fixed_budget_local_llama.signal.alarm'):
            response = model_call(model_config(), [], Path(temp), 25, [])
        self.assertIsNone(response['input_tokens'])
        self.assertIsNone(response['output_tokens'])
        self.assertEqual(response['timeout_scope'], 'run_wall')
        self.assertEqual(response['error_kind'], 'timeout')

    def test_worker_configs_do_not_mutate_source_or_each_other(self):
        p = plan(); original = json.loads((ROOT / p['source_plan']).read_text()); saved = copy.deepcopy(original)
        task = p['known_tasks'][0]['task_id']
        a, b = [config_for(original, p, task, v) for v in POLICIES]
        self.assertEqual(original, saved)
        self.assertEqual([a['model']['reasoning_budget_tokens'], b['model']['reasoning_budget_tokens']], [-1, 2048])
        self.assertEqual(a['time_visibility'], b['time_visibility'])
        self.assertEqual(a['time_visibility'], 'not_exposed')

    def test_in_task_budget_change_and_source_mismatch_stop_before_counting(self):
        p = plan(); original = json.loads((ROOT / p['source_plan']).read_text())
        config = config_for(original, p, p['known_tasks'][0]['task_id'], 'half')
        c = StableReferenceConversation('synthetic', {})
        with tempfile.TemporaryDirectory() as temp:
            infer = FixedBudgetInference(config, Path(temp), conversation=c)
            messages, _ = c.for_model(config['observation_page_characters'])
            with patch('fixed_budget_residual.count_input') as count, patch('fixed_budget_residual.model_call') as send:
                infer.config['model']['reasoning_budget_tokens'] = -1
                with self.assertRaisesRegex(ValueError, 'changed_during_task'): infer.call('agent', messages, [])
                infer.config['model']['reasoning_budget_tokens'] = 2048
                with self.assertRaisesRegex(ValueError, 'bound_source'): infer.call('agent', [], [])
                count.assert_not_called(); send.assert_not_called()

    def test_gate_needs_full_quality_and_usage_instead_of_selected_successes(self):
        self.assertTrue(summarize(rows(), [])['development_gate_met'])
        for kind in ('unknown', 'unevaluated', 'loss', 'all_failed', 'audit', 'cost_increase'):
            data = rows(); errors = []
            if kind == 'unknown': data[1]['unknown_usage_calls'] = 1
            if kind == 'unevaluated': data[1].update(record_status='not_run', success=None, known_total_tokens=None)
            if kind == 'loss': data[1]['success'] = False
            if kind == 'all_failed':
                for row in data: row['success'] = False
            if kind == 'audit': errors = ['synthetic mismatch']
            if kind == 'cost_increase': data[1]['known_total_tokens'] = 1000
            result = summarize(data, errors)
            self.assertFalse(result['development_gate_met'], kind)
            if kind in ('unknown', 'unevaluated'):
                self.assertIsNone(result['half_minus_unlimited_whole_task_tokens'])
        with self.assertRaises(ValueError): summarize(rows()[:-1], [])
        with self.assertRaises(ValueError): summarize(rows()[:-1] + [rows()[0]], [])

    def test_failure_cost_remains_in_the_total_and_separate_contribution(self):
        data = rows()
        for row in data:
            if row['task_id'] == '4': row['success'] = False
        result = summarize(data, [])
        self.assertEqual(result['paired_successful_token_difference'], -60)
        self.assertEqual(result['both_failed_token_difference'], -20)
        self.assertEqual(result['half_minus_unlimited_whole_task_tokens'], -80)
        self.assertFalse(result['novel_method_claim'])
        self.assertFalse(result['general_quality_preservation_claim'])


if __name__ == '__main__':
    unittest.main()

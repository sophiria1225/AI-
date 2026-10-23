import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_reasoning_history_comparison import development_gate
from native_conversation import NativeConversation, recover_turn
from reasoning_comparison import ARMS, ReasoningInference, build_history, prefix_responses, validate_plan
from run_handoff_factors import ROOT, read
from run_reasoning_history_comparison import cell_id, run_order


def history():
    task = {'instruction': 'synthetic only'}; view = NativeConversation('same system', task)
    responses = []
    for n in range(8):
        action = {'name': 'run_python', 'arguments': json.dumps({'code': 'x = 1', 'span_ids': []})}
        response = {'role': 'assistant', 'content': f'visible {n}',
            'tool_calls': [{'id': f'c{n}', 'type': 'function', 'function': action}],
            'reasoning_content': f'PRIVATE_FIXTURE_{n}'}
        view.append(response, [{'id': f's{n}', 'assistant': response['content'], 'action': action,
                                'observation': {'status': 'error', 'error': 'synthetic failure'}}])
        responses.append(response)
    return task, view.messages(), responses


class ReasoningComparisonTests(unittest.TestCase):
    def test_only_reasoning_changes_and_all_public_errors_are_preserved(self):
        task, messages, responses = history(); original = copy.deepcopy((task, messages, responses))
        public = build_history(messages, task, responses, ARMS[0])
        keep = build_history(messages, task, responses, ARMS[1])
        self.assertEqual(public.messages(), messages)
        self.assertEqual([{k: v for k, v in m.items() if k != 'reasoning_content'} for m in keep.messages()], messages)
        for offset in range(2, len(messages), 2):
            self.assertEqual(recover_turn(keep.messages()[offset:offset + 2]),
                             recover_turn(public.messages()[offset:offset + 2]))
        self.assertEqual((task, messages, responses), original)

    def test_policy_applies_to_later_responses_not_only_the_initial_prefix(self):
        task, messages, responses = history()
        for arm in ARMS:
            view = build_history(messages, task, responses, arm)
            response = {'role': 'assistant', 'content': 'later', 'reasoning_content': 'PRIVATE_LATER'}
            view.append(response, [{'id': 'later', 'assistant': 'later', 'action': None,
                                    'observation': {'format_error': 'no tool'}}])
            rendered, _ = view.for_model()
            self.assertEqual('reasoning_content' in rendered[-2], arm == 'reasoning_keep')

    def test_changed_task_future_response_and_reordered_prefix_are_rejected(self):
        task, messages, responses = history()
        cases = [(task, responses + [responses[-1]], ARMS[1]),
                 (task, responses[::-1], ARMS[1]), ({'different': True}, responses, ARMS[1]),
                 (task, responses, 'selective')]
        for new_task, saved, arm in cases:
            with self.assertRaises(ValueError): build_history(messages, new_task, saved, arm)

    def test_prefix_reader_checks_hashes_and_never_loads_the_ninth_response(self):
        _, _, messages = history()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'configs').mkdir(); folder = root / 'records/context_pilot/P29_01_CODE'
            calls = []
            for n, message in enumerate(messages + [{'role': 'assistant', 'content': 'FUTURE'}], 1):
                path = folder / f'call_{n:03d}' / 'response.json'; path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'status': 'ok', 'message': message}))
                if n <= 8: calls.append({'call_id': f'call_{n:03d}', 'recorded_status': 'ok',
                                         'files': {'response.json': hashlib.sha256(path.read_bytes()).hexdigest()}})
            (root / 'configs/P75_reasoning_history_v01.json').write_text(json.dumps({'groups': [
                {'run_id': 'P29_01_CODE', 'source': 'prefix', 'calls': calls}]}))
            with patch('reasoning_comparison.ROOT', root), patch('reasoning_comparison.read', wraps=read) as reader:
                self.assertEqual(prefix_responses(root, {'source_run': 'P29_01_CODE'}), messages)
                self.assertFalse(any('call_009' in str(c.args[0]) for c in reader.call_args_list))
                with self.assertRaises(ValueError): prefix_responses(root, {'source_run': 'P29_02_CODE'})
                (folder / 'call_001/response.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    prefix_responses(root, {'source_run': 'P29_01_CODE'})

    def test_plan_refuses_unequal_budget_extra_trials_or_changed_history_sources(self):
        plan = read(ROOT / 'configs/P76_reasoning_history_v01.json'); validate_plan(plan)
        for change in ({'max_calls': 17}, {'max_total_tokens': 120001}, {'max_wall_seconds': 481},
                       {'arms': ['public_only']}, {'reserved_scenarios_read': 1}, {'max_cells': 9}):
            with self.assertRaises(ValueError): validate_plan(plan | change)
        plan['source_sha256'] = dict(plan['source_sha256']); key = next(iter(plan['source_sha256']))
        plan['source_sha256'][key] = 'changed'
        with self.assertRaises(ValueError): validate_plan(plan)

    def test_order_covers_each_condition_once_and_balances_first_condition(self):
        order = run_order([{'task_id': str(n)} for n in range(4)])
        self.assertEqual(len({cell_id(n, arm) for n, _, arm in order}), 8)
        self.assertEqual([arm for _, _, arm in order[::2]], [ARMS[0], ARMS[1], ARMS[0], ARMS[1]])
        with self.assertRaises(ValueError): run_order([{}, {}, {}])

    def test_unknown_use_is_not_given_an_additional_model_request_in_either_condition(self):
        from residual_output_budget import ResidualInference
        with tempfile.TemporaryDirectory() as temp:
            for arm in ARMS:
                infer = ReasoningInference({'model': {}, 'phase': 'P76'}, Path(temp), arm)
                infer.calls = [{'status': 'error'}]
                with patch('residual_output_budget.model_call') as model:
                    with self.assertRaisesRegex(RuntimeError, 'unknown usage'):
                        ResidualInference.call(infer, 'agent', [], [])
                    model.assert_not_called()


class ReasoningGateTests(unittest.TestCase):
    def rows(self):
        return [{'task_id': str(n), 'arm': arm, 'record_status': 'evaluated', 'success': True,
            'known_total_tokens': tokens, 'logical_task_known_total_tokens': tokens + 100,
            'logical_task_unknown_usage_calls': 0}
            for n in range(4) for arm, tokens in zip(ARMS, (200, 100), strict=True)]

    def test_same_known_success_with_lower_cost_passes_only_local_gate(self):
        result = development_gate(self.rows())
        self.assertTrue(result['development_gate_met'])
        self.assertEqual(result['candidate_minus_control_work_tokens'], -400)
        self.assertFalse(result['general_quality_preservation_claim'])
        self.assertFalse(result['novel_method_claim'])

    def test_unknown_usage_or_missing_evaluation_prevents_exact_total_adoption(self):
        for change in ({'logical_task_unknown_usage_calls': 1},
                       {'record_status': 'not_run_after_stop', 'success': None}):
            rows = self.rows(); rows[1].update(change); result = development_gate(rows)
            self.assertFalse(result['development_gate_met'])
            self.assertIsNone(result['candidate_minus_control_work_tokens'])

    def test_paired_quality_loss_is_not_cancelled_by_another_gain_or_lower_cost(self):
        rows = self.rows(); rows[1]['success'] = False; rows[2]['success'] = False
        result = development_gate(rows)
        self.assertEqual(result['paired_success_losses'], 1)
        self.assertEqual(result['paired_success_gains'], 1)
        self.assertFalse(result['development_gate_met'])

    def test_all_failed_cheaper_tasks_are_not_quality_preserving_success(self):
        rows = self.rows()
        for row in rows: row['success'] = False
        self.assertFalse(development_gate(rows)['development_gate_met'])

    def test_higher_cost_or_malformed_population_is_not_adopted(self):
        rows = self.rows(); rows[1]['logical_task_known_total_tokens'] = 1000
        self.assertFalse(development_gate(rows)['development_gate_met'])
        for rows in (self.rows()[:-1], self.rows() + [self.rows()[0]]):
            with self.assertRaises(ValueError): development_gate(rows)
        rows = self.rows(); rows[0]['success'] = 1
        with self.assertRaises(ValueError): development_gate(rows)


if __name__ == '__main__': unittest.main()

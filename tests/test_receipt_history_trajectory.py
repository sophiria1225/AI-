import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from recorded_action_agreement import analyze_run
from receipt_history_trajectory import describe_call, compare_position, compare_trajectories, request_components
from test_recorded_action_agreement import fixture


def described(code='x = 1', *, known=True, request=None, value=None, text_only=False):
    raw = fixture(code, response_known=known, request=request, value=value, text_only=text_only)
    response = raw[3]['call_001']
    if known:
        response['message']['reasoning_content'] = 'retained thought'
    call = analyze_run(*raw)[0]
    input_row = dict(call_id='call_001', policy='full', actual_policy='full',
        actual_usage_status='ok' if known else 'unknown',
        actual_measured_input_tokens=10 if known else None,
        actual_measured_output_tokens=5 if known else None,
        actual_measured_cached_input_tokens=0 if known else None,
        input_tokens=10, delta_from_full=0,
        projection=dict(removed_reasoning_turns=[], redisplayed_reasoning_turns=[]))
    payload = dict(messages=[dict(role='user', content='task')], seed=58, max_tokens=4096)
    return describe_call(call, payload, response, input_row)


class TrajectoryDiagnosticTests(unittest.TestCase):
    def test_request_split_removes_only_assistant_reasoning(self):
        a = dict(messages=[dict(role='assistant', content='', reasoning_content='old',
                  tool_calls=[dict(id='opaque', function=dict(name='run_python', arguments='{}'))]),
                 dict(role='user', content='Remaining API: 3')], seed=58)
        b = copy.deepcopy(a); del b['messages'][0]['reasoning_content']
        x, y = request_components(a), request_components(b)
        self.assertNotEqual(x['request_sha256'], y['request_sha256'])
        self.assertEqual(x['request_without_reasoning_sha256'], y['request_without_reasoning_sha256'])
        for change in ('budget', 'transport_id', 'seed'):
            c = copy.deepcopy(b)
            if change == 'budget': c['messages'][1]['content'] = 'Remaining API: 2'
            if change == 'transport_id': c['messages'][0]['tool_calls'][0]['id'] = 'different'
            if change == 'seed': c['seed'] = 59
            self.assertNotEqual(y['request_without_reasoning_sha256'], request_components(c)['request_without_reasoning_sha256'])

    def test_equal_API_does_not_hide_different_code(self):
        a = described('x = 1', request={'id': 1}, value={'v': 2})
        b = described('x = 2', request={'id': 1}, value={'v': 2})
        row = compare_position(a, b)
        self.assertTrue(row['nonempty_API_equal'])
        self.assertFalse(row['Python_AST_equal'])
        self.assertEqual(row['target_component_class'], 'Python_AST_differs')
        self.assertTrue(row['same_request_different_public_output'])
        self.assertFalse(row['full_process_state_equal_claim'])

    def test_equal_requests_do_not_imply_equal_API_results(self):
        a = described(request={'id': 1}, value=1)
        b = described(request={'id': 1}, value=2)
        row = compare_position(a, b)
        self.assertTrue(row['API_sequence_including_empty_equal'])
        self.assertFalse(row['API_results_including_empty_equal'])

    def test_empty_actions_and_unknown_usage_remain_distinct(self):
        a, b = described(), described(known=False)
        empty = compare_position(a, a)
        self.assertEqual(empty['API_class'], 'both_empty')
        self.assertTrue(empty['API_sequence_including_empty_equal'])
        self.assertIsNone(empty['nonempty_API_equal'])
        unknown = compare_position(a, b)
        self.assertTrue(unknown['request_equal'])
        self.assertIsNone(unknown['reasoning_equal'])
        self.assertIsNone(unknown['API_sequence_including_empty_equal'])
        self.assertIsNone(b['known_total_tokens'])
        self.assertEqual(b['input_tokens_if_counted'], 10)

    def test_empty_to_nonempty_API_is_an_observed_difference(self):
        row = compare_position(described(), described(request={'id': 1}))
        self.assertEqual(row['API_class'], 'one_empty')
        self.assertFalse(row['API_sequence_including_empty_equal'])
        self.assertIsNone(row['nonempty_API_equal'])

    def test_all_pairs_keep_tail_and_unknown_positions(self):
        a, b = described(), described(known=False)
        b['ordinal'] = 2; b['call_id'] = 'call_002'
        runs = [dict(task_id='task', run_id=p, reasoning_display_policy=p, success=False,
                     model_calls=len(c), calls=c) for p, c in
                [('full', [a, b]), ('recent', [a]), ('execution_gated', [a, b])]]
        pairs = compare_trajectories(runs)
        self.assertEqual(len(pairs), 3)
        self.assertEqual(sum(len(p['rows']) for p in pairs), 6)
        self.assertEqual(sum(p['all_aligned']['status_counts'].get('one_run_ended', 0) for p in pairs), 2)
        self.assertEqual(pairs[0]['equality']['public_equal']['contiguous_equal_prefix_positions'], 1)
        self.assertIsNone(pairs[0]['equality']['public_equal']['first_observed_difference'])
        self.assertEqual(pairs[0]['equality']['public_equal']['first_unavailable'], 2)

    def test_missing_policy_or_unordered_calls_rejected(self):
        a = described()
        runs = [dict(task_id='task', run_id=p, reasoning_display_policy=p, success=True,
                     model_calls=1, calls=[a]) for p in ('full', 'recent', 'execution_gated')]
        with self.assertRaisesRegex(ValueError, 'all_three_policies'):
            compare_trajectories(runs[:2])
        runs[0] = copy.deepcopy(runs[0]); runs[0]['calls'][0]['ordinal'] = 2
        with self.assertRaisesRegex(ValueError, 'chronological_call'):
            compare_trajectories(runs)

    def test_source_strings_are_parsed_without_execution(self):
        value = described("raise RuntimeError('must not execute saved program')")
        self.assertTrue(value['components']['all_components_available'])
        self.assertIsNotNone(value['components']['Python_AST_sequence_sha256'])


if __name__ == '__main__': unittest.main()

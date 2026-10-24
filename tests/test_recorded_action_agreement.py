import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from recorded_action_agreement import analyze_run, compare_call, compare_runs, action_value


def fixture(code='x = 1', *, content='', request=None, value=None, api_status='returned',
            response_known=True, text_only=False, format_error=False):
    cid = 'call_001'
    usage = [dict(id=cid, status='ok' if response_known else 'unknown',
                  input_tokens=10 if response_known else None, output_tokens=5 if response_known else None)]
    if not response_known:
        return usage, [], {}, {cid: None}
    fn = dict(name='run_python', arguments=json.dumps(dict(code=code, span_ids=[])))
    response = dict(status='ok', done_reason='stop' if text_only else 'tool_calls',
                    message=dict(content=content, tool_calls=[] if text_only else [dict(id='opaque', function=fn)]))
    events = []; spans = {}; receipts = []
    if request is not None:
        sid = 's1'; api = dict(name='example__read', arguments=json.dumps(request))
        events.append(dict(call=cid, span_id=sid, stage='python_api', api_request_sent=True,
            effects_unknown=api_status == 'unknown', new_tools=[], api_execution=dict(
                bridge_request_sent=True, automatic_retries=0, status=api_status)))
        spans[sid] = dict(id=sid, action=api, observation=dict(observation=value))
        receipts.append(dict(span_id=sid, api=api['name'], api_request_sent=True))
    sid = 's' + str(len(spans) + 1)
    obs = (dict(format_error='tool call required') if text_only else
           dict(format_error='invalid Python arguments') if format_error else
           dict(status='ok', stdout='', error=None, api_requests=len(receipts), api_receipts=receipts))
    events.append(dict(call=cid, span_id=sid, stage='model_tool', api_request_sent=False,
                       effects_unknown=api_status == 'unknown', new_tools=[]))
    spans[sid] = dict(id=sid, action=None if text_only else fn, observation=obs)
    return usage, events, spans, {cid: response}


class RecordedAgreementTests(unittest.TestCase):
    def test_matching_text_without_submission_is_not_action_agreement(self):
        a = analyze_run(*fixture(text_only=True, content='done'))[0]
        c = compare_call(a, copy.deepcopy(a))
        self.assertTrue(c['public_equal'])
        self.assertTrue(c['equal_public_without_completed_submission'])
        self.assertEqual(c['API_class'], 'both_empty')
        self.assertIsNone(c['nonempty_API_equal'])
        self.assertIsNone(c['syntax_equal'])

    def test_different_syntax_can_have_same_recorded_API(self):
        a = analyze_run(*fixture('x = 1', request={'id': 1}, value={'v': 2}))[0]
        b = analyze_run(*fixture('x = 2', request={'id': 1}, value={'v': 2}))[0]
        c = compare_call(a, b)
        self.assertFalse(c['syntax_equal'])
        self.assertTrue(c['different_syntax_same_nonempty_API'])
        self.assertTrue(c['prior_API_prefix_equal'])

    def test_arguments_and_authorization_values_are_never_removed(self):
        a = analyze_run(*fixture(request={'access_token': 'a', 'id': 1}))[0]
        b = analyze_run(*fixture(request={'access_token': 'b', 'id': 1}))[0]
        self.assertFalse(compare_call(a, b)['nonempty_API_equal'])
        self.assertEqual(action_value({'name': 'a__b', 'arguments': '{"x":1,"y":2}'}),
                         action_value({'name': 'a__b', 'arguments': '{"y":2, "x":1}'}))

    def test_same_API_request_does_not_imply_same_return_value(self):
        a = analyze_run(*fixture(request={'id': 1}, value=1))[0]
        b = analyze_run(*fixture(request={'id': 1}, value=2))[0]
        c = compare_call(a, b)
        self.assertTrue(c['nonempty_API_equal']); self.assertFalse(c['API_result_equal'])

    def test_unknown_usage_and_ended_run_are_separate_from_empty_actions(self):
        unknown = analyze_run(*fixture(response_known=False))[0]
        known = analyze_run(*fixture())[0]
        self.assertIsNone(unknown['known_total_tokens'])
        self.assertEqual(compare_call(known, unknown)['API_class'], 'unavailable')
        self.assertIsNone(compare_call(known, unknown)['public_equal'])
        self.assertEqual(compare_call(known, None)['status'], 'one_run_ended')
        self.assertEqual(compare_call(known, known)['API_class'], 'both_empty')
        self.assertFalse(compare_call(known, known)['equal_public_without_completed_submission'])

    def test_failed_API_cost_and_sent_request_remain_in_inventory(self):
        a = analyze_run(*fixture(request={'id': 1}, api_status='raised', value={'error': 'example'}))[0]
        self.assertEqual(a['API_requests'], 1)
        self.assertEqual(a['API_status_counts'], {'raised': 1})
        self.assertEqual(a['known_total_tokens'], 15)

    def test_receipt_link_and_actual_submission_must_match(self):
        f = fixture(request={'id': 1}); f[2]['s2']['observation']['api_receipts'] = []
        with self.assertRaisesRegex(ValueError, 'program_API_count'):
            analyze_run(*f)
        f = fixture(); f[2]['s1']['action'] = {'name': 'different', 'arguments': '{}'}
        with self.assertRaisesRegex(ValueError, 'submitted_and_recorded'):
            analyze_run(*f)

    def test_unknown_effect_disables_current_and_later_prefix_comparisons(self):
        first = fixture(request={'id': 1}, api_status='unknown')
        second = fixture()
        second[0][0]['id'] = 'call_002'; second[1][0].update(call='call_002', span_id='s3')
        spans = {**first[2], 's3': {**second[2]['s1'], 'id': 's3'}}
        calls = analyze_run(first[0] + second[0], first[1] + second[1], spans,
                            {**first[3], 'call_002': second[3]['call_001']})
        self.assertFalse(calls[0]['API_requests_known'])
        self.assertIsNone(calls[1]['prior_API_prefix_sha256'])

    def test_all_condition_pairs_include_tail_and_cross_repetition(self):
        call = analyze_run(*fixture())[0]
        runs = [dict(run_id=f'r{i}', task_id='task', time_visibility=str(i % 3),
                     repetition=1 + i // 3, calls=[call] * (1 + (i == 0))) for i in range(6)]
        pairs = compare_runs(runs)
        self.assertEqual(len(pairs), 15)
        self.assertEqual(sum(p['relation'] == 'same_policy_repetition' for p in pairs), 3)
        self.assertEqual(sum(p['relation'] == 'within_repetition' for p in pairs), 6)
        self.assertEqual(sum(p['relation'] == 'cross_policy_cross_repetition' for p in pairs), 6)
        self.assertEqual(sum(p['all_aligned']['status_counts'].get('one_run_ended', 0) for p in pairs), 5)
        self.assertTrue(all(p['independent_samples'] is False for p in pairs))


if __name__ == '__main__': unittest.main()

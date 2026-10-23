import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_budget_visibility_usage_bounds import bound_calls, parse_numeric_log


KNOWN = '''0 I slot launch_slot_: id 0 | task 10 | processing task, is_child = 0
1 I slot print_timing: id 0 | task 10 | prompt eval time = 2.0 ms / 2 tokens
2 I slot print_timing: id 0 | task 10 |        eval time = 4.0 ms / 2 tokens
3 I slot release: id 0 | task 10 | stop processing: n_tokens = 4, truncated = 0
'''
CANCELLED = '''4 I slot launch_slot_: id 0 | task 20 | processing task, is_child = 0
5 I slot print_timing: id 0 | task 20 | n_gen = 3, tg = 2.0 t/s
6 I srv stop: cancel task, id_task = 20
7 I slot print_timing: id 0 | task 20 | n_gen = 4, tg = 2.0 t/s
8 I slot release: id 0 | task 20 | stop processing: n_tokens = 10, truncated = 0
'''


def calls():
    return [dict(run_id='known',id='call_001',status='ok',input_tokens=3,
                 cached_input_tokens=1,output_tokens=2,predicted_input_tokens=3,output_cap=8),
            dict(run_id='unknown',id='call_001',status='error',input_tokens=None,
                 output_tokens=None,cached_input_tokens=None,predicted_input_tokens=7,output_cap=8)]


class BackendBoundsTests(unittest.TestCase):
    def test_cancellation_keeps_unknown_and_counts_late_observed_work(self):
        original=calls(); before=copy.deepcopy(original)
        rows, n=bound_calls(original,parse_numeric_log(KNOWN+CANCELLED))
        self.assertEqual(n,1)
        self.assertEqual([r['logical_tokens_lower_bound'] for r in rows],[5,11])
        self.assertFalse(rows[1]['complete_usage'])
        self.assertTrue(rows[1]['original_usage_unknown'])
        self.assertEqual(rows[1]['generated_tokens_lower_bound'],4)
        self.assertEqual(original,before)

    def test_refuses_unmatched_or_incomplete_server_history(self):
        cases=[KNOWN+CANCELLED.rsplit('\n',2)[0]+'\n',
               KNOWN.replace('id 0','id 1'),
               KNOWN+CANCELLED.replace('task 20','task 10').replace('task = 20','task = 10'),
               KNOWN+CANCELLED.replace('id_task = 20','id_task = 99'),
               KNOWN+CANCELLED.replace('n_gen = 4','n_gen = 2')]
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):parse_numeric_log(text)

    def test_refuses_missing_extra_or_interleaved_launches(self):
        tasks=parse_numeric_log(KNOWN+CANCELLED)
        for selected in (tasks[:1],tasks+tasks[:1]):
            with self.assertRaises(ValueError):bound_calls(calls(),selected)
        interleaved=KNOWN.splitlines()[0]+'\n'+CANCELLED
        with self.assertRaises(ValueError):parse_numeric_log(interleaved)

    def test_all_known_receipts_must_match_including_cached_input(self):
        for key in ('input_tokens','cached_input_tokens','output_tokens','predicted_input_tokens'):
            values=calls(); values[0][key]+=1
            with self.subTest(key=key):
                with self.assertRaises(ValueError):bound_calls(values,parse_numeric_log(KNOWN+CANCELLED))
        with self.assertRaises(ValueError):bound_calls(calls()[::-1],parse_numeric_log(KNOWN+CANCELLED))

    def test_input_count_alone_does_not_establish_execution(self):
        text='\n'.join(l for l in CANCELLED.splitlines() if 'n_gen' not in l)+'\n'
        with self.assertRaises(ValueError):bound_calls(calls(),parse_numeric_log(KNOWN+text))
        text=CANCELLED.replace('6 I srv stop: cancel task, id_task = 20\n','')
        with self.assertRaises(ValueError):bound_calls(calls(),parse_numeric_log(KNOWN+text))

    def test_refuses_duplicate_attempts_and_impossible_generation_count(self):
        values=calls();values[1]['run_id']='known'
        with self.assertRaises(ValueError):bound_calls(values,parse_numeric_log(KNOWN+CANCELLED))
        values=calls();values[1]['output_cap']=3
        with self.assertRaises(ValueError):bound_calls(values,parse_numeric_log(KNOWN+CANCELLED))


if __name__=='__main__':unittest.main()

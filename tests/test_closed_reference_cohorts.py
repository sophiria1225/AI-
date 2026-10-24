import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from compare_closed_reference_cohorts import compare_cohorts, equal_prefix


def inputs():
    names = ('reports/P81_repetitions.json', 'reports/P82_comparison.json',
             'reports/P81_trajectory_stability.json', 'reports/P82_trajectory_stability.json',
             'configs/P82_late_clock_comparison_v01.json')
    old, new, a, b, plan = [json.loads((ROOT / n).read_text()) for n in names]
    return old, new, a['traces'], b['traces'], [t['task_id'] for t in plan['known_tasks']]


class ClosedReferenceCohortTests(unittest.TestCase):
    def test_all_twenty_runs_and_twenty_four_dependent_pairs_remain(self):
        selected, pairs = compare_cohorts(*inputs())
        self.assertEqual([len(x) for x in selected], [12, 8])
        self.assertEqual(len(pairs), 24)
        self.assertEqual(len({tuple(p['run_ids']) for p in pairs}), 24)
        self.assertEqual({task: sum(p['task_id'] == task for p in pairs)
                          for task in inputs()[-1]}, {task: 6 for task in inputs()[-1]})

    def test_missing_or_duplicated_hidden_run_is_rejected(self):
        for duplicate in (False, True):
            old, new, a, b, tasks = inputs()
            i = next(i for i, r in enumerate(new['rows']) if r['time_visibility'] == 'not_exposed')
            new['rows'].pop(i)
            if duplicate:
                new['rows'].append(copy.deepcopy(next(r for r in new['rows'] if r['time_visibility'] == 'not_exposed')))
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(ValueError, 'all_fixed_hidden'):
                compare_cohorts(old, new, a, b, tasks)

    def test_unknown_tail_does_not_become_a_complete_trace(self):
        old, new, a, b, tasks = inputs()
        row = next(r for r in new['rows'] if r['time_visibility'] == 'not_exposed' and r['unknown_usage_calls'])
        b[row['run_id']]['known_complete'] = True
        with self.assertRaisesRegex(ValueError, 'missing_usage'):
            compare_cohorts(old, new, a, b, tasks)

    def test_call_order_must_match_audited_attempts(self):
        old, new, a, b, tasks = inputs()
        row = next(r for r in new['rows'] if r['time_visibility'] == 'not_exposed')
        calls = b[row['run_id']]['calls']; calls[0], calls[1] = calls[1], calls[0]
        with self.assertRaisesRegex(ValueError, 'every_audited_attempt'):
            compare_cohorts(old, new, a, b, tasks)

    def test_missing_fingerprint_stops_prefix_even_if_later_values_match(self):
        left = {'calls': [{'hash': 'a'}, {'hash': None}, {'hash': 'b'}]}
        right = copy.deepcopy(left)
        self.assertEqual(equal_prefix(left, right, 'hash'), 1)
        self.assertEqual(equal_prefix({'calls': [{'hash': None}]}, {'calls': [{'hash': None}]}, 'hash'), 0)


if __name__ == '__main__':
    unittest.main()

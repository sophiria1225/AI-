import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from summarize_budget_visibility_prefixes import FIELDS, compare_field, compare_prefixes


def trace(*values):
    return {'calls': [dict(zip(FIELDS, v, strict=True)) for v in values]}


class PrefixCoverageTests(unittest.TestCase):
    def test_missing_final_outputs_do_not_hide_known_identical_requests(self):
        a = trace(('r1', 'p1', 'o1'), ('r2', None, None))
        r = compare_prefixes(a, a)
        self.assertEqual(r['fields']['request_sha256']['relation'], 'identical_recorded_sequences')
        for k in FIELDS[1:]:
            self.assertEqual(r['fields'][k]['relation'], 'indeterminate')
            self.assertEqual(r['fields'][k]['equal_initial_calls'], 1)
            self.assertEqual(r['fields'][k]['unobserved_pairs'], 1)

    def test_empty_unattempted_runs_are_not_identical_evidence(self):
        r = compare_prefixes(trace(), trace())
        self.assertTrue(all(v['relation'] == 'indeterminate' for v in r['fields'].values()))

    def test_extra_attempt_does_not_become_equal_whole_sequence(self):
        a = trace(('r1', 'p1', 'o1'))
        b = trace(('r1', 'p1', 'o1'), ('r2', 'p2', 'o2'))
        r = compare_prefixes(a, b)
        for v in r['fields'].values():
            self.assertEqual(v['relation'], 'different_lengths_identical_common_prefix')
            self.assertEqual(v['one_sided_calls'], 1)
            self.assertEqual(v['equal_initial_calls'], 1)

    def test_earlier_output_difference_is_not_attributed_to_later_input_difference(self):
        a = trace(('r1', 'p1', 'o1'), ('r2', 'p2', 'o2'))
        b = trace(('r1', 'p1', 'other'), ('r2b', 'p2b', 'o2b'))
        r = compare_prefixes(a, b)
        self.assertFalse(r['both_returned_output_prefixes_equal_before_first_request_difference'])
        self.assertTrue(r['recorded_requests_equal_through_first_returned_output_difference'])

    def test_unknown_earlier_request_prevents_claiming_equal_inputs(self):
        a = trace(('r1', 'p1', 'o1'), ('r2', 'p2', 'o2'))
        b = trace((None, 'p1', 'o1'), ('r2', 'different', 'o2'))
        r = compare_prefixes(a, b)
        self.assertFalse(r['recorded_requests_equal_through_first_returned_output_difference'])
        self.assertEqual(r['fields']['request_sha256']['relation'], 'indeterminate')

    def test_observed_difference_after_gap_does_not_certify_earlier_prefix(self):
        a = trace((None, 'p1', 'o1'), ('r2', 'p2', 'o2'))
        b = trace(('r1', 'p1', 'o1'), ('changed', 'p2', 'o2'))
        r = compare_field(a['calls'], b['calls'], 'request_sha256')
        self.assertEqual(r['relation'], 'observed_difference')
        self.assertEqual(r['first_observed_difference'], 2)
        self.assertEqual(r['equal_initial_calls'], 0)


if __name__ == '__main__':
    unittest.main()

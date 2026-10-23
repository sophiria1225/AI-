import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from summarize_late_clock_resources import resource_cells, comparisons, write_outputs
from test_late_clock_usage_intervals import fixture as interval_fixture
from late_clock_comparison import cell_id


def fixture():
    cells, calls, _ = interval_fixture()
    for c in cells:
        c.update(input_tokens=c['known_total_tokens'] - 20, output_tokens=20,
                 cached_input_tokens=40, stop_reason='fixture',
                 wall_seconds=10.0, full_wall_seconds=12.0,
                 setup_wall_seconds=1.0, cleanup_wall_seconds=1.0)
    return cells, calls


def make_unknown(cells, calls, policy, input_tokens):
    rid = cell_id(1, 4, policy)
    c = next(c for c in cells if c['run_id'] == rid)
    r = next(r for r in calls if r['run_id'] == rid)
    c.update(known_total_tokens=0, input_tokens=0, output_tokens=0,
             cached_input_tokens=0, unknown_usage_calls=1)
    r.update(complete_usage=False, logical_tokens_lower_bound=input_tokens + 10,
             logical_tokens_upper_bound=input_tokens + 20, input_tokens_lower_bound=input_tokens,
             generated_tokens_lower_bound=10, generated_tokens_upper_bound=20)


def first_total(rows):
    return next(p for p in comparisons(rows)
                if p['repetition'] == 1 and p['baseline'] == 'measured' and p['category'] == 'total')


class LateClockResourceTests(unittest.TestCase):
    def test_separate_measures_and_every_partition(self):
        cells, calls = fixture()
        before = copy.deepcopy((cells, calls))
        rows, _ = resource_cells(cells, calls)
        pairs = comparisons(rows)
        self.assertEqual((len(rows), len(pairs), sum(len(p['arms']) for p in pairs)), (24, 24, 48))
        total = first_total(rows)
        self.assertEqual(total['late_half_minus_baseline_intervals'],
                         {'logical_tokens': [-80, -80], 'uncached_input_tokens': [-80, -80], 'output_tokens': [0, 0]})
        self.assertEqual(total['arms']['measured']['full_wall_seconds'], 48.0)
        failed = next(p for p in pairs if p['repetition'] == 1
                      and p['baseline'] == 'measured' and p['category'] == 'both_failure')
        self.assertEqual(failed['arms']['measured']['conditions'], 1)
        self.assertEqual(failed['arms']['measured']['full_wall_seconds'], 12.0)
        self.assertEqual((cells, calls), before)

    def test_missing_baseline_is_not_treated_as_zero(self):
        cells, calls = fixture()
        make_unknown(cells, calls, 'measured', 150)
        rows, decisions = resource_cells(cells, calls)
        pair = first_total(rows)
        self.assertEqual(pair['late_half_minus_baseline_intervals'],
                         {'logical_tokens': [-150, -140], 'uncached_input_tokens': [-190, -40], 'output_tokens': [0, 10]})
        self.assertFalse(decisions['all_repetition_gates_met'])
        self.assertEqual(pair['arms']['measured']['unknown_usage_calls'], 1)

    def test_both_sides_unknown_can_reverse_the_known_subset_difference(self):
        cells, calls = fixture()
        make_unknown(cells, calls, 'measured', 150)
        make_unknown(cells, calls, 'late_half', 300)
        rows, decisions = resource_cells(cells, calls)
        pair = first_total(rows)
        a, b = pair['arms']['late_half'], pair['arms']['measured']
        self.assertEqual(a['known_total_tokens'] - b['known_total_tokens'], -60)
        self.assertEqual(pair['late_half_minus_baseline_intervals']['logical_tokens'], [80, 100])
        self.assertEqual(pair['late_half_minus_baseline_intervals']['uncached_input_tokens'], [-210, 240])
        self.assertEqual(pair['late_half_minus_baseline_intervals']['output_tokens'], [-10, 10])
        self.assertFalse(decisions['all_repetition_gates_met'])

    def test_unknown_cache_is_kept_as_range_not_estimated(self):
        cells, calls = fixture()
        make_unknown(cells, calls, 'late_half', 300)
        rows, _ = resource_cells(cells, calls)
        row = next(r for r in rows if r['run_id'] == cell_id(1, 4, 'late_half'))
        self.assertEqual(row['known_cached_input_tokens'], 0)
        self.assertFalse(row['terminal_usage_complete'])
        self.assertEqual(row['uncached_input_tokens'], [0, 300])
        self.assertEqual(row['output_tokens_interval'], [10, 20])

    def test_inconsistent_counter_or_nonfinite_time_is_rejected(self):
        for change in ({'cached_input_tokens': 100}, {'output_tokens': 21},
                       {'input_tokens': True}, {'wall_seconds': float('nan')},
                       {'full_wall_seconds': float('inf')}, {'api_requests': -1}):
            cells, calls = fixture(); cells[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                resource_cells(cells, calls)

    def test_unknown_resource_bounds_must_match_logical_bounds(self):
        cells, calls = fixture()
        make_unknown(cells, calls, 'late_half', 300)
        r = next(r for r in calls if not r['complete_usage'])
        r['generated_tokens_upper_bound'] = 21
        with self.assertRaisesRegex(ValueError, 'same_pinned_conditional'):
            resource_cells(cells, calls)

    def test_exports_all_cells_and_partitions_once(self):
        cells, calls = fixture()
        rows, _ = resource_cells(cells, calls)
        result = {'rows': rows, 'comparisons': comparisons(rows)}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'new'
            write_outputs(result, output)
            self.assertEqual(len((output / 'all_24_conditions.csv').read_text().splitlines()), 25)
            self.assertEqual(len((output / 'all_48_partition_arms.csv').read_text().splitlines()), 49)
            self.assertEqual(json.loads((output / 'resource_accounting.json').read_text()), result)
            with self.assertRaises(FileExistsError):
                write_outputs(result, output)


if __name__ == '__main__':
    unittest.main()

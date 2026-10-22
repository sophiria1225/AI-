import dataclasses
import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ranked_subset_read import AccessContract, ReadReceipt, subset_maximum


class RankedSubsetReadTests(unittest.TestCase):
    def setUp(self):
        self.contract = AccessContract('source', 'snapshot', 'id', 'score', ('value',),
                                       'global_desc', True, True)

    def run_case(self, rows, targets, mode, **kwargs):
        by_id = {row['id']: row for row in rows}
        ordered = sorted(rows, key=lambda row: (-row['score'], row['id']))
        def receipt(items):
            return ReadReceipt('source', 'snapshot', items)
        return subset_maximum(targets, contract=self.contract,
            point_read=lambda key: receipt([by_id[key]]),
            page_read=lambda index, size: receipt(ordered[index*size:(index+1)*size]),
            mode=mode, max_requests=kwargs.pop('max_requests', 20), **kwargs)

    def test_all_small_worlds_and_subsets_against_independent_maximum(self):
        # 81 worlds x 15 nonempty subsets x 3 strategies. Includes ties,
        # nonmembers preceding the best target, and page-boundary ties.
        for scores in itertools.product(range(3), repeat=4):
            rows = [{'id': i+1, 'score': score, 'value': str(i)} for i, score in enumerate(scores)]
            for mask in range(1, 16):
                targets = [i+1 for i in range(4) if mask & (1 << i)]
                maximum = max(scores[i-1] for i in targets)
                expected = [i for i in targets if scores[i-1] == maximum]
                for mode in ('point', 'ranked', 'bounded'):
                    result = self.run_case(rows, targets, mode, page_limit=2)
                    self.assertEqual(result['status'], 'complete', (scores, targets, mode, result))
                    self.assertEqual([r['id'] for r in result['winners']], expected)
                    if mode == 'bounded':
                        self.assertLessEqual(result['requests_attempted'], len(targets) + 1)

    def test_boundary_tie_requires_another_page(self):
        rows = [{'id': i, 'score': 5, 'value': str(i)} for i in range(1, 5)]
        result = self.run_case(rows, [1, 4], 'ranked', page_limit=2)
        self.assertEqual(result['page_requests'], 2)
        self.assertEqual([r['id'] for r in result['winners']], [1, 4])

    def test_ineligible_rank_contract_uses_point_access_without_speculation(self):
        for update in ({'order': 'within_page_desc'}, {'covers_target_universe': False}):
            self.contract = dataclasses.replace(AccessContract('source', 'snapshot', 'id', 'score',
                ('value',), 'global_desc', True, True), **update)
            result = self.run_case([{'id': 1, 'score': 3, 'value': 'a'}], [1], 'bounded')
            self.assertEqual((result['effective_mode'], result['page_requests']), ('point', 0))
            self.assertEqual(result['status'], 'complete')

    def test_unstable_snapshot_is_refused_before_any_strategy_reads(self):
        self.contract = dataclasses.replace(self.contract, stable_snapshot=False)
        for mode in ('point', 'ranked', 'bounded'):
            result = self.run_case([{'id': 1, 'score': 1, 'value': 'x'}], [1], mode)
            self.assertEqual((result['stop_reason'], result['requests_attempted']), ('unstable_snapshot_contract', 0))

    def test_budget_counts_failed_request_and_never_returns_partial_maximum(self):
        rows = [{'id': i, 'score': i, 'value': str(i)} for i in range(1, 4)]
        result = self.run_case(rows, [1, 2], 'point', max_requests=1)
        self.assertEqual(result['stop_reason'], 'request_budget_exhausted')
        self.assertEqual((result['requests_attempted'], result['winners']), (1, []))
        result = self.run_case(rows, [4], 'point')
        self.assertEqual(result['stop_reason'], 'source_exception:KeyError')
        self.assertEqual(result['requests_attempted'], 1)

    def test_receipt_and_record_faults_do_not_authorize_an_answer(self):
        cases = [
            (ReadReceipt('source', 'changed', [{'id': 1, 'score': 2, 'value': 'x'}]), 'source_or_snapshot_changed'),
            (ReadReceipt('source', 'snapshot', [{'id': 2, 'score': 2, 'value': 'x'}]), 'point_id_mismatch'),
            (ReadReceipt('source', 'snapshot', [{'id': 1, 'score': float('nan'), 'value': 'x'}]), 'invalid_record_score'),
            (ReadReceipt('source', 'snapshot', [{'id': 1, 'score': True, 'value': 'x'}]), 'invalid_record_score'),
            (ReadReceipt('source', 'snapshot', [{'id': 1, 'score': 2}]), 'required_value_missing'),
            (ReadReceipt('source', 'snapshot', []), 'invalid_response_cardinality'),
        ]
        for receipt, reason in cases:
            result = subset_maximum([1], contract=self.contract, point_read=lambda _: receipt,
                page_read=lambda *_: None, mode='point', max_requests=3)
            self.assertEqual((result['status'], result['stop_reason'], result['winners']), ('incomplete', reason, []))

    def test_detected_rank_faults_stop_without_retry(self):
        for rows, reason in [
            ([{'id': 1, 'score': 1, 'value': 'a'}, {'id': 2, 'score': 2, 'value': 'b'}], 'observed_rank_violation'),
            ([{'id': 1, 'score': 2, 'value': 'a'}] * 2, 'duplicate_ranked_id'),
        ]:
            result = subset_maximum([3], contract=self.contract, point_read=lambda _: None,
                page_read=lambda *_: ReadReceipt('source', 'snapshot', rows), mode='ranked', max_requests=5)
            self.assertEqual((result['stop_reason'], result['requests_attempted']), (reason, 1))

    def test_exhausted_source_missing_target_is_incomplete(self):
        result = self.run_case([{'id': 1, 'score': 1, 'value': 'a'}], [2], 'ranked')
        self.assertEqual(result['stop_reason'], 'target_missing_from_exhausted_source')
        self.assertEqual(result['winners'], [])

    def test_bounded_reuses_target_records_and_can_cost_one_extra_request(self):
        rows = [{'id': i, 'score': 10-i, 'value': str(i)} for i in range(1, 6)]
        reused = self.run_case(rows, [2, 4], 'bounded', page_limit=2)
        self.assertEqual((reused['page_requests'], reused['point_requests']), (1, 1))
        overhead = self.run_case(rows, [4, 5], 'bounded', page_limit=2)
        self.assertEqual(overhead['requests_attempted'], 3)

    def test_empty_and_invalid_target_sets(self):
        self.assertEqual(self.run_case([], [], 'ranked')['requests_attempted'], 0)
        for targets in ([1, 1], [True], [0], ['1']):
            with self.assertRaises(ValueError):
                self.run_case([], targets, 'point')


if __name__ == '__main__':
    unittest.main()

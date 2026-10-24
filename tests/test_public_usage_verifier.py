import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_public_usage_intervals import PLAN, REPORT, recompute, verify


class PublicUsageVerifierTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.report, self.original = [json.loads((ROOT / name).read_text()) for name in
            (PLAN, REPORT, 'reports/P97_comparison.json')]

    def check(self):
        return recompute(self.plan, self.report, self.original)

    def test_all_public_files_and_tables_verify_without_private_records(self):
        result = verify(ROOT)
        self.assertEqual(result['checked_bindings'], 16)
        self.assertEqual(result['all_conditions']['known_logical_tokens'], 2439566)
        self.assertEqual(result['unknown_attempts_preserved'], 2)
        self.assertEqual([x['successful']['known_logical_tokens'] for x in result['totals']],
                         [448825, 448825, 448825])

    def test_zero_unknown_imputation_rejected_even_when_lower_bound_is_zero(self):
        call = next(c for r in self.report['rows'] for c in r['calls'] if c['status'] == 'error')
        call['observed_logical_tokens'] = 0
        with self.assertRaisesRegex(ValueError, 'unknown_must_remain_missing'):
            self.check()

    def test_unknown_error_receipt_does_not_establish_cap_compliance(self):
        self.report['server_cap_compliance_proven_for_unknown'] = True
        with self.assertRaisesRegex(ValueError, 'scope_or_gate_changed'):
            self.check()

    def test_original_gate_cannot_be_replaced_by_conditional_sign(self):
        self.report['original_factual_notice_benefit_gate_met'] = True
        with self.assertRaisesRegex(ValueError, 'scope_or_gate_changed'):
            self.check()

    def test_omitted_cell_call_and_task_pair_rejected(self):
        before = copy.deepcopy(self.report)
        for target in ('cell', 'call', 'pair'):
            with self.subTest(target=target):
                self.report = copy.deepcopy(before)
                if target == 'cell': self.report['rows'].pop()
                elif target == 'call': self.report['rows'][0]['calls'].pop()
                else: self.report['all_task_differences'].pop()
                with self.assertRaises(ValueError): self.check()

    def test_swapped_receipt_and_changed_cap_rejected(self):
        before = copy.deepcopy(self.report)
        for key, value in [('request_sha256', 'different'), ('requested_output_cap', 4097),
                           ('observed_logical_tokens', 8000)]:
            self.report = copy.deepcopy(before)
            self.report['rows'][0]['calls'][0][key] = value
            with self.assertRaises(ValueError): self.check()

    def test_reported_difference_sign_and_failure_stratum_recomputed(self):
        before = copy.deepcopy(self.report)
        self.report['whole_cohort_differences'][0]['conditional_request_interval']['sign_under_assumptions'] = 'positive'
        with self.assertRaisesRegex(ValueError, 'stored_totals_or_differences'):
            self.check()
        self.report = before
        self.report['totals'][0]['unsuccessful']['known_logical_tokens'] -= 1
        with self.assertRaisesRegex(ValueError, 'stored_totals_or_differences'):
            self.check()

    def test_verification_does_not_mutate_evidence(self):
        before = copy.deepcopy((self.plan, self.report, self.original))
        self.check()
        self.assertEqual((self.plan, self.report, self.original), before)


if __name__ == '__main__':
    unittest.main()

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_contract_comparison import audit_cell, development_gate
from contract_comparison import ARMS, build_condition
from run_context_comparison import write_json
from run_handoff_factors import sha
import test_documentation_comparison_audit as fixture_tools


class ContractComparisonAuditTests(unittest.TestCase):
    def cohort(self):
        return [{'task_id': str(n), 'arm': arm, 'record_status': 'evaluated',
                 'success': n % 2 == 0, 'unknown_usage_calls': 0,
                 'known_total_tokens': 90 if arm == ARMS[2] else 100}
                for n in range(4) for arm in ARMS]

    def test_candidate_must_pass_both_paired_controls_and_preserve_their_successes(self):
        rows = self.cohort()
        self.assertTrue(development_gate(rows)['development_gate_met'])
        rows[2]['success'] = False; rows[5]['success'] = True
        result = development_gate(rows)
        self.assertFalse(result['development_gate_met'])
        self.assertEqual(result['contrasts'][ARMS[0]]['paired_success_losses'], 1)
        rows = self.cohort()
        for r in rows:
            if r['arm'] == ARMS[1]: r['known_total_tokens'] = 90
        self.assertFalse(development_gate(rows)['development_gate_met'])

    def test_missing_or_unknown_cell_cannot_be_replaced_by_completed_pairs(self):
        for status, unknown in [('attempted_unevaluated', 1), ('not_run_after_stop', 0), ('evaluated', 1)]:
            rows = self.cohort(); rows[-1].update(record_status=status, unknown_usage_calls=unknown)
            result = development_gate(rows)
            self.assertFalse(result['development_gate_met'])
            self.assertTrue(all(d['candidate_minus_control_total_tokens'] is None for d in result['contrasts'].values()))
        rows = self.cohort()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            development_gate([*rows[:-1], rows[0]])
        rows[-1]['success'] = None
        with self.assertRaisesRegex(ValueError, 'Boolean'):
            development_gate(rows)

    def test_p47_actual_request_and_raw_usage_are_checked_against_the_fixed_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            item, original, plan, preflight = fixture_tools.DocumentationComparisonAuditTests().fixture(folder)
            plan['phase'] = 'P47'; write_json(folder / 'factor_plan.json', plan)
            limits = json.loads((folder / 'plan.json').read_text())
            limits['phase'] = 'P47'; write_json(folder / 'plan.json', limits)
            summary = json.loads((folder / 'summary.json').read_text())
            summary.update(arm=ARMS[0], transfer=build_condition(item, ARMS[0])[1])
            write_json(folder / 'summary.json', summary)
            evaluation = json.loads((folder / 'evaluation.json').read_text())
            evaluation['execution_summary_sha256'] = sha(folder / 'summary.json')
            write_json(folder / 'evaluation.json', evaluation)
            result = audit_cell(folder, item, ARMS[0], original, plan, preflight, True)
            self.assertEqual(result['known_total_tokens'], 51)
            # A shared prefix is accounted separately; unknown usage is not zero.
            item['prefix']['usage'] = [
                {'status': 'ok', 'input_tokens': 71, 'output_tokens': 13},
                {'status': 'timeout', 'input_tokens': None, 'output_tokens': None}]
            write_json(folder / 'prefix_usage.json', item['prefix']['usage'])
            result = audit_cell(folder, item, ARMS[0], original, plan, preflight, True)
            self.assertEqual(result['prefix_known_total_tokens'], 84)
            self.assertEqual(result['prefix_unknown_usage_calls'], 1)
            self.assertEqual(result['known_total_tokens'], 51)
            path = folder / 'call_001/request.json'; request = json.loads(path.read_text())
            changed = copy.deepcopy(request); changed['messages'][1]['content'] = 'altered task'
            write_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'actual request'):
                audit_cell(folder, item, ARMS[0], original, plan, preflight, True)
            write_json(path, request)
            path = folder / 'call_001/raw_response.json'; raw = json.loads(path.read_text())
            raw['usage'].update(prompt_tokens=51, total_tokens=52); write_json(path, raw)
            with self.assertRaisesRegex(ValueError, 'raw terminal'):
                audit_cell(folder, item, ARMS[0], original, plan, preflight, True)


if __name__ == '__main__': unittest.main()

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_documentation_comparison import ARMS, require_closed, usage_total


class DocumentationDiagnosticsTests(unittest.TestCase):
    def test_missing_unknown_usage_is_retained_and_numeric_imputation_rejected(self):
        calls = [{'status': 'ok', 'input_tokens': 100, 'output_tokens': 20},
                 {'status': 'error', 'input_tokens': None, 'output_tokens': None}]
        self.assertEqual(usage_total(calls),
                         {'model_calls': 2, 'known_total_tokens': 120, 'unknown_usage_calls': 1})
        calls[1]['input_tokens'] = 0
        with self.assertRaisesRegex(ValueError, 'imputed'):
            usage_total(calls)

    def test_diagnostics_cannot_select_only_completed_cells(self):
        ids = [f'P45_{n:02d}_{arm.upper()}' for n in range(1, 5) for arm in ARMS]
        report = {'phase': 'P45', 'batch_status': 'stopped', 'all_planned_cells_accounted': True,
                  'audit_errors': [], 'rows': [{'run_id': rid, 'record_status':
                    'evaluated' if i < 6 else 'not_run_after_stop'} for i, rid in enumerate(ids)]}
        state = {'status': 'stopped', 'planned': ids, 'completed': ids[:6]}
        require_closed(report, state)
        selected = copy.deepcopy(report)
        selected['rows'] = selected['rows'][:6]
        with self.assertRaises(ValueError):
            require_closed(selected, state)
        state['status'] = 'running'
        with self.assertRaises(ValueError):
            require_closed(report, state)


if __name__ == '__main__':
    unittest.main()

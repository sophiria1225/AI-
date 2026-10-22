import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from contract_comparison import ARMS
from diagnose_contract_comparison import feedback_followups, require_closed


class ContractDiagnosticsTests(unittest.TestCase):
    def test_closed_check_keeps_all_twelve_including_missing_cells(self):
        ids = [f'P47_{n:02d}_{arm.upper()}' for n in range(1, 5) for arm in ARMS]
        rows = [{'run_id': rid, 'record_status': 'evaluated' if i < 9 else 'not_run_after_stop'}
                for i, rid in enumerate(ids)]
        report = {'phase': 'P47', 'batch_status': 'stopped', 'all_planned_cells_accounted': True,
                  'audit_errors': [], 'rows': rows}
        state = {'status': 'stopped', 'planned': ids, 'completed': ids[:9]}
        require_closed(report, state)
        selected = copy.deepcopy(report); selected['rows'] = rows[:9]
        with self.assertRaises(ValueError): require_closed(selected, state)
        with self.assertRaises(ValueError): require_closed(report, {**state, 'status': 'running'})

    def fixture(self):
        usage = [{'id': 'c1', 'status': 'ok', 'input_tokens': 100, 'output_tokens': 10},
                 {'id': 'c2', 'status': 'ok', 'input_tokens': 120, 'output_tokens': 20},
                 {'id': 'c3', 'status': 'error', 'input_tokens': None, 'output_tokens': None}]
        feedback = {'call_id': 'c1', 'span_id': 's1', 'api': 'a__f', 'mode': 'public_schema',
                    'characters': 100, 'next_call_id': 'c2', 'canonical_feedback_in_immediate_next_input': True}
        events = [{'call': 'c2', 'span_id': 's2', 'stage': 'python_api', 'api_request_sent': True}]
        spans = {'s2': {'action': {'name': 'a__f', 'arguments': 'PRIVATE'}, 'observation': {'value': 'PRIVATE'}}}
        return usage, events, spans, feedback

    def test_followup_links_usage_without_claiming_savings_or_exporting_arguments(self):
        usage, events, spans, feedback = self.fixture()
        row, = feedback_followups(usage, events, spans, {'c2': ['print(api_schemas["a__f"])']}, [feedback])
        self.assertTrue(row['next_program_has_literal_schema_lookup'])
        self.assertEqual(row['next_same_api_dispatches'], 1)
        self.assertEqual(row['following_call_cost']['known_total_tokens'], 140)
        self.assertEqual(row['all_later_calls_cost']['unknown_usage_calls'], 1)
        self.assertFalse(row['cost_is_claimed_savings'])
        self.assertFalse(row['same_api_dispatch_is_claimed_correct_repair'])
        self.assertNotIn('PRIVATE', repr(row))

    def test_missing_or_unparseable_program_is_unknown_and_wrong_link_fails(self):
        usage, events, spans, feedback = self.fixture()
        for codes in ({}, {'c2': ['if (']}):
            row, = feedback_followups(usage, events, spans, codes, [feedback])
            self.assertIsNone(row['next_program_has_literal_schema_lookup'])
        feedback['next_call_id'] = 'c3'
        with self.assertRaisesRegex(ValueError, 'identity'):
            feedback_followups(usage, events, spans, {}, [feedback])


if __name__ == '__main__': unittest.main()

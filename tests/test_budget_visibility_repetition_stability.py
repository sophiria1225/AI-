import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_budget_visibility_repetitions import compare_traces, trace as inspect_trace
from test_budget_visibility_repetition import fixture
from test_budget_visibility_audit import audit_fixture


def trace():
    return {'run_id': 'synthetic', 'known_complete': True, 'calls': [
        {'request_sha256': 'request', 'without_current_wall_sha256': 'no-wall',
         'public_output_sha256': 'public', 'opaque_message_sha256': 'opaque'}]}


class RepetitionStabilityTests(unittest.TestCase):
    def test_current_wall_only_input_change_is_not_a_causal_or_token_claim(self):
        a, b = trace(), trace(); b['calls'][0]['request_sha256'] = 'different-wall'
        result = compare_traces(a, b)
        self.assertFalse(result['all_requests_equal'])
        self.assertTrue(result['all_public_outputs_equal'])
        self.assertTrue(result['first_request_difference_is_current_wall_only'])
        self.assertFalse(result['model_visible_token_sequences_compared'])
        self.assertFalse(result['causal_timing_effect_identified'])

    def test_unknown_tail_is_not_reported_as_stable(self):
        a, b = trace(), trace(); b['known_complete'] = False
        b['calls'].append({k: None for k in b['calls'][0]})
        result = compare_traces(a, b)
        self.assertIsNone(result['all_public_outputs_equal'])
        self.assertIsNone(result['all_requests_equal'])
        self.assertEqual(result['first_call_present_in_only_one_run'], 2)

    def test_opaque_and_public_differences_are_reported_separately(self):
        a, b = trace(), trace(); b['calls'][0]['opaque_message_sha256'] = 'other-opaque'
        result = compare_traces(a, b)
        self.assertTrue(result['all_public_outputs_equal'])
        self.assertFalse(result['all_opaque_messages_equal'])
        self.assertIsNone(result['first_public_output_difference'])
        self.assertEqual(result['first_opaque_message_difference'], 1)

    def test_known_missing_call_is_not_an_identical_full_transcript(self):
        a, b = trace(), trace(); b['calls'].append(copy.deepcopy(b['calls'][0]))
        result = compare_traces(a, b)
        self.assertFalse(result['all_public_outputs_equal'])
        self.assertEqual(result['compared_prefix_calls'], 1)
        self.assertEqual(result['first_call_present_in_only_one_run'], 2)

    def test_saved_inputs_are_hash_checked_and_hidden_wall_is_not_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fixture(folder=directory)
            row = audit_fixture(directory, result)
            inspected = inspect_trace(Path(directory), row)
            self.assertEqual(len(inspected['calls']), 2)
            self.assertFalse(inspected['known_complete'])  # fixture has no independent evaluator
            for call in inspected['calls']:
                self.assertEqual(call['request_sha256'], call['without_current_wall_sha256'])
                self.assertIsNotNone(call['public_output_sha256'])
            path = Path(directory) / 'records/context_pilot/BOC_P80_fixture/call_001/request.json'
            path.write_text(path.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'audited_record_changed'):
                inspect_trace(Path(directory), row)

    def test_missing_terminal_response_remains_unknown_during_trace_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fixture(folder=directory, actions=('echo', 'transport_error'))
            row = audit_fixture(directory, result)
            inspected = inspect_trace(Path(directory), row)
            self.assertFalse(inspected['known_complete'])
            self.assertEqual(len(inspected['calls']), 2)
            self.assertIsNone(inspected['calls'][-1]['public_output_sha256'])
            self.assertIsNone(compare_traces(inspected, inspected)['all_public_outputs_equal'])


if __name__ == '__main__': unittest.main()

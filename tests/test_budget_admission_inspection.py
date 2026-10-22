from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_budget_admission import residual_capacity, restore
from native_conversation import NativeConversation


class AdmissionInspectionTests(unittest.TestCase):
    def test_unused_total_is_not_all_available_for_output(self):
        row = residual_capacity(13000, 12000, 4096)
        self.assertEqual(row['positive_output_capacity'], 1000)
        self.assertEqual(row['classification'], 'smaller_output_cap_could_admit')
        self.assertFalse(row['completion_possible_claim'])
        self.assertEqual(residual_capacity(12000, 12500, 4096)['positive_output_capacity'], 0)

    def test_reservation_stop_must_be_consistent(self):
        with self.assertRaises(ValueError):
            residual_capacity(16096, 12000, 4096)
        with self.assertRaises(ValueError):
            residual_capacity(-1, 12000, 4096)

    def test_exact_reconstruction_keeps_rejected_turn(self):
        view = NativeConversation('fixture', {'instruction': 'fixture'})
        view.append({'role': 'assistant', 'content': 'not a tool call'},
                    [{'id': 's1', 'assistant': 'not a tool call', 'action': None,
                      'observation': {'format_error': 'tool required'}}])
        self.assertEqual(restore(view.messages()).messages(), view.messages())


if __name__ == '__main__':
    unittest.main()

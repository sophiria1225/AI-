from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_native_pair import canonical_transport_ids


class NativePairControls(unittest.TestCase):
    def payload(self, identifier, argument='same'):
        return {'messages': [{'role': 'assistant', 'tool_calls': [
            {'id': identifier, 'function': {'name': 'fixture', 'arguments': argument}}]},
            {'role': 'tool', 'tool_call_id': identifier, 'content': 'observed'}]}

    def test_ignore_only_paired_transport_ids_not_action_arguments(self):
        self.assertEqual(canonical_transport_ids(self.payload('a')),
                         canonical_transport_ids(self.payload('b')))
        self.assertNotEqual(canonical_transport_ids(self.payload('a')),
                            canonical_transport_ids(self.payload('b', 'different')))
        broken = self.payload('a'); broken['messages'][1]['tool_call_id'] = 'b'
        with self.assertRaises(ValueError):
            canonical_transport_ids(broken)


if __name__ == '__main__':
    unittest.main()

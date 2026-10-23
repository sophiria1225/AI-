import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_api_error_content_divergence import canonical_transport_references


def request(ident):
    return {'seed': 51, 'messages': [
        {'role': 'assistant', 'reasoning_content': 'retained', 'tool_calls': [
            {'id': ident, 'function': {'name': 'fixture', 'arguments': 'literal-id'}}]},
        {'role': 'tool', 'tool_call_id': ident, 'content': 'literal-id'}]}


class TransportReferenceTests(unittest.TestCase):
    def test_only_linked_reference_fields_are_renamed(self):
        a, b = request('first'), request('second'); saved = copy.deepcopy(a)
        self.assertEqual(canonical_transport_references(a), canonical_transport_references(b))
        self.assertEqual(a, saved)
        b['messages'][0]['reasoning_content'] = 'different'
        self.assertNotEqual(canonical_transport_references(a), canonical_transport_references(b))
        result = canonical_transport_references(a)
        self.assertEqual(result['messages'][0]['tool_calls'][0]['function']['arguments'], 'literal-id')
        self.assertEqual(result['messages'][1]['content'], 'literal-id')

    def test_orphan_and_duplicate_references_are_rejected(self):
        orphan = request('one'); orphan['messages'][1]['tool_call_id'] = 'absent'
        with self.assertRaises(ValueError): canonical_transport_references(orphan)
        duplicate = request('one'); duplicate['messages'].append(copy.deepcopy(duplicate['messages'][0]))
        with self.assertRaises(ValueError): canonical_transport_references(duplicate)


if __name__ == '__main__': unittest.main()

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_contract_feedback import schema_lookups


class SchemaLookupSyntaxTests(unittest.TestCase):
    def test_strings_comments_other_objects_and_dynamic_keys_are_not_literal_lookups(self):
        code = '''
# api_schemas['ignored__comment']
label = "api_schemas['ignored__string']"
print(other.get('ignored__object'))
print(api_schemas[key])
print(api_schemas.get('sample__send'))
print(api_schemas['sample__read'])
'''
        self.assertEqual(schema_lookups(code), {'sample__send', 'sample__read'})


if __name__ == '__main__': unittest.main()

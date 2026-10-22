import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_documentation_origin import verify_edits
from input_exposure_accounting import digest
from native_conversation import NativeConversation


class DocumentationOriginAuditTests(unittest.TestCase):
    def fixture(self):
        conversations = []
        for changed in (False, True):
            conv = NativeConversation('system', {'instruction': 'synthetic'})
            for number in range(2):
                action = {'name': 'run_python', 'arguments': json.dumps({'code': 'print(documentation)'})}
                obs = {'stdout': 'label\ndocumentation\n', 'status': 'ok', 'error': None,
                       'api_receipts': [{'span_id': 'inner'}]}
                if changed and number == 0:
                    obs['stdout'] = 'label\n[API documentation omitted; read archived span inner.]\n'
                    obs['stdout_view'] = {'omitted': True, 'source_span_id': 'outer0',
                                         'documentation_receipt_ids': ['inner'], 'literal_output_preserved': True}
                conv.append({'role': 'assistant', 'content': '', 'tool_calls': [
                    {'id': str(number), 'type': 'function', 'function': action}]}, [
                    {'id': f'outer{number}', 'assistant': '', 'action': action, 'observation': obs}])
            conversations.append(conv.messages())
        segments = [{'start': 0, 'end': 6, 'receipt_id': None, 'text_sha256': digest('label\n')},
                    {'start': 6, 'end': 19, 'receipt_id': 'inner', 'text_sha256': digest('documentation')},
                    {'start': 19, 'end': 20, 'receipt_id': None, 'text_sha256': digest('\n')}]
        meta = {'checks': [{'span_id': 'outer0', 'changed': True, 'recognized': True,
                           'receipt_group': 'documentation_only', 'segments': segments}], 'changed_outputs': 1}
        archive = {'inner': {'action': {'name': 'api_docs__show_api_doc'}}}
        return *conversations, meta, archive

    def test_exact_literals_and_reference_are_verified(self):
        result = verify_edits(*self.fixture())
        self.assertEqual(result, {'changed_outputs': 1, 'literal_characters_preserved': 7,
                                  'distinct_documentation_references': 1})

    def test_literal_loss_or_status_relabeling_is_rejected(self):
        for change in ('literal', 'status'):
            full, selected, meta, archive = self.fixture()
            value = json.loads(selected[3]['content'])
            if change == 'literal': value['observation']['stdout'] = value['observation']['stdout'].replace('label\n', '')
            else: value['observation']['status'] = 'success'
            selected[3]['content'] = json.dumps(value)
            with self.assertRaises(ValueError): verify_edits(full, selected, meta, archive)

    def test_partition_gaps_foreign_references_and_latest_edits_are_rejected(self):
        full, selected, meta, archive = self.fixture(); meta['checks'][0]['segments'].pop(0)
        with self.assertRaises(ValueError): verify_edits(full, selected, meta, archive)
        full, selected, meta, archive = self.fixture(); archive['inner']['action']['name'] = 'files__read'
        with self.assertRaises(ValueError): verify_edits(full, selected, meta, archive)
        full, selected, meta, archive = self.fixture(); selected[-1]['content'] = selected[3]['content']
        with self.assertRaises(ValueError): verify_edits(full, selected, meta, archive)


if __name__ == '__main__':
    unittest.main()

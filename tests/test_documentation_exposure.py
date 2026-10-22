import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from documentation_exposure import match_documentation_stdout, views
from handoff_factors import split_turns
from native_conversation import NativeConversation, recover_turn


class DocumentationExposureTests(unittest.TestCase):
    def fixture(self):
        value = {'api_name': 'read_item', 'parameters': {'item_id': 'integer'}}
        outer = {'status': 'ok', 'stdout': str(value) + '\n', 'stdout_truncated': False,
                 'api_receipts': [{'span_id': 's1', 'api': 'api_docs__show_api_doc', 'api_request_sent': True}],
                 'error': None, 'unknown_effects': False, 'declared_complete': False}
        spans = {'s1': {'action': {'name': 'api_docs__show_api_doc'},
                        'observation': {'observation': json.dumps(value), 'declared_complete': False}}}
        events = {'s1': {'stage': 'python_api', 'api_request_sent': True, 'effects_unknown': False}}
        return outer, spans, events

    def test_entire_known_documentation_rendering_can_be_identified_without_execution(self):
        outer, spans, events = self.fixture(); original = copy.deepcopy((outer, spans, events))
        result = match_documentation_stdout(outer, spans, events)
        self.assertTrue(result['matched'])
        self.assertEqual((outer, spans, events), original)

    def test_extra_task_fact_before_or_after_documentation_is_preserved(self):
        outer, spans, events = self.fixture()
        for value in ('Task has 7 items\n' + outer['stdout'], outer['stdout'] + 'Completed 2 items\n'):
            self.assertFalse(match_documentation_stdout({**outer, 'stdout': value}, spans, events)['matched'])

    def test_non_documentation_receipt_cannot_be_removed_based_on_api_like_fields(self):
        outer, spans, events = self.fixture(); spans['s1']['action']['name'] = 'file_system__show_file'
        self.assertFalse(match_documentation_stdout(outer, spans, events)['matched'])

    def test_mixed_receipts_and_errors_are_rejected_even_if_stdout_matches_a_schema(self):
        outer, spans, events = self.fixture()
        spans['s2'] = {'action': {'name': 'phone__search_contacts'}, 'observation': {'observation': []}}
        events['s2'] = dict(events['s1']); outer['api_receipts'].append({'span_id': 's2', 'api_request_sent': True})
        self.assertFalse(match_documentation_stdout(outer, spans, events)['matched'])
        outer, spans, events = self.fixture()
        for update in ({'error': 'TypeError'}, {'stdout_truncated': True}, {'declared_complete': True}):
            self.assertFalse(match_documentation_stdout({**outer, **update}, spans, events)['matched'])

    def test_unmatched_serialization_is_not_repaired_by_stripping_or_guessing(self):
        outer, spans, events = self.fixture(); outer['stdout'] = outer['stdout'].rstrip('\n')
        self.assertFalse(match_documentation_stdout(outer, spans, events)['matched'])

    def test_api_error_payload_is_kept_even_when_outer_program_printed_it_successfully(self):
        for value in ({'error': 'unknown API'}, {'detail': 'not found'}, 'Traceback: failed'):
            outer, spans, events = self.fixture()
            spans['s1']['observation']['observation'] = json.dumps(value)
            outer['stdout'] = str(value) + '\n'
            self.assertFalse(match_documentation_stdout(outer, spans, events)['matched'])

    def test_views_preserve_actions_latest_turn_task_data_and_source_archive(self):
        task = {'instruction': 'synthetic required task'}
        conversation = NativeConversation('unchanged public guide', task)
        prefix = {'public_task': task, 'events': [], 'spans': {}}
        for number in range(8):
            outer, spans, events = self.fixture()
            sid = f'inner{number}'
            value = {'api_name': 'read_item', 'description': 'Documentation. ' * 150}
            spans['s1']['observation']['observation'] = json.dumps(value)
            outer['stdout'] = str(value) + '\n'
            outer['api_receipts'][0]['span_id'] = sid
            if number == 2:
                outer.update(status='execution_error', error='synthetic failure')
            if number == 4:
                spans['s1']['action']['name'] = 'file_system__show_file'
                outer['api_receipts'][0]['api'] = 'file_system__show_file'
            prefix['spans'][sid] = spans['s1']
            prefix['events'].append({'span_id': sid, **events['s1']})
            call = {'id': f'c{number}', 'type': 'function', 'function': {'name': 'run_python',
                    'arguments': json.dumps({'code': 'print(documentation)', 'span_ids': []})}}
            conversation.append({'role': 'assistant', 'content': '', 'tool_calls': [call]}, [
                {'id': f's{number}', 'assistant': '', 'action': call['function'], 'observation': outer}])
        prefix['conversation_private'] = conversation.messages()
        original = copy.deepcopy(prefix)
        built, meta = views(prefix)
        self.assertEqual(prefix, original)
        self.assertEqual(meta['matched_documentation_outputs'], 5)
        before = split_turns(built['full_keep'].messages())
        after = split_turns(built['documentation_stdout_mask_keep'].messages())
        for number, (a, b) in enumerate(zip(before, after, strict=True)):
            self.assertEqual(a[0], b[0])
            if number in (2, 4, 7): self.assertEqual(a, b)
            else:
                obs = recover_turn(b)[0]['observation']
                self.assertTrue(obs['stdout_view']['omitted'])
                self.assertEqual(obs['stdout_view']['source_span_id'], f's{number}')


if __name__ == '__main__':
    unittest.main()

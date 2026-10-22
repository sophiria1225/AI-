import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_contract_feedback import audit_feedback_cell, feedback_summary, validate_feedback
from contract_comparison import ARMS
from contract_feedback import UNKNOWN_PARAMETER, canonical, make_feedback
from run_context_comparison import write_json

FUNCTION = {'name': 'sample__send', 'parameters': {'type': 'object',
            'properties': {'value': {'type': 'integer'}}}}


class FeedbackAuditTests(unittest.TestCase):
    def fixture(self, folder):
        schemas = {'sample__send': FUNCTION}; tools = [{'type': 'function', 'function': FUNCTION}]
        action = {'name': 'sample__send', 'arguments': json.dumps({'wrong': 'DO_NOT_ECHO'})}
        row = {'action': action, 'observation': {'format_error': UNKNOWN_PARAMETER}, 'api_request_sent': False}
        feedback = make_feedback(row, schemas, 'public_schema')
        error = 'RuntimeError: ' + canonical({'format_error': UNKNOWN_PARAMETER, 'contract_feedback': feedback})
        inner = {'id': 's1', 'action': action, 'observation': {**row['observation'], 'contract_feedback': feedback}}
        event = {'call': 'call_001', 'span_id': 's1', 'stage': 'python_api',
                 'api_request_sent': False, 'effects_unknown': False, 'new_tools': []}
        source = {'code': 'call_api("sample","send",wrong="DO_NOT_ECHO")', 'observations': [],
                  'api_schemas': schemas, 'program_index': 2}
        result = {'program_index': 2, 'status': 'execution_error', 'session_usable': True,
                  'stdout': '', 'stdout_truncated': False, 'error': error, 'api_requests': 0,
                  'declared_complete': False, 'unknown_effects': False}
        outer = {'id': 's2', 'action': {'name': 'run_python', 'arguments': json.dumps({'code': source['code'], 'span_ids': []})},
                 'observation': {k: result[k] for k in ('status', 'stdout', 'stdout_truncated', 'error',
                                                     'api_requests', 'declared_complete', 'unknown_effects')}}
        outer['observation']['api_receipts'] = [{'span_id': 's1', 'api': 'sample__send', 'api_request_sent': False}]
        events = [event, {'call': 'call_001', 'span_id': 's2', 'stage': 'model_tool',
                          'api_request_sent': False, 'effects_unknown': False, 'new_tools': []}]
        item = {'programs': [{}], 'prefix': {'spans': {}, 'events': [{'new_tools': ['sample__send']}]}}
        runtime = {'mode': 'public_schema', 'checked_requests': 1, 'feedback_events': [feedback_summary(feedback)],
                   'control_wall_seconds': .001, 'automatic_retries': 0, 'extra_model_calls': 0, 'extra_environment_requests': 0}
        for name, value in {'summary.json': {'contract_feedback': runtime}, 'events.json': events,
                            'spans.json': {'s1': inner, 's2': outer},
                            'usage.json': [{'id': 'call_001'}, {'id': 'call_002'}]}.items():
            write_json(folder / name, value)
        program = folder / 'programs/call_001_01'; program.mkdir(parents=True)
        write_json(program / 'input_private.json', source); write_json(program / 'result_private.json', result)
        wire = [{'kind': 'api', 'id': 1, 'program_index': 2, 'app': 'sample', 'api': 'send',
                 'arguments': {'wrong': 'DO_NOT_ECHO'}},
                {'kind': 'done', 'program_index': 2, 'stdout': '', 'stdout_truncated': False, 'error': error}]
        (program / 'wire_private.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in wire))
        following = folder / 'call_002'; following.mkdir()
        write_json(following / 'request.json', {'messages': [{'role': 'tool', 'content': json.dumps(outer['observation'])}]})
        return item, tools, schemas, inner, event

    def test_all_program_receipts_and_exact_contract_are_reconstructed_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); item, tools, schemas, _, _ = self.fixture(folder)
            result = audit_feedback_cell(folder, item, ARMS[0], tools, schemas)
            self.assertEqual(result['programs_checked'], 1)
            self.assertEqual(result['requests_checked'], 1)
            self.assertTrue(result['feedback_events'][0]['canonical_feedback_in_immediate_next_input'])
            self.assertEqual(len(result['source_sha256']), 3)
            self.assertEqual(result['code_programs_reexecuted'], 0)
            self.assertNotIn('DO_NOT_ECHO', json.dumps(result))

    def test_changed_contract_unexposed_contract_and_already_sent_feedback_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, schemas, span, event = self.fixture(Path(directory))
            changed = copy.deepcopy(span); changed['observation']['contract_feedback']['public_schema']['parameters']['required'] = ['value']
            with self.assertRaisesRegex(ValueError, 'exact already-exposed'):
                validate_feedback(changed, event, schemas, 'public_schema')
            with self.assertRaises(ValueError): validate_feedback(span, event, {}, 'public_schema')
            with self.assertRaises(ValueError): validate_feedback(span, {**event, 'api_request_sent': True}, schemas, 'public_schema')

    def test_saved_program_schema_or_runtime_counters_cannot_be_changed_silently(self):
        for mutation in ('schema', 'counter'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory); item, tools, schemas, _, _ = self.fixture(folder)
                if mutation == 'schema':
                    path = folder / 'programs/call_001_01/input_private.json'; source = json.loads(path.read_text())
                    source['api_schemas'] = {}; write_json(path, source)
                else:
                    path = folder / 'summary.json'; summary = json.loads(path.read_text())
                    summary['contract_feedback']['checked_requests'] = 0; write_json(path, summary)
                with self.assertRaises(ValueError): audit_feedback_cell(folder, item, ARMS[0], tools, schemas)


if __name__ == '__main__': unittest.main()

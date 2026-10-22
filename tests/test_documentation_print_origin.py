import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from documentation_print_origin import build_origin_view, printer_environment_guard, recognize
from handoff_factors import split_turns
from native_conversation import NativeConversation, recover_turn


class DocumentationPrintOriginTests(unittest.TestCase):
    def entry(self, name='read', value=None):
        return {'request': {'app': 'api_docs', 'api': 'show_api_doc',
                             'arguments': {'app_name': 'files', 'api_name': name}},
                'reply': {'ok': True, 'value': value or {'description': 'private-sentinel'}},
                'originally_sent': True, 'effects_unknown': False, 'declared_complete': False}

    def program(self, code, stdout, entries=None):
        return {'source': {'code': code}, 'expected': {'status': 'ok', 'stdout': stdout,
                 'stdout_truncated': False, 'error': None, 'unknown_effects': False,
                 'declared_complete': False}, 'entries': entries or [self.entry()]}

    def check(self, program, prefix=None):
        return recognize(program, [f's{i}' for i in range(len(program['entries']))],
                         prefix or [program['source']['code']])

    def test_print_origin_retains_identical_literal_and_task_claims(self):
        value = self.entry()['reply']['value']
        code = ("doc = call_api('api_docs', 'show_api_doc', app_name='files', api_name='read')\n"
                "print('Task complete')\nprint(doc)\nprint(" + repr(str(value)) + ")")
        program = self.program(code, 'Task complete\n' + str(value) + '\n' + str(value) + '\n')
        original = copy.deepcopy(program)
        meta, parts = self.check(program)
        self.assertTrue(meta['recognized'])
        self.assertEqual([p['text'] for p in parts if p['receipt_id'] is not None], [str(value)])
        self.assertIn('Task complete', ''.join(p['text'] for p in parts if p['receipt_id'] is None))
        self.assertNotIn('private-sentinel', json.dumps(meta))
        self.assertEqual(program, original)

    def test_finite_loop_labels_and_identical_receipts_keep_separate_origins(self):
        entries = [self.entry('a'), self.entry('b')]; value = entries[0]['reply']['value']
        code = ("for name in ['a', 'b']:\n"
                "    print(f'API: {name}')\n"
                "    print(call_api('api_docs','show_api_doc', app_name='files', api_name=name))")
        stdout = 'API: a\n' + str(value) + '\nAPI: b\n' + str(value) + '\n'
        meta, parts = self.check(self.program(code, stdout, entries))
        self.assertTrue(meta['recognized'])
        self.assertEqual([p['receipt_id'] for p in parts if p['receipt_id'] is not None], ['s0', 's1'])

    def test_json_renderer_assignment_and_argument_order_are_checked(self):
        value = self.entry()['reply']['value']
        code = ("import json\nx=call_api('api_docs','show_api_doc', api_name='read', app_name='files')\n"
                "print(json.dumps(x, indent=2, ensure_ascii=False))")
        meta, parts = self.check(self.program(code, json.dumps(value, indent=2, ensure_ascii=False) + '\n'))
        self.assertTrue(meta['recognized'])
        self.assertEqual(parts[0]['receipt_id'], 's0')

    def test_history_cannot_replace_printers_or_use_reflection_or_callbacks(self):
        current = "print(call_api('api_docs','show_api_doc',app_name='files',api_name='read'))"
        program = self.program(current, str(self.entry()['reply']['value']) + '\n')
        for previous in (
            'print = something', 'json = something', 'import sys', 'import json as j',
            'from json import dumps', 'f = print', 'x = json', 'json.dumps = something',
            'x = __builtins__', 'x = globals()', 'exec("print(1)")',
            'json.dumps(x, default=call_api)', 'print(x, file=sink)',
            'def f():\n    pass', 'x.__class__', 'x = object.method()',
        ):
            with self.subTest(previous=previous):
                meta, parts = self.check(program, [previous, current])
                self.assertFalse(meta['recognized'])
                self.assertEqual(parts, [])

    def test_ordinary_previous_data_work_does_not_need_reexecution(self):
        previous = "i=0\nwhile i < 2:\n    rows=call_api('files','read')\n    if len(rows) == 0:\n        break\n    i += 1\nprint(rows)"
        self.assertTrue(printer_environment_guard([previous]))

    def test_unknown_persistent_value_and_dynamic_expression_are_preserved(self):
        for code in ('print(previous_doc)', 'print("x" + "y")',
                     "x = call_api('api_docs','show_api_doc',app_name='files',api_name='read')\nprint(x['description'])"):
            meta, parts = self.check(self.program(code, 'anything\n'))
            self.assertFalse(meta['recognized'])
            self.assertEqual(parts, [])

    def test_request_or_output_tampering_fails_without_repairing(self):
        code = "print(call_api('api_docs','show_api_doc',app_name='files',api_name='read'))"
        stdout = str(self.entry()['reply']['value']) + '\n'
        program = self.program(code, stdout); program['entries'][0]['request']['arguments']['api_name'] = 'other'
        with self.assertRaisesRegex(ValueError, 'arguments'): self.check(program)
        with self.assertRaisesRegex(ValueError, 'actual saved output'): self.check(self.program(code, stdout + 'extra'))
        program = self.program(code, stdout, [self.entry(), self.entry()])
        with self.assertRaisesRegex(ValueError, 'actual saved output'): self.check(program)

    def test_api_errors_and_incomplete_outer_results_cannot_be_attributed(self):
        code = "print(call_api('api_docs','show_api_doc',app_name='files',api_name='read'))"
        for key, value in (('stdout_truncated', True), ('unknown_effects', True), ('error', 'failed'),
                           ('declared_complete', True), ('status', 'execution_error')):
            program = self.program(code, 'anything\n'); program['expected'][key] = value
            self.assertFalse(self.check(program)[0]['recognized'])
        program = self.program(code, 'anything\n'); program['entries'][0]['reply']['ok'] = False
        with self.assertRaises(ValueError): self.check(program)

    def test_recognizer_does_not_dispatch_api_or_run_imports(self):
        # A real evaluation would create the file. The syntax is rejected before
        # any output, imports or API dispatch; only ordinary JSON values exist.
        code = "__import__('pathlib').Path('/tmp/p44-should-never-exist').write_text('bad')"
        self.assertFalse(self.check(self.program(code, ''))[0]['recognized'])

    def test_finite_resource_limits_retain_unknown_programs(self):
        program = self.program('x=' + repr('a' * 50001), '')
        self.assertFalse(self.check(program)[0]['recognized'])
        program = self.program('for x in ' + repr(list(range(101))) + ':\n    print(x)', '')
        self.assertFalse(self.check(program)[0]['recognized'])

    def test_view_keeps_actions_literals_mixed_outputs_latest_turn_and_originals(self):
        task = {'instruction': 'synthetic task'}
        conversation = NativeConversation('same guide', task)
        prefix = {'public_task': task, 'spans': {}, 'events': []}
        programs = []
        for number in range(1, 9):
            value = {'description': 'documentation ' * 150}
            code = "print('Keep task claim')\nprint(call_api('api_docs','show_api_doc',app_name='files',api_name='read'))"
            obs = {'status': 'ok', 'stdout': 'Keep task claim\n' + str(value) + '\n',
                   'stdout_truncated': False, 'error': None, 'unknown_effects': False,
                   'declared_complete': False, 'api_receipts': []}
            call = f'call_{number:03d}'; inner = f'inner{number}'; outer = f'outer{number}'
            entry = self.entry(value=value)
            api = 'api_docs__show_api_doc'
            if number == 3:
                obs['status'] = 'execution_error'; obs['error'] = 'synthetic failure'
            if number == 4:
                # A response with task-like data must not be relabeled by its
                # identical shape or documentation-looking text.
                code = "print('Keep task claim')\nprint(call_api('files','read'))"
                api = 'files__read'
                entry['request'] = {'app': 'files', 'api': 'read', 'arguments': {}}
            obs['api_receipts'] = [{'span_id': inner, 'api': api, 'api_request_sent': True}]
            prefix['spans'][inner] = {'action': {'name': api}, 'observation': {'observation': json.dumps(value)}}
            prefix['events'].append({'span_id': inner, 'stage': 'python_api', 'call': call, 'api_request_sent': True})
            prefix['events'].append({'span_id': outer, 'stage': 'model_tool', 'call': call})
            action = {'name': 'run_python', 'arguments': json.dumps({'code': code, 'span_ids': []})}
            conversation.append({'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': call, 'type': 'function', 'function': action}]}, [
                {'id': outer, 'assistant': '', 'action': action, 'observation': obs}])
            programs.append({'name': call + '_01', 'source': {'code': code},
                             'expected': obs, 'entries': [entry]})
        prefix['conversation_private'] = conversation.messages()
        item = {'prefix': prefix, 'programs': programs}; before = copy.deepcopy(item)
        views, meta = build_origin_view(item)
        self.assertEqual(item, before)
        self.assertEqual(meta['changed_outputs'], 5)
        full, selected = [split_turns(views[name].messages()) for name in ('full_keep', 'documentation_origin_keep')]
        for number, (old, new) in enumerate(zip(full, selected), 1):
            self.assertEqual(old[0], new[0])
            if number in (3, 4, 8):
                self.assertEqual(old, new)
            else:
                obs = recover_turn(new)[0]['observation']
                self.assertTrue(obs['stdout'].startswith('Keep task claim\n'))
                self.assertEqual(obs['stdout_view']['documentation_receipt_ids'], [f'inner{number}'])
                self.assertTrue(obs['stdout'].endswith('\n'))


if __name__ == '__main__':
    unittest.main()

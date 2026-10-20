from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_native_execution import inspect_operations


def fixture():
    functions = [{'name': 'public__first', 'arguments': '{}'},
                 {'name': 'public__second', 'arguments': '{}'}]
    return dict(
        usage=[{'id': 'call_001', 'status': 'ok'}],
        records=[{'call': 'call_001', 'span_id': f's{i+1}', 'api_request_sent': True,
                  'effects_unknown': False, 'new_tools': []} for i in range(2)],
        spans={f's{i+1}': {'id': f's{i+1}', 'action': f,
                          'observation': {'observation': 'public result'}}
               for i, f in enumerate(functions)},
        payloads={'call_001': {'tools': [{'function': f} for f in functions]}},
        responses={'call_001': {'message': {'tool_calls': [{'function': f} for f in functions]}}},
        summary={'tool_turns': 2, 'api_requests': 2, 'unknown_effect_requests': 0})


class NativeExecutionAuditControls(unittest.TestCase):
    def test_inner_failure_is_separate_from_transport_and_task_success(self):
        f = fixture()
        f['spans']['s2']['observation']['observation'] = 'Execution failed. private detail'
        report = inspect_operations(**f)
        self.assertFalse(report['dispatch_audit_errors'])
        self.assertEqual(report['counts']['inner_execution_errors'], 1)
        self.assertEqual(report['counts']['returned_api_results_without_detected_error'], 1)
        self.assertNotIn('private detail', str(report))
        self.assertNotIn('public__', str(report))

    def test_unknown_effects_require_stopping_without_claiming_no_execution(self):
        f = fixture()
        f['spans']['s1']['observation'] = {'transport_error_type': 'TimeoutError'}
        f['records'][0]['effects_unknown'] = True
        f['summary']['unknown_effect_requests'] = 1
        self.assertTrue(inspect_operations(**f)['dispatch_audit_errors'])
        f['records'][1]['api_request_sent'] = False
        f['spans']['s2']['observation'] = {'not_executed': 'prior request has unknown effects'}
        f['summary']['api_requests'] = 1
        report = inspect_operations(**f)
        self.assertFalse(report['dispatch_audit_errors'])
        self.assertEqual(report['counts']['unknown_effect_requests'], 1)
        self.assertEqual(report['counts']['skipped_operations'], 1)

    def test_missing_reordered_and_newly_exposed_operations_are_detected(self):
        for mutation in ('missing', 'reordered', 'unoffered'):
            f = fixture()
            if mutation == 'missing':
                f['records'].pop()
            elif mutation == 'reordered':
                f['records'].reverse()
            else:
                f['payloads']['call_001']['tools'].pop()
                f['records'][0]['new_tools'] = ['public__second']
            with self.subTest(mutation=mutation):
                self.assertTrue(inspect_operations(**f)['dispatch_audit_errors'])

    def test_completion_blocks_later_sent_request_but_keeps_skipped_record(self):
        f = fixture()
        f['spans']['s1']['observation']['declared_complete'] = True
        self.assertTrue(inspect_operations(**f)['dispatch_audit_errors'])
        f['records'][1]['api_request_sent'] = False
        f['spans']['s2']['observation'] = {'not_executed': 'already declared'}
        f['summary']['api_requests'] = 1
        self.assertFalse(inspect_operations(**f)['dispatch_audit_errors'])


if __name__ == '__main__':
    unittest.main()

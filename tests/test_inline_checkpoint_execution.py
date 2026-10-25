"""Synthetic transport/executor integration; no generated code or real API runs."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inline_checkpoint_execution import execute_inline_response
from inline_checkpoint_protocol import projection_after_turn
from test_inline_checkpoint_protocol import VALID, fixture, response


def execute(message, *, finish='tool_calls', known=True, offered=True,
            status='ok', allowed=True):
    archived, received, read_calls = [], [], []
    prior = [{'id': 's1', 'action': {'name': 'synthetic_a'}, 'observation': {'value': 1}},
             {'id': 's2', 'action': {'name': 'synthetic_b'}, 'observation': {'value': 2}}]

    def record(row, display=True):
        sid = f's{len(prior) + len(archived) + 1}'
        archived.append({'id': sid, **deepcopy(row), 'display': display})
        return sid

    def program(source, observations, channel, **kwargs):
        # Capture data; do not interpret or execute the model-supplied string.
        received.append({'source': source, 'observations': deepcopy(observations),
                         'timeout': kwargs['timeout']})
        inner = {'action': {'name': 'synthetic__echo', 'arguments': '{"value":7}'},
                 'observation': {'value': 7}, 'api_request_sent': True, 'new_tools': []}
        kwargs['on_record'](inner)
        channel.fatal = status == 'unknown'
        return {'status': status, 'stdout': 'synthetic result', 'stdout_truncated': False,
                'api_requests': 1, 'declared_complete': False,
                'unknown_effects': channel.fatal,
                'error': None if status == 'ok' else 'synthetic failure'}

    with tempfile.TemporaryDirectory() as directory:
        rows, split = execute_inline_response(message, None, None, prior, record,
            offered=offered, finish_reason=finish, usage_known=known,
            out=Path(directory), storage=Path(directory), call_id='fixture',
            remaining_api=lambda: 4, may_continue=lambda: allowed,
            remaining_wall=lambda: 12, read_archive=lambda *args: read_calls.append(args),
            program=program)
    return rows, split, archived, received, read_calls


class InlineCheckpointExecutionTests(unittest.TestCase):
    def test_metadata_never_runs_and_exact_original_action_is_archived(self):
        message = response(VALID)
        original = deepcopy(message)
        rows, split, archived, received, _ = execute(message)
        self.assertEqual(message, original)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['source'], json.loads(
            message['tool_calls'][0]['function']['arguments'])['code'])
        self.assertEqual([s['id'] for s in received[0]['observations']], ['s1', 's2'])
        self.assertEqual(received[0]['timeout'], 12)
        self.assertEqual(archived[-1]['action'], message['tool_calls'][0]['function'])
        self.assertEqual(rows[-1]['action'], message['tool_calls'][0]['function'])
        self.assertNotIn('checkpoint', json.loads(
            split['execution_message']['tool_calls'][0]['function']['arguments']))
        transport = archived[-1]['inline_transport']
        self.assertEqual(transport['original_function_sha256'], split['binding']['original_function_sha256'])
        self.assertFalse(transport['execution_success_verified'])
        self.assertFalse(transport['semantics_verified'])

    def test_inner_receipt_and_outer_reference_are_preserved(self):
        rows, _, archived, _, _ = execute(response(VALID))
        self.assertFalse(archived[0]['display'])
        self.assertNotIn('inline_transport', archived[0])
        self.assertEqual(rows[0]['observation'], {'value': 7})
        self.assertEqual(archived[-1]['observation']['api_receipts'],
            [{'span_id': archived[0]['id'], 'api': 'synthetic__echo', 'api_request_sent': True}])

    def test_original_conversation_accepts_exact_raw_action_and_projection_closes(self):
        # Reuse the complete canonical old history without exposing it to any model.
        _, _, message, old = fixture()
        before, _ = old.for_model()
        message['tool_calls'][0]['id'] = 'inline-next'
        _, split, archived, _, _ = execute(message)
        outer = deepcopy(archived[-1]); outer['id'] = 's6'
        old.append(message, [outer])
        after, _ = old.for_model()
        views = projection_after_turn(before, after, split)
        self.assertEqual(views['ordinary'][-1], after[-1])
        self.assertEqual(old.messages()[-2]['tool_calls'][0]['function'], message['tool_calls'][0]['function'])
        self.assertIsNotNone(views['compacted'])

    def test_invalid_or_truncated_summary_does_not_retry_or_prevent_valid_program(self):
        for msg, finish in ((response({'completed': []}), 'tool_calls'),
                            (response(VALID), 'length')):
            rows, split, archived, received, _ = execute(msg, finish=finish)
            self.assertEqual(len(received), 1)
            self.assertIsNone(split['checkpoint'])
            self.assertEqual(rows[-1]['observation']['status'], 'ok')
            self.assertEqual(archived[-1]['action'], msg['tool_calls'][0]['function'])

    def test_execution_failure_and_unknown_effects_remain_literal_without_retry(self):
        for status in ('execution_error', 'unknown'):
            rows, split, _, received, _ = execute(response(VALID), status=status)
            self.assertEqual(len(received), 1)
            self.assertEqual(rows[-1]['observation']['status'], status)
            self.assertEqual(rows[-1]['observation']['error'], 'synthetic failure')
            self.assertEqual(rows[-1]['effects_unknown'], status == 'unknown')
            self.assertFalse(split['semantics_verified'])

    def test_budget_stop_preserves_nonexecution_and_raw_action(self):
        rows, _, archived, received, _ = execute(response(VALID), allowed=False)
        self.assertEqual(received, [])
        self.assertIn('not_executed', rows[-1]['observation'])
        self.assertEqual(archived[-1]['action'], response(VALID)['tool_calls'][0]['function'])

    def test_unoffered_extra_metadata_is_not_silently_accepted(self):
        rows, split, _, received, _ = execute(response(VALID), offered=False)
        self.assertEqual(received, [])
        self.assertIn('format_error', rows[-1]['observation'])
        self.assertIsNone(split['binding'])

    def test_missing_metadata_preserves_ordinary_action_and_archive(self):
        message = response()
        rows, split, archived, received, _ = execute(message)
        self.assertEqual(len(received), 1)
        self.assertEqual(split['execution_message'], message)
        self.assertNotIn('inline_transport', archived[-1])
        self.assertEqual(rows[-1]['action'], message['tool_calls'][0]['function'])

    def test_unknown_usage_and_malformed_response_block_before_program_dispatch(self):
        with self.assertRaisesRegex(ValueError, 'unknown_usage_blocks'):
            execute(response(VALID), known=False)
        for malformed in (False, {'bad': 'shape'}, ['not an object']):
            message = response(VALID); message['tool_calls'] = malformed
            with self.assertRaisesRegex(ValueError, 'tool_call_objects_required'):
                execute(message)


if __name__ == '__main__':
    unittest.main()

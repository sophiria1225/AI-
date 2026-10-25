import json
from pathlib import Path
import tempfile
import unittest

from required_inline_checkpoint_worker_fixture import ROOT, audit_fixture, fixture
from audit_required_inline_checkpoint_trace import audit_trace
from whole_task_required_inline_checkpoint import initial_conversation


def recheck(folder):
    trial = Path(folder) / 'records/context_pilot/BOC_P120_fixture'
    original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
    config = json.loads((trial / 'plan.json').read_text())
    public = json.loads((trial / 'public_task.json').read_text())
    return audit_trace(trial, config, initial_conversation(original, public))


class InlineCheckpointAuditTests(unittest.TestCase):
    def test_both_policies_reconstruct_all_requests_and_whole_costs_without_external_execution(self):
        for policy in ('single_checkpoint', 'inline_checkpoint'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                run = fixture(policy=policy, actions=('echo', 'echo', 'echo', 'echo', 'finish'), folder=folder)
                checked = audit_fixture(folder, run)
                self.assertEqual(checked['known_total_tokens'], run['result']['known_total_tokens'])
                self.assertEqual(checked['usage_by_role'], run['result']['usage_by_role'])
                self.assertEqual(checked['suffix_api_requests'], 5)
                self.assertTrue(checked['checkpoint_installed'])
                self.assertEqual(checked['additional_model_calls'], 0)
                self.assertEqual(checked['additional_API_requests'], 0)
                self.assertEqual(checked['additional_tokenizer_calls'], 0)

    def test_invalid_omitted_and_truncated_metadata_and_valid_terminal_checkpoint_are_retained(self):
        options = [{'summary_mode': m} for m in ('invalid', 'missing', 'truncated')]
        options += [{'actions': ('echo', 'echo', 'echo', 'finish')}]
        for parameters in options:
            with self.subTest(parameters=parameters), tempfile.TemporaryDirectory() as folder:
                run = fixture(folder=folder, **{'actions': ('echo', 'echo', 'echo', 'echo', 'finish'), **parameters})
                checked = audit_fixture(folder, run)
                self.assertFalse(checked['checkpoint_installed'])
                self.assertEqual(checked['unknown_usage_calls'], 0)

    def test_unknown_usage_and_missing_terminal_cannot_gain_execution_or_a_zero_cost(self):
        for action in ('unknown', 'transport_error'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as folder:
                run = fixture(actions=('echo', 'echo', 'echo', action), folder=folder)
                checked = audit_fixture(folder, run)
                self.assertEqual(checked['unknown_usage_calls'], 1)
                self.assertEqual(checked['suffix_api_requests'], 3)
                self.assertFalse(checked['checkpoint_installed'])

    def test_budget_stops_and_bad_initial_cache_remain_auditable(self):
        for parameters in ({'token_limit': 44000}, {'token_limit': 50000},
                           {'first_cached': 1}, {'count_delay': 61}):
            with self.subTest(parameters=parameters), tempfile.TemporaryDirectory() as folder:
                run = fixture(actions=('echo', 'echo', 'echo', 'echo', 'finish'), folder=folder, **parameters)
                checked = audit_fixture(folder, run)
                self.assertEqual(checked['model_calls'], run['result']['model_calls'])
                self.assertEqual(checked['known_total_tokens'], run['result']['known_total_tokens'])

    def test_changed_request_schema_cost_count_or_program_source_is_rejected(self):
        for target in ('request', 'schema', 'requirement', 'cost', 'count', 'program', 'binding', 'decision'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                run = fixture(actions=('echo', 'echo', 'echo', 'echo', 'finish'), folder=folder)
                audit_fixture(folder, run)
                trial = Path(folder) / 'records/context_pilot/BOC_P120_fixture'
                if target in ('request', 'schema', 'requirement'):
                    path = trial / 'call_004/request.json'
                    data = json.loads(path.read_text())
                    if target == 'request': data['messages'][-2]['content'] += ' changed'
                    elif target == 'requirement': data['tools'][0]['function']['parameters']['required'].remove('checkpoint')
                    else: del data['tools'][0]['function']['parameters']['properties']['checkpoint']
                elif target == 'cost':
                    path = trial / 'summary.json'; data = json.loads(path.read_text())
                    data['known_total_tokens'] -= 1
                elif target == 'count':
                    path = trial / 'inline_input_counts.json'; data = json.loads(path.read_text())
                    data[-1]['messages_sha256'] = '0' * 64
                elif target == 'program':
                    path = trial / 'programs/call_004_01/input_private.json'; data = json.loads(path.read_text())
                    data['code'] = 'different submitted code'
                elif target == 'binding':
                    path = trial / 'events.json'; data = json.loads(path.read_text())
                    next(e for e in data if 'inline_transport' in e)['inline_transport']['code_sha256'] = '0' * 64
                else:
                    path = trial / 'inline_checkpoint_private.json'; data = json.loads(path.read_text())
                    data['decision']['accepted'] = False
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError): recheck(folder)


if __name__ == '__main__':
    unittest.main()

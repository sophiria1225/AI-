from pathlib import Path
import sys
import unittest
import tempfile
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))
from single_checkpoint_worker_fixture import fixture, audit_fixture


class SingleCheckpointWorkerTests(unittest.TestCase):
    def test_summary_is_charged_in_the_worker_but_never_sent_to_environment(self):
        result = fixture(policy='single_checkpoint', actions=('echo', 'echo', 'echo', 'finish'))
        row = result['result']
        self.assertEqual(row['stop_reason'], 'agent_declared_complete')
        self.assertTrue(row['cleanup_confirmed'])
        self.assertEqual(result['programs'], ['echo', 'echo', 'echo', 'finish'])
        self.assertEqual(row['model_calls'], 5)
        self.assertEqual(row['api_requests'], 4)
        self.assertEqual(row['usage_by_role']['focus']['calls'], 1)
        self.assertEqual(row['usage_by_role']['agent']['calls'], 4)
        self.assertEqual(row['known_total_tokens'], sum(r['input_tokens'] + r['output_tokens']
                         for r in row['usage_by_role'].values()))
        self.assertTrue(row['checkpoint_control']['checkpoint_installed'])
        self.assertEqual(len(result['saved']['checkpoint_history_views']), 4)
        self.assertEqual(sum(m['role'] == 'assistant' for m in result['saved']['conversation_private']), 4)

    def test_full_control_uses_same_initial_input_and_counts_all_agent_calls(self):
        actions = ('echo', 'echo', 'echo', 'finish')
        full = fixture(policy='full', actions=actions)
        compact = fixture(policy='single_checkpoint', actions=actions)
        self.assertEqual(full['captured'][0]['messages'], compact['captured'][0]['messages'])
        self.assertEqual(full['result']['model_calls'], 4)
        self.assertEqual(full['result']['usage_by_role']['focus']['calls'], 0)
        self.assertFalse(full['result']['checkpoint_control']['checkpoint_installed'])

    def test_stop_after_API_prevents_summary_and_next_agent_call(self):
        result = fixture(policy='single_checkpoint', stop_after_api=True)
        self.assertEqual(result['result']['stop_reason'], 'user_stop')
        self.assertEqual(len(result['captured']), 1)
        self.assertEqual(result['programs'], ['echo'])

    def test_unknown_API_effect_or_cleanup_failure_keeps_batch_stop(self):
        from api_error_comparison import disposition
        for options in ({'unknown_api': True}, {'cleanup_ok': False}, {'first_cached': 1}):
            with self.subTest(options=options):
                result = fixture(policy='single_checkpoint', **options)
                self.assertEqual(disposition(result['result']), 'stop_batch')

    def test_all_saved_calls_and_checkpoint_inputs_replay_from_the_archive(self):
        for policy in ('full', 'single_checkpoint'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                result = fixture(policy=policy, actions=('echo', 'echo', 'echo', 'finish'), folder=folder)
                audit = audit_fixture(folder, result)
                self.assertEqual(audit['known_total_tokens'], result['result']['known_total_tokens'])
                self.assertEqual(audit['checkpoint_installed'], policy == 'single_checkpoint')
                self.assertEqual(audit['suffix_api_requests'], 4)
                self.assertEqual(audit['additional_model_calls'], 0)

    def test_audit_rejects_a_changed_checkpoint_input_or_free_summary_cost(self):
        for altered in ('request', 'summary_cost'):
            with self.subTest(altered=altered), tempfile.TemporaryDirectory() as folder:
                result = fixture(policy='single_checkpoint', actions=('echo', 'echo', 'echo', 'finish'), folder=folder)
                audit_fixture(folder, result)
                trial = Path(folder) / 'records/context_pilot/BOC_P118_fixture'
                if altered == 'request':
                    path = trial / 'call_005/request.json'
                    value = json.loads(path.read_text())
                    value['messages'][2]['content'] = 'tampered checkpoint'
                else:
                    path = trial / 'summary.json'
                    value = json.loads(path.read_text())
                    value['known_total_tokens'] -= 10020
                path.write_text(json.dumps(value))
                from audit_single_checkpoint_trace import audit_trace
                from whole_task_single_checkpoint import initial_conversation
                root = Path(__file__).resolve().parents[1]
                original = json.loads((root / 'configs/P29_stateful_code_v01.json').read_text())
                config = json.loads((trial / 'plan.json').read_text())
                public = json.loads((trial / 'public_task.json').read_text())
                with self.assertRaises(ValueError):
                    audit_trace(trial, config, initial_conversation(original, public))

    def test_audit_keeps_failed_and_unrecorded_summary_costs_and_skipped_opportunities(self):
        for options in ({'summary_mode': 'invalid'}, {'summary_mode': 'unknown'},
                        {'summary_mode': 'transport_error'}, {'token_limit': 50000}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as folder:
                result = fixture(policy='single_checkpoint', actions=('echo', 'echo', 'echo', 'finish'),
                                 folder=folder, **options)
                audited = audit_fixture(folder, result)
                self.assertFalse(audited['checkpoint_installed'])
                self.assertEqual(audited['unknown_usage_calls'],
                                 int(options.get('summary_mode') in ('unknown', 'transport_error')))
                self.assertEqual(audited['usage_by_role'], result['result']['usage_by_role'])


if __name__ == '__main__':
    unittest.main()

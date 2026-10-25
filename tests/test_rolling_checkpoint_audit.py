import json
from pathlib import Path
import tempfile
import unittest

from rolling_checkpoint_worker_fixture import ROOT, audit_fixture, fixture
from audit_rolling_checkpoint_trace import audit_trace
from whole_task_rolling_checkpoint import initial_conversation


def replay(folder, run):
    trial = Path(folder)/'records/context_pilot'/run['result']['run_id']
    config = json.loads((trial/'plan.json').read_text())
    public = json.loads((trial/'public_task.json').read_text())
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    return audit_trace(trial, config, initial_conversation(original, public))


class RollingAuditTests(unittest.TestCase):
    def test_repeated_controls_and_all_roles_replay_without_external_execution(self):
        for policy in ('single_checkpoint','rolling_separate','rolling_inline'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                run = fixture(policy=policy, actions=('echo',)*12+('finish',), api_limit=32, folder=folder)
                audit = audit_fixture(folder, run)
                self.assertEqual(audit['known_total_tokens'], run['result']['known_total_tokens'])
                self.assertEqual(audit['model_calls'], run['result']['model_calls'])
                self.assertEqual(audit['additional_model_calls'], 0)
                self.assertEqual(audit['additional_API_requests'], 0)
                self.assertEqual(audit['additional_tokenizer_calls'], 0)
                if policy != 'single_checkpoint':
                    self.assertEqual(audit['checkpoint_installations'], 3)

    def test_closed_failures_and_undispatched_or_final_opportunities_replay(self):
        variants = [
            {'policy':'rolling_separate','max_calls':4,'actions':('echo',)*3+('finish',)},
            {'policy':'rolling_separate','token_limit':55000,'actions':('echo',)*3+('finish',)},
            {'policy':'rolling_separate','focus_input_tokens':64000,'actions':('echo',)*3+('finish',)},
            {'actions':('echo',)*3+('finish',)},
            {'policy':'rolling_separate','summary_mode':('valid','unknown'),'actions':('echo',)*12},
            {'policy':'rolling_separate','summary_mode':('valid','transport_error'),'actions':('echo',)*12},
            {'actions':('echo',)*7+('unknown',)},
            {'actions':('echo',)*7+('transport_error',)},
            {'summary_mode':'invalid','actions':('echo',)*12+('finish',)},
            {'summary_mode':'missing','actions':('echo',)*12+('finish',)},
            {'summary_mode':'truncated','actions':('echo',)*12+('finish',)},
            {'policy':'rolling_separate','summary_mode':'invalid','actions':('echo',)*12+('finish',)},
            {'first_cached':1}, {'count_delay':61}, {'stop_after_api':True},
            {'unknown_api':True}, {'cleanup_ok':False},
            {'max_calls':3,'actions':('echo',)*8},
            {'token_limit':70000,'actions':('echo',)*8},
        ]
        for options in variants:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as folder:
                run = fixture(**options, api_limit=32, folder=folder)
                audit = audit_fixture(folder, run)
                self.assertEqual(audit['known_total_tokens'], run['result']['known_total_tokens'])
                self.assertEqual(audit['unknown_usage_calls'], run['result']['unknown_usage_calls'])

    def test_second_summary_request_change_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            run = fixture(policy='rolling_separate', actions=('echo',)*12+('finish',), api_limit=32, folder=folder)
            audit_fixture(folder, run)
            calls = [c['id'] for c in run['saved']['usage'] if c['role']=='focus']
            path = Path(folder)/'records/context_pilot'/run['result']['run_id']/calls[1]/'request.json'
            obj = json.loads(path.read_text())
            obj['messages'][1]['content'] = '{}'
            path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, 'actual_rolling_request_differs'):
                replay(folder, run)

    def test_recurrent_boundary_cost_count_and_execution_mutations_are_detected(self):
        cases = (
            ('rolling_offers_private', lambda x: x[1]['offer'].__setitem__('cutoff', 2)),
            ('rolling_closed_private', lambda x: x[1].__setitem__('ordinary_sha256', 'wrong')),
            ('rolling_input_counts', lambda x: x[-1].__setitem__('messages_sha256', 'wrong')),
            ('rolling_controls', lambda x: next(r for r in x if r['status']=='checkpoint_decided').__setitem__('compacted_input_tokens', 1)),
            ('summary', lambda x: x['usage_by_role']['focus'].__setitem__('calls', 0)),
            ('events', lambda x: next(r for r in x if 'inline_transport' in r)['inline_transport'].__setitem__('original_payload_sha256', 'wrong')),
        )
        for name, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                run = fixture(actions=('echo',)*12+('finish',), api_limit=32, folder=folder)
                audit_fixture(folder, run)
                path = Path(folder)/'records/context_pilot'/run['result']['run_id']/(name+'.json')
                obj = json.loads(path.read_text())
                if name == 'summary':
                    obj['usage_by_role']['focus']['calls'] = 1
                else:
                    mutate(obj)
                path.write_text(json.dumps(obj))
                with self.assertRaises(ValueError):
                    replay(folder, run)

    def test_second_focus_cannot_be_removed_from_the_shared_total(self):
        with tempfile.TemporaryDirectory() as folder:
            run = fixture(policy='rolling_separate', actions=('echo',)*12+('finish',), api_limit=32, folder=folder)
            audit_fixture(folder, run)
            path = Path(folder)/'records/context_pilot'/run['result']['run_id']/'summary.json'
            obj = json.loads(path.read_text()); obj['known_total_tokens'] -= 10020
            path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, 'worker_accounting_changed'):
                replay(folder, run)


if __name__ == '__main__':
    unittest.main()

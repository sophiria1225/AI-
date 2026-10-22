import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_new_move_scope as fixtures
from test_public_name_catalog import tool
from ordinary_completion_control import check_prefix, prefix_digest
from completion_control_comparison import PLAN, validate, can_continue_batch
from run_completion_control import run_condition
from probe_completion_control import public_summary
from audit_completion_control import audit_controller
from run_handoff_factors import ROOT, read


def fixture(): return fixtures.NewMoveScopeTests().fixture()


class MonitorTests(unittest.TestCase):
    def test_support_requires_the_last_move_not_a_matching_partial_subset(self):
        t, s, e, u, _ = fixture()
        for n in range(1, len(u)):
            self.assertNotEqual(check_prefix(t, {x['span_id']: s[x['span_id']] for x in e[:n]}, e[:n], u[:n])['trace_support'], 'supported')
        self.assertEqual(check_prefix(t, s, e, u)['trace_support'], 'supported')

    def test_missing_clock_changed_principal_and_failed_moves_do_not_support_completion(self):
        for case in ('clock', 'principal', 'failed_move'):
            with self.subTest(case=case):
                t, s, e, u, _ = fixture()
                if case == 'clock': s['s2']['observation']['observation'] = '{}'
                elif case == 'principal':
                    args = json.loads(s['s6']['action']['arguments']); args['access_token'] = 'different-synthetic-token'
                    s['s6']['action']['arguments'] = json.dumps(args)
                else: s['s6']['observation']['observation'] = '{"error":"synthetic failure"}'
                self.assertEqual(check_prefix(t, s, e, u)['trace_support'], 'unknown')

    def test_extra_app_effects_unknown_effects_or_late_same_message_mutation_block_support(self):
        for case in ('other_app', 'unknown_effect', 'late_file_mutation'):
            with self.subTest(case=case):
                t, s, e, u, _ = fixture()
                if case == 'unknown_effect': e[-1]['effects_unknown'] = True
                else:
                    name = 'venmo__create_payment' if case == 'other_app' else 'file_system__delete_file'
                    s['extra'] = {'action': {'name': name, 'arguments': '{"access_token":"synthetic-token"}'}, 'observation': {'observation': '{}'}}
                    e.append({'span_id': 'extra', 'call': u[-1]['id'], 'api_request_sent': True})
                self.assertEqual(check_prefix(t, s, e, u)['trace_support'], 'unknown')

    def test_future_or_reordered_events_and_unaccounted_usage_remain_unknown(self):
        for case in ('future', 'reorder', 'duplicate', 'unknown_usage', 'ground_truth'):
            with self.subTest(case=case):
                t, s, e, u, _ = fixture()
                if case == 'future': e[-1]['call'] = 'call_007'
                elif case == 'reorder': e.reverse()
                elif case == 'duplicate': e.append(e[-1])
                elif case == 'unknown_usage': u[-1]['usage_known'] = False
                else: t['ground_truth_loaded'] = True
                self.assertEqual(check_prefix(t, s, e, u)['trace_support'], 'unknown')

    def test_wrong_destination_is_contradicted_and_unsupported_task_is_unknown(self):
        t, s, e, u, _ = fixture()
        a = json.loads(s['s6']['action']['arguments']); a['destination_file_path'] = a['destination_file_path'].replace('/Peru/', '/Italy/')
        s['s6']['action']['arguments'] = json.dumps(a)
        r = json.loads(s['s6']['observation']['observation']); r['destination_file_path'] = a['destination_file_path']
        s['s6']['observation']['observation'] = json.dumps(r)
        self.assertEqual(check_prefix(t, s, e, u)['trace_support'], 'contradicted')
        t['instruction'] += ' Also send an email.'
        self.assertEqual(check_prefix(t, s, e, u)['trace_support'], 'unknown')

    def test_digest_binds_evidence_and_the_check_does_not_mutate_it(self):
        t, s, e, u, _ = fixture(); before = copy.deepcopy((t, s, e, u))
        digest = prefix_digest(t, s, e, u); check_prefix(t, s, e, u)
        self.assertEqual(before, (t, s, e, u)); self.assertEqual(digest, prefix_digest(t, s, e, u))
        s['s6']['observation']['observation'] = '{}'
        self.assertNotEqual(digest, prefix_digest(t, s, e, u))


class Bridge:
    mode = 'ok'
    sent = []
    def __init__(self, *_):
        self.task, self.spans, _, _, _ = fixture()
    def request(self, request):
        if request['op'] == 'init': return {'ok': True, 'result': self.task}
        action = request['call']; type(self).sent.append(copy.deepcopy(action))
        if action['app'] == 'supervisor':
            if self.mode == 'unknown_completion': raise TimeoutError('synthetic ambiguous completion')
            if self.mode == 'failed_completion': return {'ok': False, 'error': 'synthetic rejection'}
            return {'ok': True, 'result': {'observation': '{}', 'declared_complete': True}}
        fn = action['app']+'__'+action['api']
        if fn == 'file_system__delete_file': return {'ok': True, 'result': {'observation': '{}'}}
        span = next(s for s in self.spans.values() if s['action']['name'] == fn and json.loads(s['action']['arguments']) == action['args'])
        result = copy.deepcopy(span['observation'])
        if self.mode == 'missing_clock' and action['app'] == 'phone': result['observation'] = '{}'
        return {'ok': True, 'result': result}
    def close(self): pass


class Inference:
    def __init__(self, *_): self.calls = []; self.started = time.monotonic()
    @property
    def tokens(self): return 15*len(self.calls)
    def call(self, *_):
        n = len(self.calls)+1
        if n > 7: raise AssertionError('unexpected generation')
        self.calls.append({'id': f'call_{n:03d}', 'usage_known': True, 'input_tokens': 10, 'output_tokens': 5})
        return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': f'c{n}', 'type': 'function',
            'function': {'name': 'run_python', 'arguments': json.dumps({'code': str(n), 'span_ids': []})}}]}


class Session:
    late_mutation = False
    def __init__(self, *_):
        self.usable = True; self.state = {'status': 'active', 'programs': [], 'container_removed': False}
    def run(self, code, observations, channel, *, on_record, **kwargs):
        n = int(code)
        if n <= 6:
            action = fixture()[1][f's{n}']['action']; app, api = action['name'].split('__')
            args = json.loads(action['arguments'])
        else: app, api, args = 'supervisor', 'complete_task', {'status': 'success'}
        channel.exchange({'kind': 'api', 'id': 1, 'app': app, 'api': api, 'arguments': args})
        if n == 6 and self.late_mutation:
            channel.exchange({'kind': 'api', 'id': 2, 'app': 'file_system', 'api': 'delete_file',
                'arguments': {'access_token': 'synthetic-token'}})
        for row in channel.rows: on_record(row)
        self.state['programs'].append({'private': 'SYNTHETIC PRIVATE OUTPUT'})
        return {'status': 'ok', 'stdout': '', 'stdout_truncated': False,
            'api_requests': sum(r['api_request_sent'] for r in channel.rows),
            'declared_complete': channel.complete, 'unknown_effects': channel.fatal}
    def close(self): self.state.update(status='closed', container_removed=True)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        Bridge.mode = 'ok'; Bridge.sent = []; Session.late_mutation = False
        self.plan = read(ROOT / PLAN); self.original = read(ROOT / self.plan['source_config'])

    def run_fixture(self, directory, budget=160):
        plan = copy.deepcopy(self.plan); plan['api_budget_by_task']['34d9492_1'] = budget
        task, spans, _, _, _ = fixture(); fields = {}
        for span in spans.values():
            fn = span['action']; fields[fn['name']] = {k: {} for k in json.loads(fn['arguments'])}
        fields['supervisor__complete_task'] = {'status': {}}
        fields['file_system__delete_file'] = {'access_token': {}}
        tools = [tool(n, f) for n, f in fields.items()]
        (Path(directory)/'records/context_pilot').mkdir(parents=True)
        with patch('run_completion_control.Bridge', Bridge), patch('run_completion_control.PersistentApiPython', Session), \
             patch('run_completion_control.OrdinaryInference', Inference), \
             patch('run_completion_control.db_hashes', return_value={'dbs/fixture': 'same'}):
            summary = run_condition(Path(directory), plan, self.original,
                {'34d9492_1': {'public_task': task, 'initial_database_hashes': {'dbs/fixture': 'same'}}},
                tools, *plan['run_order'][1])
        return summary, Path(directory)/'records/context_pilot'/plan['run_order'][1][2]

    def test_fixed_protocol_rejects_extra_attempts_budget_or_changed_notification(self):
        validate(self.plan, self.original)
        for k, v in [('max_controller_completion_attempts', 2), ('max_calls', 81),
                     ('run_order', self.plan['run_order'][::-1]), ('notification', 'hint_to_model')]:
            with self.subTest(k=k), self.assertRaises(ValueError): validate({**self.plan, k:v}, self.original)

    def test_complete_prefix_dispatches_once_through_channel_without_another_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, trial = self.run_fixture(tmp)
            self.assertEqual(s['stop_reason'], 'controller_declared_complete'); self.assertTrue(can_continue_batch(s))
            self.assertEqual(s['model_calls'], 6); self.assertEqual(s['api_requests'], 7)
            self.assertEqual(s['known_total_tokens'], 90); self.assertEqual(s['controller_checks'], 6)
            self.assertEqual(s['controller_completion_attempts'], 1)
            events = read(trial/'events.json'); self.assertEqual(events[-1]['stage'], 'controller_api')
            self.assertEqual(events[-1]['call'], 'controller_001')
            spans = read(trial/'spans.json'); self.assertEqual(spans[events[-1]['span_id']]['assistant'], '')
            self.assertEqual(Bridge.sent[-1], {'app':'supervisor','api':'complete_task','args':{'status':'success'}})
            self.assertNotIn('SYNTHETIC PRIVATE OUTPUT', json.dumps(public_summary(s)))
            self.assertTrue(s['python_session']['container_removed'])

    def test_unknown_evidence_and_later_same_message_mutation_keep_ordinary_continuation(self):
        for mode, late in [('missing_clock', False), ('ok', True)]:
            with self.subTest(mode=mode, late=late), tempfile.TemporaryDirectory() as tmp:
                Bridge.mode = mode; Session.late_mutation = late
                s, trial = self.run_fixture(tmp)
                self.assertEqual(s['stop_reason'], 'agent_declared_complete'); self.assertEqual(s['model_calls'], 7)
                self.assertEqual(s['controller_completion_attempts'], 0)
                self.assertFalse(any(e['stage'] == 'controller_api' for e in read(trial/'events.json')))

    def test_controller_completion_uses_the_same_api_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, _ = self.run_fixture(tmp, budget=6)
            self.assertEqual(s['stop_reason'], 'api_request_limit'); self.assertEqual(s['api_requests'], 6)
            self.assertEqual(s['controller_completion_attempts'], 0); self.assertFalse(s['declared_complete'])

    def test_failed_or_unknown_completion_never_retries_or_continues_schedule(self):
        for mode, unknown in [('failed_completion', 0), ('unknown_completion', 1)]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                Bridge.mode = mode
                s, _ = self.run_fixture(tmp)
                self.assertEqual(s['model_calls'], 6); self.assertEqual(s['api_requests'], 7)
                self.assertEqual(s['controller_completion_attempts'], 1)
                self.assertEqual(s['unknown_effect_requests'], unknown); self.assertFalse(can_continue_batch(s))
                self.assertFalse(s['declared_complete']); self.assertTrue(s['python_session']['container_removed'])

    def test_auditor_replays_then_visible_prefix_and_rejects_future_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary, trial = self.run_fixture(tmp)
            task, spans, events, usage, checks = [read(trial/(n+'.json')) for n in
                ('public_task', 'spans', 'events', 'usage', 'controller_checks')]
            errors = []
            audit_controller(task, spans, events, usage, checks, summary,
                lambda ok, label: errors.append(label) if not ok else None)
            self.assertEqual(errors, [])
            checks[0]['decision'] = checks[-1]['decision']
            audit_controller(task, spans, events, usage, checks, summary,
                lambda ok, label: errors.append(label) if not ok else None)
            self.assertIn('controller decision cannot be reproduced', errors)


if __name__ == '__main__': unittest.main()

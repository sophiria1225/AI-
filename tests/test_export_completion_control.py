import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_public_export_evidence as fixtures
from test_public_name_catalog import tool
from export_completion_control import check_prefix, prefix_digest
from export_completion_comparison import PLAN, validate, can_continue_batch
from run_export_completion import run_condition
from audit_export_completion import audit_controller, audit_native_history, compare_pair
from run_handoff_factors import ROOT, read
from run_context_comparison import write_json


class Bridge:
    mode = 'ok'
    sent = []
    def __init__(self, *_): self.task, self.actions = fixtures.fixture()
    def request(self, request):
        if request['op'] == 'init': return {'ok': True, 'result': self.task}
        action = request['call']; type(self).sent.append(copy.deepcopy(action))
        if action['app'] == 'supervisor':
            if self.mode == 'unknown_completion': raise TimeoutError('synthetic ambiguous effect')
            if self.mode == 'failed_completion': return {'ok': False, 'error': 'synthetic rejection'}
            return {'ok': True, 'result': {'observation': '{}', 'declared_complete': True}}
        if action['app'] == 'api_docs' or action['api'] == 'delete_file':
            return {'ok': True, 'result': {'observation': '{}'}}
        name = action['app']+'__'+action['api']
        value = next(v for n, a, v in self.actions if name == n and a == action['args'])
        return {'ok': True, 'result': {'observation': json.dumps(value)}}
    def close(self): pass


class Inference:
    late_mutation = False
    def __init__(self, config, output):
        self.output = output; self.started = time.monotonic(); self.calls = []
    @property
    def tokens(self): return 15*len(self.calls)
    def call(self, messages, tools):
        n = len(self.calls)+1
        self.calls.append({'id': f'call_{n:03d}', 'usage_known': True, 'status': 'ok',
                           'input_tokens': 10, 'output_tokens': 5})
        _, actions = fixtures.fixture()
        if n == 1:
            actions = [('api_docs__show_api_descriptions', {'app_name': app}, {}) for app in ('spotify', 'file_system')]
        else:
            actions = [actions[n-2]]
            if actions[0][0] == 'spotify__delete_account' and self.late_mutation:
                actions.append(('file_system__delete_file', {'access_token': 'synthetic-file',
                                'file_path': '~/backups/spotify.csv'}, {}))
        message = {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': f'c{n}_{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
            for i, (name, args, _) in enumerate(actions)]}
        path = self.output / f'call_{n:03d}'
        path.mkdir()
        write_json(path / 'request.json', {'messages': messages, 'tools': tools})
        write_json(path / 'response.json', {'status': 'ok', 'message': message})
        return message


class ExportCompletionTests(unittest.TestCase):
    def setUp(self):
        Bridge.mode = 'ok'; Bridge.sent = []; Inference.late_mutation = False
        self.plan = read(ROOT / PLAN); self.original = read(ROOT / self.plan['source_config'])

    def run_fixture(self, directory, arm='controlled', budget=80):
        plan = copy.deepcopy(self.plan); plan['api_budget_by_task']['6104387_1'] = budget
        task, actions = fixtures.fixture(); fields = {}
        for name, args, _ in actions: fields[name] = {k: {} for k in args}
        fields['api_docs__show_api_descriptions'] = {'app_name': {}}
        fields['file_system__delete_file'] = {'access_token': {}, 'file_path': {}}
        tools = [tool(name, f) for name, f in fields.items()]
        (Path(directory) / 'records/context_pilot').mkdir(parents=True)
        row = next(r for r in plan['run_order'] if r[1] == arm)
        with patch('run_export_completion.Bridge', Bridge), patch('run_export_completion.OrdinaryInference', Inference), \
             patch('run_export_completion.db_hashes', return_value={'dbs/fixture': 'same'}):
            summary = run_condition(Path(directory), plan, self.original,
                {'6104387_1': {'public_task': task, 'initial_database_hashes': {'dbs/fixture': 'same'}}},
                tools, *row)
        return summary, Path(directory) / 'records/context_pilot' / row[2], tools

    def test_fixed_plan_rejects_added_budget_retry_task_or_changed_notification(self):
        validate(self.plan, self.original)
        for k, v in [('max_calls', 81), ('api_budget_by_task', {'6104387_1': 81}),
                     ('max_controller_completion_attempts', 2), ('task_ids', ['new']),
                     ('notification', 'new_hint'), ('run_order', self.plan['run_order'][::-1])]:
            with self.subTest(k=k), self.assertRaises(ValueError): validate({**self.plan, k:v}, self.original)

    def test_write_without_deletion_unknown_usage_or_unrelated_requirement_cannot_complete(self):
        task, actions = fixtures.fixture(); spans, events, usage = fixtures.records(actions[:-1])
        self.assertEqual(check_prefix(task, spans, events, usage)['trace_support'], 'supported')
        s, e, u = fixtures.records(actions[:-2])
        self.assertEqual(check_prefix(task, s, e, u)['trace_support'], 'unknown')
        usage[-1]['usage_known'] = False
        self.assertEqual(check_prefix(task, spans, events, usage)['trace_support'], 'unknown')
        usage[-1]['usage_known'] = True; task['instruction'] += ' Also send mail.'
        self.assertEqual(check_prefix(task, spans, events, usage)['trace_support'], 'unknown')

    def test_digest_binds_current_prefix_and_checks_do_not_mutate_it(self):
        task, actions = fixtures.fixture(); spans, events, usage = fixtures.records(actions[:-1])
        before = copy.deepcopy((task, spans, events, usage)); digest = prefix_digest(*before)
        check_prefix(task, spans, events, usage); self.assertEqual((task, spans, events, usage), before)
        events[-1]['effects_unknown'] = True
        self.assertNotEqual(prefix_digest(task, spans, events, usage), digest)
        self.assertEqual(check_prefix(task, spans, events, usage)['trace_support'], 'unknown')

    def test_controller_uses_one_completion_after_agent_deletion_without_further_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, trial, _ = self.run_fixture(tmp)
            self.assertEqual(s['stop_reason'], 'controller_declared_complete'); self.assertTrue(can_continue_batch(s))
            self.assertEqual(s['model_calls'], 10); self.assertEqual(s['api_requests'], 12)
            self.assertEqual(s['controller_completion_attempts'], 1)
            events, spans = read(trial/'events.json'), read(trial/'spans.json')
            self.assertEqual(events[-1]['call'], 'controller_001'); self.assertEqual(events[-1]['stage'], 'controller_api')
            self.assertEqual(spans[events[-1]['span_id']]['assistant'], '')
            self.assertEqual([r['api'] for r in Bridge.sent[-2:]], ['delete_account', 'complete_task'])
            self.assertEqual(Bridge.sent[-1]['args'], {'status': 'success'})

    def test_ordinary_baseline_has_no_monitor_or_controller_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, trial, _ = self.run_fixture(tmp, 'native')
            self.assertEqual(s['stop_reason'], 'agent_declared_complete'); self.assertEqual(s['model_calls'], 11)
            self.assertEqual(s['controller_checks'], 0); self.assertEqual(s['controller_wall_seconds'], 0)
            self.assertEqual(read(trial/'controller_checks.json'), [])
            self.assertFalse(any(e['stage'] == 'controller_api' for e in read(trial/'events.json')))
            values = [read(trial/(n+'.json')) for n in ('public_task','spans','events','usage','controller_checks')]
            errors = []; audit_controller(*values, s, lambda ok, label: errors.append(label) if not ok else None)
            self.assertEqual(errors, [])

    def test_pair_gate_retains_unknown_failed_and_different_final_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = []; folders = []
            for i, arm in enumerate(('native','controlled')):
                folder = Path(tmp)/'records/context_pilot'/arm; (folder/'call_001').mkdir(parents=True)
                folders.append(folder)
                for name, value in [('events',[]),('spans',{}),('evaluation',{'frozen_database_hashes':{str(n):'same' for n in range(13)}})]:
                    write_json(folder/(name+'.json'),value)
                write_json(folder/'call_001/request.json',{'messages':[]})
                write_json(folder/'call_001/response.json',{'message':{'tool_calls':[{'id':f'different_{i}'}]}})
                rows.append({'run_id':arm,'status':'evaluated','official_success':True,'unknown_usage_calls':0,
                             'known_total_tokens':100-i*20,'calls':[{'call_id':'call_001'}]})
            result=compare_pair(Path(tmp),rows)
            self.assertTrue(result['local_gate_met']); self.assertFalse(result['same_entire_executed_model_prefix'])
            self.assertEqual(result['response_identifier_differences'],1)
            self.assertEqual(result['response_other_differences'],0)
            for field,value in [('unknown_usage_calls',1),('official_success',False),('known_total_tokens',101),('status','not_run')]:
                changed=copy.deepcopy(rows);changed[1][field]=value
                with self.subTest(field=field):self.assertFalse(compare_pair(Path(tmp),changed)['local_gate_met'])
            state=read(folders[1]/'evaluation.json');state['frozen_database_hashes']['0']='different'
            write_json(folders[1]/'evaluation.json',state)
            self.assertFalse(compare_pair(Path(tmp),rows)['local_gate_met'])

    def test_later_mutation_in_same_native_message_prevents_controller_completion(self):
        Inference.late_mutation = True
        with tempfile.TemporaryDirectory() as tmp:
            s, _, _ = self.run_fixture(tmp)
            self.assertEqual(s['stop_reason'], 'agent_declared_complete'); self.assertEqual(s['model_calls'], 11)
            self.assertEqual(s['controller_completion_attempts'], 0)

    def test_completion_consumes_same_api_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, _, _ = self.run_fixture(tmp, budget=11)
            self.assertEqual(s['stop_reason'], 'api_request_limit'); self.assertEqual(s['api_requests'], 11)
            self.assertEqual(s['controller_completion_attempts'], 0); self.assertFalse(s['declared_complete'])

    def test_failed_or_unknown_completion_never_retries(self):
        for mode, unknown in [('failed_completion', 0), ('unknown_completion', 1)]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                Bridge.mode = mode; s, _, _ = self.run_fixture(tmp)
                self.assertEqual(s['model_calls'], 10); self.assertEqual(s['controller_completion_attempts'], 1)
                self.assertEqual(s['unknown_effect_requests'], unknown); self.assertFalse(can_continue_batch(s))

    def test_audit_reconstructs_current_history_and_rejects_future_decision_or_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary, trial, tools = self.run_fixture(tmp)
            task, spans, events, usage, checks = [read(trial/(n+'.json')) for n in
                ('public_task', 'spans', 'events', 'usage', 'controller_checks')]
            errors = []; check = lambda ok, label: errors.append(label) if not ok else None
            audit_controller(task, spans, events, usage, checks, summary, check)
            audit_native_history(trial, self.original, task, tools, usage, events, spans, check)
            self.assertEqual(errors, [])
            checks[0]['decision'] = checks[-1]['decision']
            audit_controller(task, spans, events, usage, checks, summary, check)
            self.assertIn('controller decision cannot be reproduced', errors)
            r = read(trial/'call_001/request.json'); r['tools'] = read(trial/'call_002/request.json')['tools']
            write_json(trial/'call_001/request.json', r)
            audit_native_history(trial, self.original, task, tools, usage, events, spans, check)
            self.assertIn('call_001: then-visible public schemas', errors)


if __name__ == '__main__': unittest.main()

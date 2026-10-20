import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_native_generated as runner
import audit_native_generated as auditor
from audit_native_boundaries import audit as audit_boundaries
from context_preservation import function
from native_conversation import NativeConversation


class GeneratedRunnerControls(unittest.TestCase):
    def execute(self, root, fail_second_count=False):
        storage, appworld = root / 'storage', root / 'world'
        (storage / '.runtime').mkdir(parents=True)
        (storage / '.runtime/model_server.json').write_text('{}')
        spec = appworld / 'data/tasks/dev/specs.json'; spec.parent.mkdir(parents=True); spec.write_text('{}')
        sent, requests = [], []
        task = {'instruction': 'public fixture task'}
        names = ['api_docs__show_app_descriptions', 'supervisor__complete_task']
        tools = [function(n, 'fixture', {}, []) for n in names]
        dbs = appworld / 'experiments/outputs/P13_FIXTURE/tasks/dev/dbs'

        class FakeBridge:
            def __init__(self, *args):
                pass
            def request(self, request):
                if request['op'] == 'init':
                    dbs.mkdir(parents=True); (dbs / 'fixture.jsonl').write_text('initial')
                    return {'ok': True, 'result': task}
                sent.append(request['call'])
                complete = request['call']['api'] == 'complete_task'
                (dbs / 'fixture.jsonl').write_text(str(len(sent)))
                return {'ok': True, 'result': {'observation': 'fixture observation', 'declared_complete': complete}}
            def close(self):
                pass

        class FakeInference:
            def __init__(self, config, out):
                self.started, self.calls, self.tokens = time.monotonic(), [], 0
                self.output = out
            def call(self, role, messages, supplied):
                index = len(self.calls)
                if role == "agent":
                    requests.append(messages)
                self.calls.append({'id': f'call_{index + 1:03d}', 'status': 'ok', 'role': role,
                                   'input_tokens': 10, 'output_tokens': 1, 'predicted_input_tokens': 10})
                self.tokens += 11
                if role == 'focus':
                    ids = [s['id'] for s in json.loads(messages[-1]['content'])['memory']['visible_spans']]
                    message = {'tool_calls': [{'function': {'name': 'submit_selection',
                        'arguments': json.dumps({'steps': [{'plan': 'continue', 'depends_on': ids}],
                                                 'rescued': [], 'rescue_reason': ''})}}]}
                else:
                    agent_index = len(requests) - 1
                    message = {'role': 'assistant', 'content': '', 'tool_calls': [{
                        'id': f'c{agent_index}', 'type': 'function',
                        'function': {'name': names[agent_index], 'arguments': '{}'}}]}
                path = self.output / self.calls[-1]['id']; path.mkdir()
                (path / 'request.json').write_text(json.dumps({'messages': messages, 'tools': supplied}))
                (path / 'response.json').write_text(json.dumps({'status': 'ok', 'input_tokens': 10,
                                                               'output_tokens': 1, 'message': message}))
                (self.output / 'usage.json').write_text(json.dumps(self.calls))
                return message

        count_requests = []
        def count(*args):
            count_requests.append(args)
            if fail_second_count and len(count_requests) == 2:
                raise TimeoutError('fixture tokenizer failure')
            return {'tokens': [0] * (100 if len(count_requests) == 1 else 5000)}
        config = {'phase': 'P13', 'arms': ['native_focus'], 'task_ids': ['dev'],
                  'model_selection': 'fixture', 'model': {'base_url': 'http://unused', 'num_ctx': 65536},
                  'seed': 42, 'max_total_tokens': 1000, 'max_calls': 80, 'max_api_requests': 80,
                  'max_wall_seconds': 1800, 'max_checkpoint_object_bytes': 10000000,
                  'max_checkpoint_new_bytes_per_boundary': 10000000, 'observation_page_characters': 24000,
                  'history_budget_tokens': 4096, 'focus_rollouts': 3, 'focus_threshold': 0.3}
        with patch.object(runner, 'Bridge', FakeBridge), patch.object(runner, 'Inference', FakeInference), \
             patch.object(runner, 'check_live_model'), patch.object(runner, 'load_public_tools', return_value=(tools, {}, None)), \
             patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(b'{}')), \
             patch.object(runner, 'post', side_effect=count), contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(config, 'dev', 'P13_FIXTURE', storage, appworld, Path('/unused'))
        return result, sent, requests, task, tools

    def test_generation_costs_are_counted_and_submissions_never_reach_the_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, sent, requests, task, tools = self.execute(Path(tmp))
            self.assertEqual(result['stop_reason'], 'agent_declared_complete')
            self.assertEqual([c['api'] for c in sent], ['show_app_descriptions', 'complete_task'])
            self.assertEqual(result['model_calls'], 3)
            self.assertEqual(result['usage_by_role']['agent']['calls'], 2)
            self.assertEqual(result['usage_by_role']['focus']['calls'], 1)
            self.assertEqual(result['known_total_tokens'], 33)
            self.assertEqual(result['all_retained_early_exits'], 1)
            self.assertEqual(result['boundary_records'], 3)
            self.assertEqual(result['memory_token_count_requests'], 3)
            conversation = NativeConversation(runner.NATIVE_PROMPT, task)
            self.assertEqual(requests[0], conversation.for_model()[0])
            fn = {'name': 'api_docs__show_app_descriptions', 'arguments': '{}'}
            conversation.append({'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'c0', 'type': 'function', 'function': fn}]},
                [{'id': 's1', 'assistant': '', 'action': fn,
                  'observation': {'observation': 'fixture observation', 'declared_complete': False}}])
            self.assertEqual(requests[1], conversation.for_model()[0])
            with patch.object(auditor, 'load_public_tools', return_value=(tools, {}, None)):
                audited = auditor.audit(Path(tmp) / 'storage/records/context_pilot/P13_FIXTURE', Path('/unused'))
            self.assertEqual(audited['audit_errors'], [])
            self.assertEqual(audited['dispatch_audit_errors'], [])
            self.assertEqual(audited['memory_audit_errors'], [])
            boundaries = audit_boundaries(Path(tmp) / 'storage/records/context_pilot/P13_FIXTURE',
                                          Path(tmp) / 'world')
            self.assertEqual(boundaries['audit_errors'], [])
            self.assertEqual([r['model_calls'] for r in boundaries['boundary_records']], [0, 1, 3])


if __name__ == '__main__':
    unittest.main()

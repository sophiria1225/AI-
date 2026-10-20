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
import run_native_recent as runner
from context_preservation import function
from native_conversation import NativeConversation


class RecentRunnerControls(unittest.TestCase):
    def execute(self, root, fail_second_count=False):
        storage, appworld = root / 'storage', root / 'world'
        (storage / '.runtime').mkdir(parents=True)
        (storage / '.runtime/model_server.json').write_text('{}')
        spec = appworld / 'data/tasks/dev/specs.json'; spec.parent.mkdir(parents=True); spec.write_text('{}')
        sent, requests = [], []
        task = {'instruction': 'public fixture task'}
        names = ['api_docs__show_app_descriptions', 'supervisor__complete_task']
        tools = [function(n, 'fixture', {}, []) for n in names]
        dbs = appworld / 'experiments/outputs/P12_FIXTURE/tasks/dev/dbs'

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
            def call(self, role, messages, supplied):
                index = len(self.calls)
                requests.append(messages)
                self.calls.append({'id': f'call_{index + 1:03d}', 'status': 'ok',
                                   'input_tokens': 10, 'output_tokens': 1})
                self.tokens += 11
                return {'role': 'assistant', 'content': '', 'tool_calls': [{
                    'id': f'c{index}', 'type': 'function',
                    'function': {'name': names[index], 'arguments': '{}'}}]}

        count_requests = []
        def count(*args):
            count_requests.append(args)
            if fail_second_count and len(count_requests) == 2:
                raise TimeoutError('fixture tokenizer failure')
            return {'tokens': [0] * 100}
        config = {'phase': 'P12', 'arms': ['native_recent'], 'task_ids': ['dev'],
                  'model_selection': 'fixture', 'model': {'base_url': 'http://unused', 'num_ctx': 65536},
                  'seed': 42, 'max_total_tokens': 1000, 'max_calls': 80, 'max_api_requests': 80,
                  'max_wall_seconds': 1800, 'max_checkpoint_object_bytes': 10000000,
                  'max_checkpoint_new_bytes_per_boundary': 10000000, 'observation_page_characters': 24000,
                  'history_budget_tokens': 4096}
        with patch.object(runner, 'Bridge', FakeBridge), patch.object(runner, 'Inference', FakeInference), \
             patch.object(runner, 'check_live_model'), patch.object(runner, 'load_public_tools', return_value=(tools, {}, None)), \
             patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(b'{}')), \
             patch.object(runner, 'post', side_effect=count), contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(config, 'dev', 'P12_FIXTURE', storage, appworld, Path('/unused'))
        return result, sent, requests, task

    def test_under_budget_execution_and_original_history_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, sent, requests, task = self.execute(Path(tmp))
            self.assertEqual(result['stop_reason'], 'agent_declared_complete')
            self.assertEqual([c['api'] for c in sent], ['show_app_descriptions', 'complete_task'])
            self.assertEqual(result['model_calls'], 2)
            self.assertEqual(result['boundary_records'], 3)
            self.assertEqual(result['memory_token_count_requests'], 2)
            conversation = NativeConversation(runner.NATIVE_PROMPT, task)
            self.assertEqual(requests[0], conversation.for_model()[0])
            fn = {'name': 'api_docs__show_app_descriptions', 'arguments': '{}'}
            conversation.append({'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'c0', 'type': 'function', 'function': fn}]},
                [{'id': 's1', 'assistant': '', 'action': fn,
                  'observation': {'observation': 'fixture observation', 'declared_complete': False}}])
            self.assertEqual(requests[1], conversation.for_model()[0])

    def test_failed_count_stops_without_reexecuting_prior_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, sent, requests, _ = self.execute(Path(tmp), fail_second_count=True)
            self.assertEqual(result['stop_reason'], 'runtime_error')
            self.assertEqual(len(sent), 1)
            self.assertEqual(len(requests), 1)
            self.assertEqual(result['known_total_tokens'], 11)
            self.assertEqual(result['memory_token_count_requests'], 2)
            self.assertEqual(result['memory_token_count_failures'], 1)
            self.assertEqual(result['memory_selection_attempts'], 2)
            self.assertEqual(result['memory_selections_completed'], 1)


if __name__ == '__main__':
    unittest.main()

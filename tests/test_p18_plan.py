import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from context_preservation import function
from run_native_batch import PHASES, public_body, validate_schedule
import run_native_appworld as runner


class P18Controls(unittest.TestCase):
    def test_same_baseline_budgets_and_fixed_new_scenarios(self):
        previous = json.loads((ROOT/'configs/P11_additional_baseline_v01.json').read_text())
        actual = json.loads((ROOT/'configs/P18_additional_baseline_v01.json').read_text())
        validate_schedule(actual)
        for key in ('model', 'model_selection', 'seed', 'agent_temperature', 'max_calls',
                    'max_api_requests', 'max_wall_seconds', 'max_total_tokens', 'max_output_tokens',
                    'observation_page_characters', 'history_representation', 'discovery_policy'):
            self.assertEqual(previous[key], actual[key], key)
        self.assertTrue(set(previous['task_ids']).isdisjoint(actual['task_ids']))
        self.assertEqual(actual['wait_for_contract_probe'], 'P17_01')
        self.assertEqual(PHASES['P18']['issue'], 86)
        changed = copy.deepcopy(actual)
        changed['task_ids'][0] = changed['run_order'][0][0] = previous['task_ids'][0]
        with self.assertRaises(ValueError):
            validate_schedule(changed)
        body = public_body([{'task_number': 1, 'status': 'running', 'instruction': 'PRIVATE'}],
                           {'status': 'running', 'phase': 'P18'})
        self.assertNotIn('PRIVATE', body)

    def run_fixture(self, root, phase):
        storage, world = root/'storage', root/'world'
        (storage/'.runtime').mkdir(parents=True)
        (storage/'.runtime/model_server.json').write_text('{}')
        spec = world/'data/tasks/dev/specs.json'
        spec.parent.mkdir(parents=True); spec.write_text('{}')
        task = {'instruction': 'public fixture'}
        dbs = world/'experiments/outputs'/f'{phase}_FIXTURE/tasks/dev/dbs'
        sent, requests = [], []
        names = ['api_docs__show_app_descriptions', 'supervisor__complete_task']
        tools = [function(n, 'fixture', {}, []) for n in names]

        class Bridge:
            def __init__(self, *args): pass
            def request(self, request):
                if request['op'] == 'init':
                    dbs.mkdir(parents=True); (dbs/'fixture.jsonl').write_text('initial')
                    return {'ok': True, 'result': task}
                sent.append(request['call'])
                (dbs/'fixture.jsonl').write_text(str(len(sent)))
                return {'ok': True, 'result': {'observation': 'observed',
                        'declared_complete': request['call']['api'] == 'complete_task'}}
            def close(self): pass

        class Inference:
            def __init__(self, *args):
                self.started, self.calls, self.tokens = time.monotonic(), [], 0
            def call(self, role, messages, tools):
                index = len(self.calls)
                requests.append((role, messages, tools))
                self.calls.append({'id': f'call_{index+1:03d}', 'role': role, 'status': 'ok',
                                   'input_tokens': 10, 'output_tokens': 1})
                self.tokens += 11
                return {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'id': f'c{index}', 'type': 'function',
                     'function': {'name': names[index], 'arguments': '{}'}}]}

        config = json.loads((ROOT/'configs/P18_additional_baseline_v01.json').read_text())
        config.update(phase=phase, task_ids=['dev'])
        with patch.object(runner, 'Bridge', Bridge), patch.object(runner, 'Inference', Inference), \
             patch.object(runner, 'check_live_model'), patch.object(runner, 'load_public_tools', return_value=(tools, {}, None)), \
             patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(b'{}')), \
             contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(config, 'dev', phase+'_FIXTURE', storage, world, Path('/unused'))
        return result, sent, requests

    def test_execution_and_passive_snapshot_behavior_match_p11(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = self.run_fixture(root/'old', 'P11')
            new = self.run_fixture(root/'new', 'P18')
            self.assertEqual(old[1:], new[1:])
            for key in ('known_total_tokens', 'model_calls', 'api_requests', 'boundary_records', 'stop_reason'):
                self.assertEqual(old[0][key], new[0][key], key)
            self.assertEqual(new[0]['boundary_records'], 3)
            self.assertEqual(new[0]['known_total_tokens'], 22)


if __name__ == '__main__':
    unittest.main()

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_ledger_contract_probe import ROOT, audit, outcome, sha
from ledger_contract import inputs as make_inputs
from local_llama import parse_response, payload_for
from run_ledger_contract_probe import schedule


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


class ContractAuditTests(unittest.TestCase):
    def fixture(self, root):
        run, inputs = root/'run', root/'inputs'
        plan = json.loads((ROOT/'configs/P17_ledger_contract_v01.json').read_text())
        config = {'model': {'model': 'synthetic', 'temperature': 1, 'seed': 47, 'num_predict': 4096},
                  'observation_page_characters': 24000}
        manifest, cases = {'cases': []}, {}
        for case_id in plan['case_ids']:
            case = {'case_id': case_id, 'condition': 'recorded', 'task': {'instruction': 'PRIVATE work'},
                    'tools': [], 'spans': {'s1': {'id': 's1', 'action': {},
                                               'observation': {'message': 'PRIVATE observed'}}}}
            path = inputs/(case_id+'.json')
            put(path, case)
            cases[case_id] = case
            manifest['cases'].append({'case_id': case_id, 'condition': 'recorded', 'case_sha256': sha(path)})
        for path in (inputs/'manifest.json', run/'input_manifest.json'):
            put(path, manifest)
        put(run/'plan.json', plan)
        names = ['configs/P17_ledger_contract_v01.json', 'scripts/ledger_contract.py']
        for name in names:
            target = run/'source'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes())
        put(run/'freeze_record.json', {'plan_sha256': sha(ROOT/names[0]),
            'input_manifest_sha256': sha(inputs/'manifest.json'),
            'source_hashes': {name: sha(ROOT/name) for name in names}})
        put(run/'provenance.json', {'config': config})
        order = schedule(plan)
        put(run/'schedule.json', order)
        results, usages, counts = [], [], []
        for index, item in enumerate(order, 1):
            call_id = f'call_{index:03d}'
            directory = run/call_id
            messages, tool = make_inputs(cases[item['case_id']], item['variant'], 24000)
            cfg = dict(config['model'], seed=item['seed'])
            put(directory/'request.json', payload_for(cfg, messages, [tool]))
            value = {'items': [{'key': 'q', 'requirement': 'PRIVATE requested operation',
                               'status': 'pending', 'source_ids': ['task']}],
                     'constraints': [], 'unresolved': []}
            message = {'role': 'assistant', 'content': '', 'tool_calls': [
                {'function': {'name': 'submit_ledger', 'arguments': json.dumps(value)}}]}
            raw = {'usage': {'prompt_tokens': 100, 'completion_tokens': 5, 'total_tokens': 105},
                   'choices': [{'finish_reason': 'tool_calls', 'message': message}]}
            response = parse_response(raw)
            put(directory/'raw_response.json', raw)
            put(directory/'response.json', response)
            result, ledger = outcome(message, cases[item['case_id']], item['variant'])
            if ledger is not None:
                put(directory/'ledger_private.json', ledger)
            results.append({**item, **result, 'call_id': call_id, 'known_tokens': 105,
                'request_sha256': sha(directory/'request.json'), 'response_sha256': sha(directory/'response.json')})
            usages.append({'id': call_id, 'role': 'ledger', 'status': 'ok', 'input_tokens': 100,
                           'output_tokens': 5, 'predicted_input_tokens': 100, 'wall_seconds': 1})
            counts.append({**item, 'input_tokens': 100})
        for name, value in [('results.json', results), ('usage.json', usages), ('input_counts.json', counts)]:
            put(run/name, value)
        put(run/'status.json', {'status': 'complete', 'model_calls': 16, 'completed_outputs': 16,
                               'known_total_tokens': 1680, 'unknown_usage_calls': 0, 'wall_seconds': 16})
        return run, inputs

    def test_every_output_and_cost_is_counted_but_no_private_content_exported(self):
        with tempfile.TemporaryDirectory() as d:
            run, inputs = self.fixture(Path(d))
            report = audit(run, inputs)
            self.assertEqual(report['audit_errors'], [])
            self.assertEqual([g['schema_valid'] for g in report['groups']], [0, 8])
            self.assertEqual(report['known_total_tokens'], 1680)
            self.assertNotIn('PRIVATE', json.dumps(report))

    def test_wrong_seed_and_usage_detected(self):
        with tempfile.TemporaryDirectory() as d:
            run, inputs = self.fixture(Path(d))
            path = run/'call_001/request.json'
            value = json.loads(path.read_text()); value['seed'] = 49; put(path, value)
            path = run/'usage.json'
            value = json.loads(path.read_text()); value[0]['output_tokens'] = 6; put(path, value)
            errors = audit(run, inputs)['audit_errors']
            self.assertIn('call_001 request', errors)
            self.assertIn('call_001 usage output_tokens', errors)

    def test_live_batch_not_exposed_as_terminal_audit(self):
        with tempfile.TemporaryDirectory() as d:
            run, inputs = self.fixture(Path(d))
            path = run/'status.json'
            value = json.loads(path.read_text()); value['status'] = 'running'; put(path, value)
            with self.assertRaisesRegex(ValueError, 'terminal P17'):
                audit(run, inputs)


if __name__ == '__main__':
    unittest.main()

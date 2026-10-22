from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_context_comparison import write_json
from run_contract_comparison import ACTIVATION, PREFLIGHT, run
from run_handoff_factors import sha


class ContractBatchTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'reports').mkdir()
        (root / 'records/context_pilot').mkdir(parents=True)
        items = [{'boundary_manifest_sha256': str(n), 'task_id': str(n)} for n in range(4)]
        write_json(root / PREFLIGHT, {'model_identity': {'fixture': True}})
        write_json(root / 'reports/P47_runtime_checks.json', {'fixture': True})
        write_json(root / ACTIVATION, {'source_hashes': {}, 'preflight_sha256': sha(root / PREFLIGHT),
                   'runtime_check_sha256': sha(root / 'reports/P47_runtime_checks.json'),
                   'source_boundaries': [str(n) for n in range(4)], 'research_resume': {'fixture': True}})
        plan = {'batch_id': 'P47_batch_v01', 'max_setup_seconds': 600, 'max_wall_seconds': 480}
        return plan, items

    def exercise(self, root, *, failure=None):
        plan, items = self.fixture(root)
        seen = []
        def branch(storage, repo, p, original, tools, schemas, item, arm, rid):
            seen.append(rid)
            folder = storage / 'records/context_pilot' / rid
            folder.mkdir()
            write_json(folder / 'evaluation.json', {'official_success': False})
            result = {'run_id': rid, 'task_id': item['task_id'], 'arm': arm,
                'stop_reason': 'api_request_limit', 'model_calls': 2, 'known_total_tokens': 123,
                'unknown_usage_calls': 0, 'api_requests': 2, 'prefix_api_requests': 3,
                'wall_seconds': 1, 'unknown_effect_requests': 0,
                'setup': {'status': 'matched_observable_prefix'}}
            if failure == 'usage': result['unknown_usage_calls'] = 1
            if failure == 'effects': result['unknown_effect_requests'] = 1
            if failure == 'runtime': result['stop_reason'] = 'runtime_error'
            if failure == 'restore': result['setup']['status'] = 'failed'
            return result
        with ExitStack() as stack:
            stack.enter_context(patch('run_contract_comparison.sources', return_value=(plan, {}, [], {}, items)))
            stack.enter_context(patch('run_contract_comparison.frozen_hashes', return_value={}))
            stack.enter_context(patch('run_contract_comparison.check_resume', return_value={'fixture': True}))
            stack.enter_context(patch('run_contract_comparison.live_identity', return_value=({'fixture': True}, 1)))
            stack.enter_context(patch('run_contract_comparison.subprocess.check_output', return_value='fixture'))
            evaluator = stack.enter_context(patch('run_contract_comparison.subprocess.run',
                return_value=SimpleNamespace(returncode=int(failure == 'evaluation'), stdout='', stderr='')))
            stack.enter_context(patch('run_contract_comparison.run_branch', side_effect=branch))
            stack.enter_context(patch('run_contract_comparison.signal.alarm'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            code = run(root, root)
            before = len(seen)
            with self.assertRaises(FileExistsError):
                run(root, root)
            self.assertEqual(len(seen), before)
        state = json.loads((root / 'records/context_pilot/P47_batch_v01/status.json').read_text())
        return code, state, seen, evaluator.call_count

    def test_ordinary_budget_failure_is_evaluated_and_all_fixed_cells_run_once(self):
        with tempfile.TemporaryDirectory() as directory:
            code, state, seen, evaluations = self.exercise(Path(directory))
        self.assertEqual(code, 0)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(seen, state['planned'])
        self.assertEqual(len(set(seen)), 12)
        self.assertEqual(evaluations, 12)
        self.assertEqual(len(state['completed']), 12)
        self.assertEqual(state['not_run'], [])
        self.assertEqual(state['unevaluated'], [])
        self.assertTrue(all(row['success'] is False for row in state['rows']))

    def test_unknown_or_inconsistent_cell_stops_without_replacement_or_evaluation(self):
        for failure in ('usage', 'effects', 'runtime', 'restore', 'evaluation'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                code, state, seen, evaluations = self.exercise(Path(directory), failure=failure)
                self.assertEqual(code, 1)
                self.assertEqual(state['status'], 'stopped')
                self.assertEqual(len(seen), 1)
                self.assertEqual(len(state['not_run']), 11)
                self.assertEqual(state['completed'], [])
                self.assertEqual(state['unevaluated'], seen)
                self.assertEqual(evaluations, int(failure == 'evaluation'))


if __name__ == '__main__':
    unittest.main()

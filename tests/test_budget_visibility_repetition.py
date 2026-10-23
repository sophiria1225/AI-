import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget_visibility_comparison import config_for as anchor_config
from budget_visibility_repetition import cell_id, config_for, run_order, validate_plan, summarize_repetitions
import run_budget_visibility_repeat_cell as worker
import test_budget_visibility_worker as external_fixture
from test_budget_visibility_audit import audit_fixture
from test_budget_visibility_audit import rows as anchor_fixture

ROOT = Path(__file__).resolve().parents[1]


def plan():
    value = json.loads((ROOT / 'configs/P80_budget_visibility_v01.json').read_text())
    value.update(experiment='P81', batch_id='P81_batch_v01', repetitions=[2, 3],
        anchor_experiment='P80', max_cells=16, max_model_calls=1280,
        max_reserved_tokens=7200000, server_max_lifetime_seconds=43200,
        fresh_seed_search=False, new_task_requirements_read=0,
        primary_question='same_seed_trajectory_and_cost_stability',
        prior_cohort='reports/P80_comparison.json')
    # Synthetic hashes only for plan validation; execution verifies real bytes.
    value['source_sha256'].update({name: '0' * 64 for name in
        ('reports/P80_comparison.json', 'reports/P80_server_session.json',
         'configs/P80_budget_visibility_v01.json')})
    return value


def fixture(**kwargs):
    # Reuse trusted synthetic I/O around the new real worker, not a second runner.
    with patch.dict(sys.modules, {'run_budget_visibility_cell': worker}), \
         patch.object(external_fixture, 'run_cell', worker.run_cell):
        return external_fixture.fixture(**kwargs)


class RepetitionTests(unittest.TestCase):
    def test_all_sixteen_cells_have_new_ids_and_alternate_order(self):
        order = run_order()
        self.assertEqual(len(order), 16)
        self.assertEqual(len({cell_id(*entry) for entry in order}), 16)
        for rep in (2, 3):
            rows = [row for row in order if row[0] == rep]
            self.assertEqual({(n, p) for _, n, p in rows},
                             {(n, p) for n in range(1, 5) for p in ('measured', 'not_exposed')})
        self.assertEqual(order[:2], [(2, 1, 'not_exposed'), (2, 1, 'measured')])
        self.assertEqual(order[8:10], [(3, 1, 'measured'), (3, 1, 'not_exposed')])
        for rep, n, p in ((1, 1, 'measured'), (4, 1, 'measured'), (2, 5, 'measured'),
                          (True, 1, 'measured'), (2, 1, 'rounded')):
            with self.assertRaises(ValueError): cell_id(rep, n, p)

    def test_model_world_and_budgets_match_anchor_exactly(self):
        p = plan(); validate_plan(p)
        original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
        anchor = json.loads((ROOT / 'configs/P80_budget_visibility_v01.json').read_text())
        for task in p['known_tasks']:
            for policy in ('measured', 'not_exposed'):
                self.assertEqual(config_for(original, p, task['task_id'], policy),
                                 anchor_config(original, anchor, task['task_id'], policy))
        per_cell = sum(p[k] for k in ('max_setup_seconds', 'max_wall_seconds',
            'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
        self.assertLess(per_cell * p['max_cells'] + 1200, p['server_max_lifetime_seconds'])

    def test_seed_task_retry_and_budget_search_are_rejected(self):
        for key, value in [('model_seed', 58), ('world_seed', 43), ('max_cells', 8),
            ('max_total_tokens', 450001), ('automatic_retries', 1),
            ('repetitions', [2, 4]), ('fresh_seed_search', True), ('new_task_requirements_read', 1)]:
            data = plan(); data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_plan(data)
        data = plan(); data['known_tasks'][0]['task_id'] = 'new-unread-task'
        with self.assertRaises(ValueError): validate_plan(data)
        data = plan(); del data['source_sha256']['reports/P80_comparison.json']
        with self.assertRaises(ValueError): validate_plan(data)

    def test_real_repeat_worker_preserves_both_policies_and_full_costs(self):
        for policy in ('measured', 'not_exposed'):
            result = fixture(policy=policy)
            self.assertEqual(result['result']['phase'], 'P81')
            self.assertEqual(result['result']['stop_reason'], 'agent_declared_complete')
            self.assertTrue(result['result']['cleanup_confirmed'])
            self.assertEqual(result['result']['known_total_tokens'], 100)
            remaining = result['saved']['budget_observations'][0]['visible_state']['remaining']
            self.assertEqual('wall_seconds_at_snapshot' in remaining, policy == 'measured')

    def test_unknown_dispatch_and_late_response_remain_auditable(self):
        for kwargs, known, unknown, api in [
                ({'actions': ('echo', 'transport_error')}, 50, 1, 1),
                ({'response_delay': 61}, 50, 0, 0)]:
            with tempfile.TemporaryDirectory() as directory:
                result = fixture(folder=directory, **kwargs)
                row = audit_fixture(directory, result)
                self.assertEqual((row['known_total_tokens'], row['unknown_usage_calls'], row['api_requests']),
                                 (known, unknown, api))

    def test_p81_stop_marker_prevents_any_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = Path(directory) / '.runtime/P81.stop'
            stop.parent.mkdir(); stop.touch()
            result = fixture(folder=directory)
            self.assertEqual(result['result']['stop_reason'], 'user_stop')
            self.assertEqual(result['captured'], [])
            self.assertEqual(result['raw'], [])

    def test_repetition_summary_preserves_all_rows_and_missing_cost(self):
        anchor = [{**r, 'run_id': f'anchor{i}'} for i, r in enumerate(anchor_fixture())]
        repeated = [{**r, 'repetition': rep, 'run_id': f'rep{rep}_{i}'}
                    for rep in (2, 3) for i, r in enumerate(anchor)]
        result = summarize_repetitions(anchor, repeated, [])
        self.assertTrue(result['all_three_repetition_gates_met'])
        self.assertTrue(all(g['exact_costs_stable'] for g in result['groups']))
        self.assertEqual(result['independent_tasks'], 4)
        bad = copy.deepcopy(repeated); bad[0]['unknown_usage_calls'] = 1
        result = summarize_repetitions(anchor, bad, [])
        self.assertFalse(result['all_three_repetition_gates_met'])
        self.assertIsNone(result['groups'][0]['range_tokens'])
        self.assertEqual(result['groups'][0]['unknown_usage_sequence'], [0, 1, 0])
        with self.assertRaises(ValueError): summarize_repetitions(anchor, repeated[:-1], [])
        with self.assertRaises(ValueError): summarize_repetitions(anchor, repeated[:-1] + [repeated[0]], [])


if __name__ == '__main__':
    unittest.main()

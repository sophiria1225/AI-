"""Exercise frozen-condition and duplicate-attempt rejection without model calls."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_planned_p3 import prepare_trial, reserve_attempt


class PlannedTrialControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'configs').mkdir()
        (self.root / 'scripts').mkdir()
        config = {'instance_id': 'task', 'model': 'fixture', 'cache_type_k': 'q8_0',
                  'cache_type_v': 'q8_0', 'max_calls': 2, 'max_total_tokens': 100,
                  'max_wall_seconds': 60}
        self.config = self.root / 'configs/task.json'
        self.config.write_text(json.dumps(config))
        self.source = self.root / 'scripts/runner.py'
        self.source.write_text('# fixture\n')
        self.plan = self.root / 'configs/plan.json'
        plan = {'trial_count': 2, 'max_total_model_calls': 4,
                'max_total_input_output_tokens': 200, 'per_trial_max_wall_seconds': 60,
                'model': 'fixture', 'cache_type_k': 'q8_0', 'cache_type_v': 'q8_0',
                'trials': [{'trial_id': 'P3-01', 'task': 'task', 'strategy': 'single',
                            'config': 'configs/task.json'},
                           {'trial_id': 'P3-02', 'task': 'task', 'strategy': 'fixed_pair',
                            'config': 'configs/task.json'}],
                'config_sha256': {'configs/task.json': hashlib.sha256(self.config.read_bytes()).hexdigest()},
                'source_sha256': {'runner.py': hashlib.sha256(self.source.read_bytes()).hexdigest()}}
        self.plan.write_text(json.dumps(plan))

    def test_duplicate_attempt_is_rejected_even_before_a_result_exists(self):
        *_, directory = prepare_trial(self.plan, 'P3-01', self.root)
        reserve_attempt(directory)
        with self.assertRaises(FileExistsError):
            reserve_attempt(directory)

    def test_changed_budget_config_is_rejected_before_execution(self):
        data = json.loads(self.config.read_text())
        data['max_total_tokens'] += 1
        self.config.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'config changed'):
            prepare_trial(self.plan, 'P3-01', self.root)

    def test_changed_source_is_rejected(self):
        self.source.write_text('# changed\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            prepare_trial(self.plan, 'P3-01', self.root)

    def test_unresolved_but_valid_previous_evaluation_allows_next_trial(self):
        *_, directory = prepare_trial(self.plan, 'P3-01', self.root)
        reserve_attempt(directory)
        (directory / 'status.json').write_text(json.dumps({
            'status': 'execution_completed', 'audit_errors': [],
            'run_record': 'records/p3/first', 'artifact_sha256': 'fixturehash',
            'plan_sha256': hashlib.sha256(self.plan.read_bytes()).hexdigest()}))
        record = self.root / 'records/p3/first'
        record.mkdir(parents=True)
        evaluation = record / 'final_evaluation_summary.json'
        evaluation.write_text(json.dumps({'evaluation_status': 'completed',
            'infra_failure': False, 'resolved': False, 'artifact_sha256': 'fixturehash'}))
        self.assertEqual(prepare_trial(self.plan, 'P3-02', self.root)[1]['trial_id'], 'P3-02')
        evaluation.write_text(json.dumps({'evaluation_status': 'completed',
            'infra_failure': True, 'resolved': False, 'artifact_sha256': 'fixturehash'}))
        with self.assertRaisesRegex(ValueError, 'evaluation'):
            prepare_trial(self.plan, 'P3-02', self.root)

    def test_plan_revision_cannot_change_after_a_started_trial(self):
        *_, directory = prepare_trial(self.plan, 'P3-01', self.root)
        reserve_attempt(directory)
        (directory / 'status.json').write_text(json.dumps({
            'status': 'execution_completed', 'audit_errors': [],
            'plan_sha256': hashlib.sha256(self.plan.read_bytes()).hexdigest()}))
        data = json.loads(self.plan.read_text())
        data['note'] = 'A revision made after the first trial started.'
        self.plan.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            prepare_trial(self.plan, 'P3-02', self.root)


if __name__ == '__main__':
    unittest.main()

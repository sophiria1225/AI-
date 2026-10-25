import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from measure_checkpoint_realized_inputs import (
    PHASES, SOURCE_PLANS, SCOPE, PREPARATION, check_scope, closed_sources, fixed_parameters, sha)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def sources(folder):
    root, storage = Path(folder) / 'source', Path(folder) / 'storage'
    for phase in PHASES:
        tasks = ['synthetic_' + str(i) for i in range(4)]
        save(root / SOURCE_PLANS[phase], {'known_tasks': [{'task_id': t} for t in tasks]})
        directory = storage / 'records/context_pilot' / (phase + '_pipeline_v01')
        save(directory / 'status.json', {'status': 'complete', 'server_stopped': True, 'server_supervisor_pid': 12})
        save(directory / 'server_final.json', {'status': 'stopped', 'supervisor_pid': 12, 'pid': 13})
        policies = ('full', 'single_checkpoint') if phase == 'P118' else ('single_checkpoint', 'inline_checkpoint')
        rows = [{'run_id': phase + '_' + task + '_' + p, 'task_id': task, 'checkpoint_policy': p,
                 'record_status': 'not_run' if task == tasks[-1] else 'evaluated', 'success': None}
                for task in tasks for p in policies]
        audit_path = root / f'reports/{phase}_comparison.json'
        save(audit_path, {'phase': phase, 'audit_errors': [], 'owned_processes_absent': True,
            'batch_status': 'stopped', 'plan_sha256': sha(root / SOURCE_PLANS[phase]), 'rows': rows,
            'pipeline_status_sha256': sha(directory / 'status.json'),
            'server_final_sha256': sha(directory / 'server_final.json')})
        save(root / f'reports/{phase}_server_session.json', {'phase': phase, 'status': 'stopped',
            'owned_processes_absent': True, 'audit_source_sha256': sha(audit_path)})
    return root, storage


class CheckpointInputScopeTests(unittest.TestCase):
    def test_all_twenty_four_conditions_keep_unrun_slots(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch('measure_checkpoint_realized_inputs.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='')):
            root, storage = sources(folder)
            rows, runtime = closed_sources(storage, root)
            self.assertEqual(len(rows), 24)
            self.assertEqual(sum(r['record_status'] == 'not_run' for r in rows), 6)
            self.assertEqual(set(runtime), set(PHASES))

    def test_last_source_must_be_closed_and_have_unchanged_closure_records(self):
        for change in ('running', 'process_exists', 'altered_server'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder, \
                 patch('measure_checkpoint_realized_inputs.subprocess.run') as process:
                root, storage = sources(folder)
                process.return_value = SimpleNamespace(returncode=0 if change == 'process_exists' else 1,
                                                      stdout='synthetic process' if change == 'process_exists' else '')
                directory = storage / 'records/context_pilot/P120_pipeline_v01'
                if change == 'running':
                    save(directory / 'status.json', {'status': 'running', 'server_stopped': False, 'server_supervisor_pid': 12})
                elif change == 'altered_server':
                    save(directory / 'server_final.json', {'status': 'stopped', 'supervisor_pid': 12, 'pid': 99})
                with self.assertRaises(ValueError): closed_sources(storage, root)

    def test_scope_cannot_drop_prior_phases_or_claim_preparation_after_reading_P120_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save(root / SCOPE, fixed_parameters())
            save(root / PREPARATION, {'P120_outcomes_inspected': False, 'source_sha256': {}})
            check_scope(root)
            altered = fixed_parameters()
            altered['source_phases'] = ['P120']
            save(root / SCOPE, altered)
            with self.assertRaises(ValueError): check_scope(root)
            save(root / SCOPE, fixed_parameters())
            save(root / PREPARATION, {'P120_outcomes_inspected': True, 'source_sha256': {}})
            with self.assertRaises(ValueError): check_scope(root)


if __name__ == '__main__':
    unittest.main()

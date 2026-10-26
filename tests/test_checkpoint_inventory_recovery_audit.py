"""P131 closure/identity accounting on handwritten records; no model or task code."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_whole_task_checkpoint_inventory_recovery as auditor
import run_whole_task_checkpoint_inventory_recovery as driver


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


class RecoveryAuditTests(unittest.TestCase):
    def test_closed_batch_requires_exact_two_new_ids_and_no_old_phase(self):
        ids = [auditor.cell_id(*x) for x in auditor.run_order()]
        self.assertEqual(len(ids), 2)
        batch = dict(phase='P131', status='complete', rows=[], completed=ids, active=None)
        self.assertEqual(auditor.validate_closed_batch(batch), set(ids))
        for changes in ({'phase': 'P130'}, {'completed': ids[:1]},
                        {'completed': ids + [ids[0]]}, {'active': ids[0]},
                        {'rows': [{'run_id': 'BOC_P130_R01_01_OFF'}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                auditor.validate_closed_batch({**batch, **changes})

    def test_preflight_rejects_second_seed_duplicate_and_bool_identity(self):
        prepared = [{'task_id': 'synthetic'}]
        row = dict(replication=1, model_seed=57, task_id='synthetic',
                   conditions={m: {} for m in auditor.MODES})
        self.assertEqual(set(auditor.preflight_conditions([row], prepared)), {(1, 'synthetic')})
        for rows in ([], [row, row], [{**row, 'replication': True}],
                     [{**row, 'replication': 2, 'model_seed': 157}],
                     [{**row, 'conditions': {'off': {}}}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                auditor.preflight_conditions(rows, prepared)

    def fixture(self, storage, root):
        prepared = [{'task_id': 'synthetic'}]
        pre = {'rows': [dict(replication=1, model_seed=57, task_id='synthetic',
                            conditions={m: {} for m in auditor.MODES})]}
        write(root / auditor.PREFLIGHT, pre)
        hashes = {'synthetic.py': '0' * 64}
        write(root / auditor.ACTIVATION, dict(source_hashes=hashes,
              preflight_sha256=auditor.sha(root / auditor.PREFLIGHT)))
        plan = {'batch_id': 'P131_batch_v01'}
        write(root / auditor.PLAN, plan)
        pipeline = storage / 'records/context_pilot/P131_pipeline_v01'
        write(pipeline / 'status.json', dict(status='stopped', server_stopped=True,
              server_supervisor_pid=12345))
        write(pipeline / 'server_final.json', dict(status='stopped', pid=12344,
              supervisor_pid=12345))
        ids = [auditor.cell_id(*x) for x in auditor.run_order()]
        write(storage / 'records/context_pilot/P131_batch_v01/status.json',
              dict(phase='P131', status='stopped', rows=[], completed=[], active=ids[0]))
        return prepared, plan, hashes, ids, pipeline

    def test_stopped_audit_keeps_both_missing_slots_without_zero_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            storage, root = Path(tmp) / 'storage', Path(tmp) / 'repo'
            prepared, plan, hashes, ids, _ = self.fixture(storage, root)
            stack.enter_context(patch.object(driver, 'sources', return_value=(plan, {}, [], prepared)))
            stack.enter_context(patch.object(driver, 'frozen_hashes', return_value=hashes))
            stack.enter_context(patch.object(auditor.subprocess, 'run',
                return_value=SimpleNamespace(returncode=1, stdout='')))
            stack.enter_context(patch('builtins.print'))
            result = auditor.run(storage, root)
            self.assertEqual([r['run_id'] for r in result['rows']], ids)
            self.assertEqual([r['record_status'] for r in result['rows']], ['incomplete_worker', 'not_run'])
            self.assertTrue(all(r['known_total_tokens'] is None and r['inventory_accounting_complete'] is None
                                for r in result['rows']))
            self.assertFalse(result['development_gate_met'])
            self.assertEqual((result['planned_rows'], result['repetitions'], result['model_seeds']), (2, 1, [57]))
            with self.assertRaises(FileExistsError): auditor.run(storage, root)

    def test_cell_audit_failure_is_retained_and_does_not_create_success(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            storage, root = Path(tmp) / 'storage', Path(tmp) / 'repo'
            prepared, plan, hashes, ids, _ = self.fixture(storage, root)
            write(storage / 'records/context_pilot' / ids[0] / 'summary.json', {'synthetic': True})
            stack.enter_context(patch.object(driver, 'sources', return_value=(plan, {}, [], prepared)))
            stack.enter_context(patch.object(driver, 'frozen_hashes', return_value=hashes))
            stack.enter_context(patch.object(auditor.subprocess, 'run',
                return_value=SimpleNamespace(returncode=1, stdout='')))
            stack.enter_context(patch.object(auditor, 'audit_cell', side_effect=ValueError('synthetic_failure')))
            stack.enter_context(patch('builtins.print'))
            result = auditor.run(storage, root)
            self.assertEqual(result['rows'][0]['record_status'], 'audit_error')
            self.assertIsNone(result['rows'][0]['success'])
            self.assertIsNone(result['rows'][0]['known_total_tokens'])
            self.assertEqual(len(result['audit_errors']), 1)
            self.assertFalse(result['development_gate_met'])

    def test_unclosed_or_live_owned_server_is_rejected_before_sources(self):
        for live in (False, True):
            with self.subTest(live=live), tempfile.TemporaryDirectory() as tmp:
                storage, root = Path(tmp) / 'storage', Path(tmp) / 'repo'
                _, _, _, _, pipeline = self.fixture(storage, root)
                if not live:
                    state = json.loads((pipeline / 'status.json').read_text())
                    state['status'] = 'running'; write(pipeline / 'status.json', state)
                with patch.object(driver, 'sources') as source, patch.object(auditor.subprocess, 'run',
                        return_value=SimpleNamespace(returncode=0, stdout='synthetic owned process')):
                    with self.assertRaises(ValueError): auditor.run(storage, root)
                    source.assert_not_called()


if __name__ == '__main__':
    unittest.main()

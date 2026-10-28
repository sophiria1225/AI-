"""Continuation equivalence and namespace boundaries without model/API calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import state_update_resume_config_p144r1 as config
import run_state_update_resume_cell_p144r1 as worker
import whole_task_state_update_p144 as original


def inputs():
    plan = json.loads((ROOT / 'configs/P144_state_update_v01.json').read_text())
    source = json.loads((ROOT / plan['source_plan']).read_text())
    return source, plan


class ResumeCellTests(unittest.TestCase):
    def test_scientific_worker_body_exactly_matches_frozen_original(self):
        before = (ROOT / 'scripts/run_whole_task_state_update_cell_p144.py').read_text()
        after = (ROOT / 'scripts/run_state_update_resume_cell_p144r1.py').read_text()
        changes = {
            '"""P144 cell: P143 worker path with the bounded three-arm state-update adapter.':
                '"""P144R1 continuation cell; scientific P144 worker body preserved.\n'
                'Operational changes: new validated run IDs, new stop marker and summary phase.\n'
                'P144 cell: P143 worker path with the bounded three-arm state-update adapter.',
            'from whole_task_state_update_p144 import worker_config':
                'from state_update_resume_config_p144r1 import worker_config',
            "'.runtime/P144.stop'": "'.runtime/P144R1.stop'",
            "'explicit_P144_stop'": "'explicit_P144R1_stop'",
            "{'phase':'P144', 'run_id':run_id": "{'phase':'P144R1', 'run_id':run_id",
        }
        for old, new in changes.items():
            self.assertEqual(before.count(old), 2 if old == "'explicit_P144_stop'" else 1)
            before = before.replace(old, new)
        self.assertEqual(before, after)

    def test_all_ten_scientific_configs_equal_original_without_mutation(self):
        source, plan = inputs()
        frozen = deepcopy((source, plan))
        self.assertEqual(len(config.REMAINING), 10)
        for number, mode in config.REMAINING:
            with self.subTest(number=number, mode=mode):
                actual = config.worker_config(source, plan, original.TASKS[number-1],
                    original.ERROR_POLICY, config.cell_id(number, mode), mode)
                expected = original.worker_config(source, plan, original.TASKS[number-1],
                    original.ERROR_POLICY, original.cell_id(number, mode), mode)
                self.assertEqual(actual, expected)
                self.assertNotIn('run_id', actual)
        self.assertEqual((source, plan), frozen)

    def test_completed_slots_and_wrong_or_unknown_identity_are_rejected(self):
        source, plan = inputs()
        for mode in original.MODES[:2]:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                config.cell_id(1, mode)
        for number, mode in ((True, original.MODES[2]), (5, original.MODES[0]),
                             (1, 'unknown')):
            with self.subTest(number=number, mode=mode), self.assertRaises(ValueError):
                config.cell_id(number, mode)
        number, mode = config.REMAINING[0]
        for run_id in (original.cell_id(number, mode), 'BOC_P144R1_UNKNOWN',
                       config.cell_id(2, mode), None):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                config.worker_config(source, plan, original.TASKS[0],
                    original.ERROR_POLICY, run_id, mode)
        with self.assertRaises(ValueError):
            config.worker_config(source, plan, original.TASKS[0], 'error_value',
                config.cell_id(number, mode), mode)

    def test_repeated_missing_reordered_or_extra_slots_are_rejected(self):
        ids = config.remaining_ids()
        config.validate_remaining_ids(ids)
        config.validate_remaining_ids(list(ids))
        for changed in (ids[:-1], ids + ids[:1], ids[:1] + ids[:-1], ids[::-1], set(ids)):
            with self.subTest(identities=str(changed)), self.assertRaises(ValueError):
                config.validate_remaining_ids(changed)

    def test_scientific_plan_change_rejected_before_worker_allocation(self):
        source, plan = inputs()
        number, mode = config.REMAINING[0]
        for key, value in (('model_seed', 258), ('max_wall_seconds', 1799),
                           ('trigger_input_tokens', 8193), ('world_seed', 43)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                config.worker_config(source, dict(plan, **{key:value}), original.TASKS[0],
                    original.ERROR_POLICY, config.cell_id(number, mode), mode)

    def test_new_stop_marker_prevents_bridge_and_old_marker_is_preserved(self):
        source, plan = inputs()
        number, mode = config.REMAINING[0]
        item = {'task_id':original.TASKS[0], 'source_run':'P29_01_CODE',
                'known_public_task_sha256':'synthetic', 'public_task':{}}
        for marker, expected_called, reason in (('P144R1.stop', False, 'user_stop'),
                                                ('P144.stop', True, 'setup_failure')):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                storage = Path(temp)
                (storage / '.runtime').mkdir()
                stop = storage / '.runtime' / marker
                stop.write_text('unchanged stop record')
                with patch.object(worker.TypedBridgeProcess, '__init__',
                        side_effect=RuntimeError('synthetic bridge boundary')) as constructor:
                    result = worker.run_cell(storage, ROOT, plan, source, [], item,
                        original.ERROR_POLICY, config.cell_id(number, mode),
                        checkpoint_representation_mode=mode)
                self.assertEqual(constructor.called, expected_called)
                self.assertEqual(result['stop_reason'], reason)
                self.assertEqual(result['phase'], 'P144R1')
                self.assertEqual(result['model_calls'], 0)
                self.assertEqual(stop.read_text(), 'unchanged stop record')

    def test_existing_trial_and_world_are_never_overwritten(self):
        source, plan = inputs()
        number, mode = config.REMAINING[0]
        rid = config.cell_id(number, mode)
        item = {'task_id':original.TASKS[0], 'source_run':'P29_01_CODE',
                'known_public_task_sha256':'synthetic', 'public_task':{}}
        for prefix in ('records/context_pilot', '.runtime/appworld/r18_probe_01/experiments/outputs'):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temp:
                storage = Path(temp)
                (storage / prefix / rid).mkdir(parents=True)
                with patch.object(worker.TypedBridgeProcess, '__init__') as constructor:
                    with self.assertRaises(FileExistsError):
                        worker.run_cell(storage, ROOT, plan, source, [], item,
                            original.ERROR_POLICY, rid, checkpoint_representation_mode=mode)
                constructor.assert_not_called()


if __name__ == '__main__':
    unittest.main()

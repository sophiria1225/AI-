import copy
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_whole_task_remaining_late_obligations_p137 import preflight_conditions, validate_closed_batch
from inspect_whole_task_remaining_late_obligations_session_p137 import cell_time_totals
import run_whole_task_remaining_late_obligations_pipeline_p137 as pipeline
from whole_task_remaining_late_obligations_p137 import cell_id, run_order


class RemainingClosureTests(unittest.TestCase):
    def test_asymmetric_preflight_excludes_the_two_previously_attempted_slots(self):
        rows = [dict(replication=1, model_seed=57, task_id='fixture',
                     conditions={'entity_fields': {}}),
                dict(replication=2, model_seed=157, task_id='fixture',
                     conditions={'entity_fields': {}, 'ids_only': {}, 'raw_anchor': {}})]
        self.assertEqual(len(preflight_conditions(rows, [{'task_id': 'fixture'}])), 2)
        for mode in ('raw_anchor', 'ids_only'):
            changed = copy.deepcopy(rows)
            changed[0]['conditions'][mode] = {}
            with self.assertRaises(ValueError):
                preflight_conditions(changed, [{'task_id': 'fixture'}])

    def test_closed_batch_preserves_four_exact_planned_slots_and_attempt_state(self):
        order = [cell_id(*item) for item in run_order()]
        batch = dict(phase='P137', status='stopped', planned=order, completed=[],
                     rows=[], active=order[0])
        self.assertEqual(validate_closed_batch(batch), set(order))
        for changed in ({**batch, 'planned': list(reversed(order))},
                        {**batch, 'status': 'complete', 'active': None},
                        {**batch, 'active': 'BOC_P136_R01_01_IDS_ONLY'}):
            with self.assertRaises(ValueError):
                validate_closed_batch(changed)

    def test_incomplete_worker_time_is_unknown_but_unstarted_time_is_not_paid(self):
        value = cell_time_totals([dict(record_status='evaluated', full_wall_seconds=4),
                                 dict(record_status='incomplete_worker'),
                                 dict(record_status='not_run'), dict(record_status='not_run')])
        self.assertEqual(value['known_cell_full_wall_seconds'], 4)
        self.assertEqual(value['unknown_cell_full_wall_count'], 1)
        self.assertIsNone(value['cell_full_wall_seconds'])

    def test_late_launch_cannot_spawn_a_server_or_shrink_the_outer_budget(self):
        plan = dict(deadline_jst='2026-10-27T18:00:00+09:00',
                    server_max_lifetime_seconds=14400)
        too_late = datetime.fromisoformat('2026-10-27T13:41:00+09:00').timestamp()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(pipeline.subprocess, 'check_output', side_effect=['fixed\n', '']), \
                patch.object(pipeline, 'checked_ci', return_value=[]), \
                patch.object(pipeline, 'check_resume', return_value={}), \
                patch.object(pipeline, 'read', return_value=plan), \
                patch.object(pipeline.time, 'time', return_value=too_late), \
                patch.object(pipeline.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'exceed_user_deadline'):
                pipeline.run(Path(directory), 'fixed')
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()

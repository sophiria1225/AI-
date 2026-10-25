import unittest

from inspect_whole_task_projection_session import cell_time_totals


class ProjectionSessionTests(unittest.TestCase):
    def test_missing_started_measurement_is_not_zero(self):
        result = cell_time_totals([
            {'record_status': 'evaluated', 'full_wall_seconds': 5.5},
            {'record_status': 'incomplete_worker'}, {'record_status': 'not_run'}])
        self.assertEqual(result['known_cell_full_wall_seconds'], 5.5)
        self.assertEqual(result['unknown_cell_full_wall_count'], 1)
        self.assertIsNone(result['cell_full_wall_seconds'])

    def test_not_run_cost_is_zero_without_unknown_measurement(self):
        result = cell_time_totals([
            {'record_status': 'unevaluated', 'full_wall_seconds': 7},
            {'record_status': 'not_run'}])
        self.assertEqual(result['cell_full_wall_seconds'], 7)
        self.assertEqual(result['unknown_cell_full_wall_count'], 0)

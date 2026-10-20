import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_native_boundaries import check_state


class BoundaryPrefixControls(unittest.TestCase):
    def test_budget_and_completion_must_follow_recorded_operations(self):
        usage = [{'status': 'ok', 'input_tokens': 100, 'output_tokens': 20}]
        events = [{'api_request_sent': True, 'declared_complete': False}]
        spans = {'s1': {'observation': 'PRIVATE_OBSERVATION'}}
        state = {'run_id': 'P11_01_ROLES', 'task_id': 'task', 'arm': 'native_roles',
                 'model_calls': 1, 'known_total_tokens': 120, 'api_requests': 1,
                 'span_ids': ['s1'], 'remaining_tokens': 880, 'declared_complete': False,
                 'rng_and_process_state_captured': False, 'visible_api_schemas': ['app__read'],
                 'elapsed_wall_seconds': 10, 'remaining_wall_seconds_before_capture': 90}
        args = (usage, events, spans, {'max_total_tokens': 1000, 'max_wall_seconds': 100},
                'P11_01_ROLES', 'task', {'app__read'})
        self.assertEqual(check_state(state, *args), [])
        for key, value in [('declared_complete', True), ('remaining_tokens', 1000),
                           ('rng_and_process_state_captured', True), ('api_requests', 0)]:
            changed = copy.deepcopy(state); changed[key] = value
            errors = check_state(changed, *args)
            self.assertTrue(errors)
            self.assertNotIn('PRIVATE_OBSERVATION', str(errors))

    def test_invalid_elapsed_time_is_not_accepted_as_a_budget_record(self):
        args = ([], [], {}, {'max_total_tokens': 1000, 'max_wall_seconds': 100}, 'run', 'task', set())
        self.assertIn('boundary wall accounting disagrees', check_state({'elapsed_wall_seconds': -1}, *args))


if __name__ == '__main__':
    unittest.main()

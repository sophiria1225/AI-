import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_native_observation_shape import observation_shape


class ObservationShapeControls(unittest.TestCase):
    def test_values_and_private_operation_names_are_never_exported(self):
        span = {'id': 's1', 'action': {'name': 'phone__list', 'arguments': 'PRIVATE_TOKEN'},
                'observation': {'observation': '[{"secret":"PRIVATE_VALUE"}]'}}
        row = observation_shape(span, {'phone__list': 'GET'})
        self.assertEqual(row['top_level_list_items'], 1)
        self.assertNotIn('PRIVATE', json.dumps(row))
        span['action']['name'] = 'PRIVATE_UNKNOWN'
        with self.assertRaises(ValueError):
            observation_shape(span, {'phone__list': 'GET'})


if __name__ == '__main__':
    unittest.main()

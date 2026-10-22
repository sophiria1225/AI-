import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_new_move_scope import inspect_records, later_cost


class NewMoveScopeTests(unittest.TestCase):
    def fixture(self):
        root = '/home/fixture/Photos'; files = [root+'/one.jpg', root+'/two.jpg']
        task = {'ground_truth_loaded': False, 'instruction':
            'Arrange my "~/Photos" directory by organizing the photos from three vacations. '
            'The files created in February and March of this year correspond to Japan and Peru, '
            'respectively, while the others are from Italy. Move them into sub-directories '
            'named after their respective vacation spots, maintaining the original file names.'}
        requests = [
            ('file_system__show_directory', {'directory_path': '~/Photos'}, files),
            ('phone__get_current_date_and_time', {}, {'date': 'Saturday, April 01, 2023', 'time': '09:00:00'}),
        ]
        requests += [('file_system__show_file', {'file_path': path},
            {'path': path, 'file_id': n, 'created_at': f'2023-0{n+1}-01T12:00:00'}) for n, path in enumerate(files, 1)]
        requests += [('file_system__move_file', {'source_file_path': path, 'destination_file_path': root+'/'+dest+'/'+Path(path).name},
            {'message': 'File moved.', 'destination_file_path': root+'/'+dest+'/'+Path(path).name})
            for path, dest in zip(files, ('Japan', 'Peru'))]
        events = []; spans = {}; usage = []
        for n, (name, args, response) in enumerate(requests, 1):
            if name.startswith('file_system__'): args['access_token'] = 'synthetic-token'
            sid, cid = f's{n}', f'call_{n:03d}'
            spans[sid] = {'action': {'name': name, 'arguments': json.dumps(args)},
                'observation': {'observation': json.dumps(response)}}
            events.append({'span_id': sid, 'call': cid, 'api_request_sent': True, 'effects_unknown': False})
            usage.append({'id': cid, 'usage_known': True, 'input_tokens': 20, 'output_tokens': 3})
        source = {'run_id': 'synthetic', 'arm': 'synthetic', 'success': None,
            'api_requests': len(events), 'prefix_api_requests': 0}
        return task, spans, events, usage, source

    def test_valid_temporal_receipts_support_declared_moves_and_ignore_outer_text(self):
        t, s, e, u, source = self.fixture()
        s['outer'] = {'action': None, 'observation': {'format_error': 'tool call required'}}
        e.insert(0, {'span_id': 'outer', 'call': u[0]['id'], 'api_request_sent': False})
        result = inspect_records(t, s, [], e, u, source)
        self.assertEqual(result['final']['trace_support'], 'supported')
        self.assertEqual(result['final']['filename_preserved_moves'], 2)
        self.assertEqual(result['public_clock_years_observed'], 1)

    def test_metadata_after_first_move_remains_outside_strict_adapter_scope(self):
        t, s, e, u, source = self.fixture()
        e[3]['call'], e[4]['call'] = e[4]['call'], e[3]['call']
        result = inspect_records(t, s, [], e, u, source)
        self.assertEqual(result['final']['trace_support'], 'unknown')
        self.assertEqual(result['final']['metadata_files'], 1)

    def test_failed_clock_cannot_supply_the_year(self):
        t, s, e, u, source = self.fixture()
        s['s2']['observation'] = {'observation': json.dumps({'error': 'fixture failure'})}
        result = inspect_records(t, s, [], e, u, source)
        self.assertEqual(result['final']['trace_support'], 'unknown')
        self.assertEqual(result['public_clock_years_observed'], 0)

    def test_later_cost_retains_unknown_usage_and_is_not_a_saving(self):
        boundaries = [{'boundary': 'call_001', 'trace_support': 'supported'}]
        usage = [{'id': 'call_001', 'usage_known': True, 'input_tokens': 20, 'output_tokens': 3},
            {'id': 'call_002', 'usage_known': True, 'input_tokens': 40, 'output_tokens': 5},
            {'id': 'call_003', 'usage_known': False, 'input_tokens': None, 'output_tokens': None}]
        result = later_cost(boundaries, usage)
        self.assertEqual(result['later_model_calls'], 2)
        self.assertEqual(result['later_known_tokens'], 45)
        self.assertEqual(result['later_unknown_usage_calls'], 1)
        self.assertFalse(result['is_measured_saved_cost']); self.assertFalse(result['controller_installed'])

    def test_no_supported_boundary_does_not_create_zero_cost_savings(self):
        self.assertIsNone(later_cost([{'boundary': 'prefix', 'trace_support': 'unknown'}], []))
        with self.assertRaises(ValueError):
            later_cost([{'boundary': 'missing', 'trace_support': 'supported'}], [])


if __name__ == '__main__': unittest.main()

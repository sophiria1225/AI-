"""Protect state isolation and exactly-once source replay in the terminal probe."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_completion_scope import fixed_cases, sent_events, terminal_changes, worker_record


class CompletionScopeTests(unittest.TestCase):
    def test_missing_or_partial_worker_record_is_not_zero_cost(self):
        case = {'source_run': 'source', 'run_id': 'run', 'arm': 'no_completion'}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.assertFalse(worker_record(folder, case)['request_accounting_finalized'])
            (folder / 'result.json').write_text('{"partial":')
            self.assertFalse(worker_record(folder, case)['request_accounting_finalized'])

    def test_unknown_or_duplicate_source_effects_cannot_be_replayed(self):
        event = {'span_id': 's1', 'stage': 'python_api', 'api_request_sent': True, 'effects_unknown': False}
        spans = {'s1': {'action': {'name': 'file_system__move_file', 'arguments': '{}'}}}
        self.assertEqual(sent_events([event], [], spans), [event])
        with self.assertRaises(ValueError): sent_events([event], [event], spans)
        with self.assertRaises(ValueError): sent_events([{**event, 'effects_unknown': True}], [], spans)
        self.assertEqual(sent_events([{**event, 'api_request_sent': False}], [], spans), [])

    def test_completion_does_not_license_other_application_changes(self):
        before = {'dbs/file_system.jsonl': 'files', 'dbs/supervisor.jsonl': 'pending', 'dbs/model_hashes.json': 'old'}
        completed = {**before, 'dbs/supervisor.jsonl': 'complete', 'dbs/model_hashes.json': 'new'}
        self.assertEqual(len(terminal_changes(before, completed, 'append_completion')), 2)
        with self.assertRaises(ValueError): terminal_changes(before, completed, 'no_completion')
        with self.assertRaises(ValueError): terminal_changes(before, {**completed, 'dbs/file_system.jsonl': 'changed'}, 'append_completion')
        with self.assertRaises(ValueError): terminal_changes(before, {'dbs/supervisor.jsonl': 'complete'}, 'append_completion')

    def test_fixed_probe_cannot_search_new_answers_or_extend_budget(self):
        plan = json.loads((Path(__file__).resolve().parents[1] / 'configs/P56_completion_scope_v01.json').read_text())
        self.assertEqual(len(fixed_cases(plan)), 4)
        altered = copy.deepcopy(plan)
        altered['completion_action']['arguments'] = '{"answer":"new candidate"}'
        with self.assertRaises(ValueError): fixed_cases(altered)
        with self.assertRaises(ValueError): fixed_cases({**plan, 'max_api_requests_per_case': 121})


if __name__ == '__main__': unittest.main()

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_p3 import audit_protocol


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class P3AuditControls(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run = Path(self.directory.name)
        initial = self.run/'artifact_versions/initial/final.patch'
        initial.parent.mkdir(parents=True)
        initial.write_bytes(b'')
        sha = hashlib.sha256(b'').hexdigest()
        state = {'units': ['single'], 'artifact_sha256': sha, 'revision': 0,
                 'votes': {'single': sha}, 'complete': True}
        event = {'turn': 1, 'unit': 'single', 'artifact': state, 'artifact_changed': False,
                 'completion_vote_accepted': True,
                 'operations': [{'result': {'output': 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n', 'returncode': 0}}]}
        write(self.run/'artifact_versions/001/turn.json', event)
        (self.run/'artifact_versions/001/final.patch').write_bytes(b'')
        before = {'recorded_total_tokens': 0, 'attempted_calls': 0, 'remaining_tokens': 1000, 'remaining_calls': 5}
        after = {'recorded_total_tokens': 120, 'attempted_calls': 1, 'pending': False, 'usage_complete': True}
        write(self.run/'call_001_single/budget_before.json', before)
        write(self.run/'call_001_single/budget_after.json', after)
        self.summary = {'strategy': 'single', 'calls': [{'path': 'call_001_single', 'unit': 'single', 'input_tokens': 100, 'output_tokens': 20}],
                        'turns': [{'artifact': state}], 'budget': after, 'usage_complete': True,
                        'completion': state, 'stop_reason': 'submitted', 'artifact_sha256': sha}
        write(self.run/'summary.json', self.summary)
        write(self.run/'config.json', {'max_calls': 5, 'max_total_tokens': 1000})

    def test_consistent_record_passes(self):
        self.assertEqual(audit_protocol(self.run), [])

    def test_resetting_shared_budget_is_detected(self):
        path = self.run/'call_001_single/budget_after.json'
        data = json.loads(path.read_text()); data['recorded_total_tokens'] = 20
        write(path, data)
        self.assertTrue(any('global budget after' in e for e in audit_protocol(self.run)))

    def test_changed_artifact_cannot_keep_old_vote(self):
        (self.run/'artifact_versions/001/final.patch').write_bytes(b'changed artifact fixture')
        self.assertTrue(any('completion does not match' in e for e in audit_protocol(self.run)))

    def test_failed_marker_cannot_be_a_completion(self):
        path = self.run/'artifact_versions/001/turn.json'
        data = json.loads(path.read_text()); data['operations'][0]['result']['returncode'] = 3
        write(path, data)
        errors = audit_protocol(self.run)
        self.assertTrue(any('completion decision differs' in e for e in errors))
        self.assertTrue(any('submitted without' in e for e in errors))


if __name__ == '__main__':
    unittest.main()

import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pro_runtime import PUBLIC_FIELDS, load_public_task, task_text
from evaluate_pro_environment import PRIVATE_FILES, make_archive
from evaluate_pro_pilot import frozen_patch
from run_pro_pilot import prepare


class ProPilotGuardTests(unittest.TestCase):
    def test_public_projection_rejects_hidden_fields_and_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {k: 'public' for k in PUBLIC_FIELDS}
            row.update(instance_id='task', base_commit='a' * 40)
            spec = {'public_inputs': 'public.jsonl', 'instance_id': 'task',
                    'base_commit': 'a' * 40}
            path = root / spec['public_inputs']
            path.write_text(json.dumps(row) + '\n')
            spec['public_inputs_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(load_public_task(root, spec), row)
            row['patch'] = 'must not be accepted'
            path.write_text(json.dumps(row) + '\n')
            with self.assertRaises(ValueError):
                load_public_task(root, spec)
            spec['public_inputs_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                load_public_task(root, spec)

    def test_all_public_instruction_fields_are_preserved(self):
        values = {'problem_statement': 'problem <literal>',
                  'requirements': 'requirement\nsecond line', 'interface': 'interface'}
        result = task_text(values)
        for value in values.values():
            self.assertIn(value, result)

    def test_candidate_receives_no_reference_patch_and_empty_diff_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in PRIVATE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'synthetic verifier file')
            for candidate in (b'', b'synthetic candidate diff'):
                data = make_archive(root, {'base_commit': 'a' * 40},
                                    'candidate_evaluation', '/app', candidate_patch=candidate)
                with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                    self.assertNotIn('solution/gold_patch.diff', archive.getnames())
                    self.assertEqual(archive.extractfile('research/candidate.patch').read(), candidate)
                    script = archive.extractfile('research/run.sh').read()
                    self.assertEqual(b'git apply --check' in script, bool(candidate))
            with self.assertRaises(ValueError):
                make_archive(root, {'base_commit': 'a' * 40}, 'negative_control',
                             '/app', candidate_patch=b'diff')

    def test_candidate_tampering_or_incomplete_usage_blocks_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'final.patch').write_bytes(b'candidate')
            digest = hashlib.sha256(b'candidate').hexdigest()
            summary = {'execution_status': 'completed', 'audit_errors': [],
                       'usage_complete': True, 'artifact_frozen_at': 'time',
                       'container_removed': True, 'artifact_sha256': digest}
            (root / 'summary.json').write_text(json.dumps(summary))
            (root / 'audit.json').write_text(json.dumps({'errors': [], 'artifact_sha256': digest}))
            self.assertEqual(frozen_patch(root)[1], b'candidate')
            (root / 'final.patch').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                frozen_patch(root)
            (root / 'final.patch').write_bytes(b'candidate')
            summary['usage_complete'] = False
            (root / 'summary.json').write_text(json.dumps(summary))
            with self.assertRaises(ValueError):
                frozen_patch(root)

    def test_changed_frozen_source_is_rejected_before_any_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'scripts/runner.py').write_bytes(b'changed')
            plan = {'trial_count': 1, 'strategy': 'single', 'config_sha256': {},
                    'source_sha256': {'runner.py': hashlib.sha256(b'original').hexdigest()}}
            path = root / 'plan.json'
            path.write_text(json.dumps(plan))
            with patch('run_pro_pilot.ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Frozen source'):
                    prepare(path, root)


if __name__ == '__main__':
    unittest.main()

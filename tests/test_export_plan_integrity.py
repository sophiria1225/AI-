import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evaluate_data_export_probe_v02 import evaluate


class PlanIntegrityTests(unittest.TestCase):
    def prepare(self, root):
        values = {'run_id': 'P20_01', 'max_output_tokens': 4096}
        original = root / 'original.json'
        original.write_text(json.dumps(values, separators=(',', ':')))
        (root / 'plan.json').write_text(json.dumps(values, indent=4))
        (root / 'status.json').write_text('{"status":"complete"}')
        (root / 'provenance.json').write_text('{"config": {"model": {}}}')
        (root / 'input_private.json').write_text('{"observations": []}')
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        (root / 'freeze_record.json').write_text(json.dumps({
            'input_sha256': digest(root / 'input_private.json'),
            'plan_sha256': digest(original), 'source_hashes': {},
        }))
        return original

    def test_reserialization_preserves_plan_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.prepare(root)
            with patch('evaluate_data_export_probe_v02.schedule', side_effect=LookupError('integrity passed')):
                with self.assertRaisesRegex(LookupError, 'integrity passed'):
                    evaluate(root, original)

    def test_changed_recorded_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.prepare(root)
            (root / 'plan.json').write_text('{"run_id":"P20_01","max_output_tokens":8192}')
            with self.assertRaisesRegex(ValueError, 'frozen input or plan changed'):
                evaluate(root, original)

    def test_changing_both_copies_still_fails_frozen_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.prepare(root)
            changed = '{"run_id":"P20_01","max_output_tokens":8192}'
            original.write_text(changed)
            (root / 'plan.json').write_text(changed)
            with self.assertRaisesRegex(ValueError, 'frozen input or plan changed'):
                evaluate(root, original)


if __name__ == '__main__':
    unittest.main()

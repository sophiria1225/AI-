import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from browsecomp_terminal import digest
from run_browsecomp_batch import body, check_plan, collect


class BatchTests(unittest.TestCase):
    def test_changed_order_and_changed_source_prevent_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'source.py').write_text('original')
            plan = {'phase': 'P15', 'batch_id': 'P15_batch_v01', 'selected_ids': ['1', '2', '3'],
                    'run_ids': {'1': 'P15_01_FULL', '2': 'P15_02_FULL'}}
            path = root / 'plan.json'; path.write_text(json.dumps(plan))
            frozen = {'plan_sha256': digest(path), 'source_hashes': {'source.py': digest(root / 'source.py')}}
            with patch('run_browsecomp_batch.ROOT', root):
                check_plan(plan, frozen, path)
                changed = dict(plan, run_ids={'2': 'P15_01_FULL', '1': 'P15_02_FULL'})
                with self.assertRaises(ValueError):
                    check_plan(changed, frozen, path)
                (root / 'source.py').write_text('changed')
                with self.assertRaises(ValueError):
                    check_plan(plan, frozen, path)

    def test_progress_omits_private_fields_and_preserves_unknown_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); trial = root / 'records/browsecomp_pilot/P15_01_FULL'
            trial.mkdir(parents=True)
            (trial / 'usage.json').write_text(json.dumps([
                {'status': 'ok', 'input_tokens': 100, 'output_tokens': 20, 'response': 'PRIVATE'},
                {'status': 'error', 'input_tokens': None, 'output_tokens': None}]))
            (trial / 'question_private.json').write_text('MUST_NOT_EXPORT')
            plan = {'run_ids': {'1': 'P15_01_FULL', '2': 'P15_02_FULL'}}
            rows = collect(root, plan)
            self.assertEqual(rows[0]['known_tokens'], 120)
            self.assertEqual(rows[0]['unknown_usage_calls'], 1)
            text = body({'status': 'running', 'rows': rows})
            self.assertNotIn('MUST_NOT_EXPORT', text); self.assertNotIn('PRIVATE', text)
            self.assertIsNone(rows[0]['submitted'])


if __name__ == '__main__':
    unittest.main()

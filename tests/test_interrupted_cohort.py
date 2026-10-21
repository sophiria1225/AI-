import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from continue_p13_after_interruption import interrupted_cost, validate_cohort


class InterruptionControls(unittest.TestCase):
    def test_missing_response_is_unknown_and_completed_failure_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            order = [[str(i), 'native_focus', f'P13_{i:02d}_FOCUS'] for i in range(1, 5)]
            for row in order[:2]:
                p = base / row[2]; p.mkdir()
                (p / 'summary.json').write_text('{}')
                (p / 'evaluation.json').write_text('{"official_success": false}')
            p = base / order[2][2]; p.mkdir()
            (p / 'usage.json').write_text(json.dumps([
                {'id': 'call_001', 'status': 'ok', 'input_tokens': 10, 'output_tokens': 2}]))
            q = p / 'call_002'; q.mkdir(); (q / 'request.json').write_text('PRIVATE')
            schedule = [list(r) for r in order]; schedule[2][2] = 'P13_03_FOCUS_RECOVERY01'
            result = validate_cohort({'cohort': schedule}, {'run_order': order}, base)
            self.assertEqual(result['known_total_tokens'], 12)
            self.assertEqual(result['incomplete_requests'], 1)
            self.assertNotIn('PRIVATE', json.dumps(result))
            bad = [list(r) for r in schedule]; bad[0][2] += '_RETRY'
            with self.assertRaises(ValueError):
                validate_cohort({'cohort': bad}, {'run_order': order}, base)
            (p / 'summary.json').write_text('{}')
            with self.assertRaises(ValueError): interrupted_cost(p)

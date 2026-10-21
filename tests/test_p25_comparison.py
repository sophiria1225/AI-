import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_p25_guidance import analyze, comparison
import test_generic_guidance_comparison as fixture


class P25Comparison(unittest.TestCase):
    def test_full_four_preserves_improvements_regressions_and_unknown_cost(self):
        values = fixture.fixture()
        for index, phase in enumerate(('P18', 'P25')):
            plan, summary, budget = values[index], values[index+2], values[index+4]
            plan['phase'] = phase
            plan['task_ids'] += ['c', 'd']
            for row in copy.deepcopy(plan['run_order']):
                row[0] = {'a':'c','b':'d'}[row[0]]; row[2] += '_extra'
                plan['run_order'].append(row)
            for row in copy.deepcopy(summary['trials']):
                row['task_id'] = {'a':'c','b':'d'}[row['task_id']]
                row['run_id'] += '_extra'; summary['trials'].append(row)
            for row in copy.deepcopy(budget['trials']):
                row['run_id'] += '_extra'; budget['trials'].append(row)
            summary['total_model_calls'] *= 2
            summary['known_total_tokens'] *= 2
        values[2]['trials'][0]['unknown_usage_calls'] = 1
        values[2]['unknown_usage_calls'] = 1
        values[4]['trials'][0]['unknown_usage_calls'] = 1
        result = comparison(values)
        self.assertEqual(result['outcome_counts'], {'worsened':2,'improved':2})
        self.assertEqual(result['totals']['guided']['trials'], 4)
        self.assertIsNone(result['exact_total_token_delta'])
        self.assertIn('Four', result['limitations'][0])
        values[1]['run_order'].pop()
        with self.assertRaisesRegex(ValueError, 'all four'):
            comparison(values)

    def test_running_batch_is_refused_before_any_result_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for phase in ('P18', 'P25'):
                p = root/'records/context_pilot'/f'{phase}_batch_v01/status.json'
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'status':'running' if phase == 'P25' else 'complete'}))
            with self.assertRaisesRegex(ValueError, 'wait for both full batches'):
                analyze(root, root)


if __name__ == '__main__':
    unittest.main()

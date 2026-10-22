import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_input_exposure import audit_row
from input_exposure_accounting import COMPONENTS, token_increments


class InputExposureAuditTests(unittest.TestCase):
    def fixture(self, folder):
        expected = {'source_run': 'synthetic', 'outputs': [{'span_id': 's1'}],
                    'p42_candidates_accounted': 1, 'p42_full_input_tokens': 20}
        cases = [{'component': name, 'messages': [{'role': 'user', 'content': 'private fixture'}], 'tools': []}
                 for name in ('envelope', *COMPONENTS)]
        entries = []
        for number, case in enumerate(cases, 10):
            path = folder / f'synthetic_{case["component"]}_private.json'
            path.write_text(json.dumps(case))
            entries.append({'component': case['component'], 'input_tokens': number,
                            'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        counts = {e['component']: e['input_tokens'] for e in entries}
        return expected, {**expected, 'cumulative_inputs': entries,
                          'ordered_token_increments': token_increments(counts)}, cases

    def test_valid_record_and_input_tampering_with_recomputed_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            expected, row, cases = self.fixture(folder)
            self.assertEqual(audit_row(expected, row, cases, folder, tokens=True)['inputs_reconstructed'], 11)
            path = folder / 'synthetic_task_private.json'
            modified = copy.deepcopy(cases[3]); modified['messages'][0]['content'] = 'altered'
            path.write_text(json.dumps(modified))
            row['cumulative_inputs'][3]['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'reconstruction'):
                audit_row(expected, row, cases, folder, tokens=True)

    def test_incomplete_reordered_or_changed_group_and_counts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            expected, row, cases = self.fixture(folder)
            changed = copy.deepcopy(row); changed['cumulative_inputs'].pop()
            with self.assertRaises(ValueError): audit_row(expected, changed, cases, folder, tokens=True)
            changed = copy.deepcopy(row); changed['cumulative_inputs'].reverse()
            with self.assertRaises(ValueError): audit_row(expected, changed, cases, folder, tokens=True)
            changed = copy.deepcopy(row); changed['outputs'] = []
            with self.assertRaises(ValueError): audit_row(expected, changed, cases, folder, tokens=True)
            changed = copy.deepcopy(row); changed['ordered_token_increments']['tools'] += 1
            with self.assertRaises(ValueError): audit_row(expected, changed, cases, folder, tokens=True)


if __name__ == '__main__':
    unittest.main()

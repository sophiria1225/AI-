import base64
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_browsecomp_grading import project_labels, terminal_inputs


def encrypt(text, canary='synthetic'):
    key = hashlib.sha256(canary.encode()).digest()
    return base64.b64encode(bytes(b ^ key[i % len(key)] for i, b in enumerate(text.encode()))).decode()


class GradingProjectionTests(unittest.TestCase):
    def test_incomplete_generation_is_rejected_before_opening_files(self):
        with self.assertRaises(ValueError):
            terminal_inputs({'status': 'running'}, Path('/nonexistent-never-opened'))

    def test_only_selected_answers_are_decrypted_and_question_identity_is_checked(self):
        rows = [{'query_id': 'ignored', 'query': 'intentionally-invalid-base64', 'answer': 'not-decoded'},
                {'query_id': '7', 'query': encrypt('Synthetic question'), 'answer': encrypt('blue')}]
        selected = {'7': {'question': 'Synthetic question', 'response': 'blue', 'run_id': 'P15_01_FULL'}}
        result, count = project_labels(rows, selected, 'synthetic')
        self.assertEqual(count, 2); self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['answer'], 'blue')
        selected['7']['question'] = 'Different question'
        with self.assertRaises(ValueError):
            project_labels(rows, selected, 'synthetic')


if __name__ == '__main__':
    unittest.main()

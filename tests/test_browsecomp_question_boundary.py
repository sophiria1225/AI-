import base64
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_browsecomp_questions import selected_questions


class QuestionProjectionControls(unittest.TestCase):
    def test_only_selected_questions_are_decrypted_and_no_labels_are_accepted(self):
        key='test-only-canary';plain='Synthetic question only'
        digest=hashlib.sha256(key.encode()).digest()
        cipher=base64.b64encode(bytes(b^digest[i%len(digest)] for i,b in enumerate(plain.encode()))).decode()
        rows=[{'query_id':'a','query':cipher},{'query_id':'b','query':'NOT_BASE64_UNSELECTED'}]
        self.assertEqual(selected_questions(rows,['a'],key),[{'query_id':'a','query':plain}])
        with self.assertRaises(ValueError):selected_questions([dict(rows[0],answer='SECRET')],['a'],key)
        with self.assertRaises(ValueError):selected_questions(rows,['missing'],key)
        with self.assertRaises(ValueError):selected_questions([rows[0],rows[0]],['a'],key)

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stateful_code_validation import validate
from run_native_batch import validate_schedule,public_body
ROOT=Path(__file__).resolve().parents[1]
class StatefulActivation(unittest.TestCase):
    def test_preparation_cannot_silently_start_or_change_cohort(self):
        p=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        validate_schedule(p)
        self.assertIn('P29',public_body([],{'phase':'P29','status':'waiting'}))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'configs').mkdir()
            (root/'configs/P28_code_clarification_v01.json').write_bytes((ROOT/'configs/P28_code_clarification_v01.json').read_bytes())
            with self.assertRaisesRegex(ValueError,'preparation only'):validate(p,root)
            for key,value in [('max_output_tokens',8192),('max_calls',90),('task_ids',p['task_ids'][:1])]:
                bad=copy.deepcopy(p);bad[key]=value
                with self.assertRaisesRegex(ValueError,'changed fixed'):validate(bad,root)
if __name__=='__main__':unittest.main()

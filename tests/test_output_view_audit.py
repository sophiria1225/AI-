import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_output_views import validate_cohort, validate_first_view


class OutputViewAuditTests(unittest.TestCase):
    def test_partial_or_duplicate_cohort_rejected(self):
        expected=[f'r{i}' for i in range(12)]
        good={'status':'complete','completed':expected[:],'rows':[{'run_id':r} for r in expected]}
        validate_cohort(good,expected)
        for key in ('completed','rows'):
            broken={**good,key:good[key][:-1]}
            with self.assertRaises(ValueError):validate_cohort(broken,expected)
        broken={**good,'completed':expected[:-1]+[expected[0]]}
        with self.assertRaises(ValueError):validate_cohort(broken,expected)

    def test_first_model_input_matches_what_was_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp);(trial/'call_001').mkdir()
            (trial/'usage.json').write_text(json.dumps([{'id':'call_001'}]))
            expected=[{'role':'system','content':'same'},{'role':'user','content':'same task'}]
            target=trial/'call_001/request.json';target.write_text(json.dumps({'messages':expected}))
            validate_first_view(trial,expected)
            changed=[{**expected[0],'content':'unrecorded extra instruction'},expected[1]]
            target.write_text(json.dumps({'messages':changed}))
            with self.assertRaises(ValueError):validate_first_view(trial,expected)


if __name__=='__main__':unittest.main()

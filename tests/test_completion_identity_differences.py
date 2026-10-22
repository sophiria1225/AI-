import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_completion_identity_differences import difference_paths, IDENTIFIER

class DifferenceTests(unittest.TestCase):
    def test_only_linkage_ids_are_classified_not_function_content(self):
        a={'messages':[{'tool_calls':[{'id':'first','function':{'name':'run_python','arguments':'{"code":"a"}'}}]},
                       {'tool_call_id':'first','content':'public response'}]}
        b=copy.deepcopy(a);b['messages'][0]['tool_calls'][0]['id']='second';b['messages'][1]['tool_call_id']='second'
        diff=difference_paths(a,b)
        self.assertEqual(len(diff),2);self.assertTrue(all(IDENTIFIER.fullmatch(p) for p in diff))
        b['messages'][0]['tool_calls'][0]['function']['arguments']='{"code":"changed"}'
        self.assertEqual(sum(not bool(IDENTIFIER.fullmatch(p)) for p in difference_paths(a,b)),1)

    def test_missing_key_and_type_difference_remain_non_identifier_differences(self):
        self.assertFalse(IDENTIFIER.fullmatch(difference_paths({'id':1},{'id':'1'})[0]))
        self.assertFalse(IDENTIFIER.fullmatch(difference_paths({'tool_calls':[{'id':'x'}]},{'tool_calls':[{}]})[0]))
        self.assertEqual(difference_paths({'a':1},{'a':1}),[])

if __name__=='__main__':unittest.main()

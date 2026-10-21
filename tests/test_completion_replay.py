import copy
import json
import unittest
from unittest.mock import patch

import replay_completion_format as replay


class CompletionReplayTests(unittest.TestCase):
    def test_only_completion_argument_changes_and_original_is_unchanged(self):
        message={'role':'assistant','tool_calls':[{'id':'c1','type':'function',
            'function':{'name':'supervisor__complete_task','arguments':'{"status":"success","answer":"recorded"}'}}]}
        original=copy.deepcopy(message)
        present=replay.change_completion(message,'answer_present','recorded')
        omitted=replay.change_completion(message,'answer_omitted','recorded')
        self.assertEqual(message,original)
        self.assertEqual(json.loads(present['tool_calls'][0]['function']['arguments']),{'status':'success','answer':'recorded'})
        self.assertEqual(json.loads(omitted['tool_calls'][0]['function']['arguments']),{'status':'success'})
        for changed in (present,omitted):
            changed['tool_calls'][0]['function']['arguments']=original['tool_calls'][0]['function']['arguments']
            self.assertEqual(changed,original)
        with self.assertRaises(ValueError): replay.change_completion(message,'try_another_answer','recorded')

    def test_any_prefix_mismatch_refuses_a_causal_comparison(self):
        row={'action':{'name':'a'},'observation':{'result':1},'api_request_sent':True,'new_tools':[]}
        event={'span_id':'s1','api_request_sent':True,'effects_unknown':False,'new_tools':[]}
        spans={'s1':{'action':row['action'],'observation':row['observation']}}
        replay.assert_rows_match([row],[event],spans)
        for key,value in [('observation',{'result':2}),('action',{'name':'b'}),
                          ('api_request_sent',False),('new_tools',['new']),('effects_unknown',True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                replay.assert_rows_match([{**row,key:value}],[event],spans)

    def test_no_world_replay_before_p25_complete(self):
        with patch.object(replay,'read',side_effect=[{}, {'status':'running'}]), \
             patch.object(replay,'verify_plan'), patch.object(replay,'replay_case') as execute:
            with self.assertRaisesRegex(ValueError,'wait for all P25'):
                replay.run(replay.Path('/unused'),replay.Path('/unused/plan'),replay.Path('/unused/report'))
            execute.assert_not_called()


if __name__=='__main__': unittest.main()

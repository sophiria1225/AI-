import copy
import json
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from handoff_factors import ARMS, handoff_conversation, replay_environment, split_turns
from native_conversation import NativeConversation


def conversation(turns=4):
    task={'instruction':'synthetic task'}
    c=NativeConversation('public system',task)
    for n in range(turns):
        calls=[{'id':f't{n}-{i}','type':'function','function':{'name':'run_python','arguments':'{}'}} for i in range(2)]
        c.append({'role':'assistant','content':f'public {n}','tool_calls':calls},
                 [{'id':f's{n}-{i}','assistant':'','action':call['function'],
                   'observation':{'status':'ok','value':n}} for i,call in enumerate(calls)])
    return task,c


def replay_fixture():
    events=[{'stage':'python_api','api_request_sent':sent,'span_id':f's{i}',
             'new_tools':[]} for i,sent in enumerate([True,False,True])]
    prefix={'events':events,'spans':{e['span_id']:{'action':{'name':'x','arguments':'{}'},
             'observation':{'observation':str(i)}} for i,e in enumerate(events)},
             'manifest':{'state':{'visible_api_schemas':['x']},'files':{'dbs/a':{'sha256':'hash'}}}}
    catalog=Mock();catalog.visible={'x'};catalog.decode.return_value={'app':'x','api':'f','args':{}}
    catalog.expose_requested_document.return_value=[]
    bridge=Mock();bridge.request.side_effect=[{'ok':True,'result':{'observation':'0'}},
                                              {'ok':True,'result':{'observation':'2'}}]
    return prefix,catalog,bridge



class HandoffFactorTests(unittest.TestCase):
    def test_later_boundary_requires_eight_complete_turns(self):
        task,c=conversation(8)
        full,meta=handoff_conversation(c.messages(),task,'full_keep',8)
        recent,_=handoff_conversation(c.messages(),task,'recent_keep',8)
        self.assertEqual(len(split_turns(full.messages())),8)
        self.assertEqual(len(split_turns(recent.messages())),1)
        self.assertEqual(recent.messages()[2:],c.messages()[-3:])
        self.assertEqual(meta['source_turns'],8)
        for boundary in (4,7,9):
            with self.assertRaises(ValueError):
                handoff_conversation(c.messages(),task,'full_keep',boundary)

    def test_history_removal_preserves_complete_multi_call_turn_and_task(self):
        task,c=conversation();original=c.messages()
        recent,meta=handoff_conversation(original,task,'recent_keep')
        full,_=handoff_conversation(original,task,'full_keep')
        assert len(split_turns(recent.messages()))==1
        assert len(split_turns(full.messages()))==4
        assert recent.messages()[1]==original[1]
        assert recent.messages()[2:]==original[-3:]
        assert meta['all_public_receipts_still_accessible']
        assert c.messages()==original

    def test_only_runtime_notice_differs_for_fixed_history_factor(self):
        task,c=conversation()
        keep,_=handoff_conversation(c.messages(),task,'recent_keep')
        reset,_=handoff_conversation(c.messages(),task,'recent_reset')
        assert keep.messages()[1:]==reset.messages()[1:]
        assert 'retained' in keep.messages()[0]['content']
        assert 'restarted once' in reset.messages()[0]['content']
        assert 'Subsequent run_python calls share' in reset.messages()[0]['content']

    def test_handoff_rejects_orphaned_or_wrong_boundary_without_repair(self):
        task,c=conversation();messages=c.messages()
        with self.assertRaises(ValueError): split_turns(messages[:-1])
        with self.assertRaises(ValueError): handoff_conversation(messages[:-3],task,'full_keep')
        with self.assertRaises(ValueError): handoff_conversation(messages,{'instruction':'different'},'full_keep')
        with self.assertRaises(ValueError): handoff_conversation(messages,task,'other')

    def test_recent_condition_accepts_later_turn_without_reapplying_window(self):
        task,c=conversation();after,_=handoff_conversation(c.messages(),task,'recent_reset')
        after.append({'role':'assistant','content':'later'},[
            {'id':'new','assistant':'later','action':None,'observation':{'format_error':'no call'}}])
        rendered,stats=after.for_model()
        assert len(split_turns(after.messages()))==2
        assert rendered[-2]['content']=='later'

    def test_environment_replays_only_dispatched_calls_and_checks_db(self):
        prefix,catalog,bridge=replay_fixture()
        with patch('probe_prefix_replay.db_hashes',return_value={'dbs/a':'hash'}):
            result=replay_environment(prefix,catalog,bridge,Path('unused'),deadline=10,clock=lambda:0)
        assert bridge.request.call_count==2
        assert result['api_requests']==2 and result['db_files_match']

    def test_environment_mismatch_stops_before_next_effect(self):
        prefix,catalog,bridge=replay_fixture()
        bridge.request.side_effect=[{'ok':True,'result':{'observation':'wrong'}}]
        with self.assertRaisesRegex(ValueError, 'observation'):
            replay_environment(prefix,catalog,bridge,Path('unused'),deadline=10,clock=lambda:0)
        assert bridge.request.call_count==1

    def test_environment_saved_db_and_discovery_must_both_match(self):
        prefix,catalog,bridge=replay_fixture()
        with patch('probe_prefix_replay.db_hashes',return_value={'dbs/a':'different'}):
            with self.assertRaisesRegex(ValueError, 'DB'):
                replay_environment(prefix,catalog,bridge,Path('unused'),deadline=10,clock=lambda:0)
        prefix,catalog,bridge=replay_fixture();catalog.visible={'x','extra'}
        with patch('probe_prefix_replay.db_hashes',return_value={'dbs/a':'hash'}):
            with self.assertRaisesRegex(ValueError, 'schema'):
                replay_environment(prefix,catalog,bridge,Path('unused'),deadline=10,clock=lambda:0)

    def test_setup_deadline_prevents_further_dispatch(self):
        prefix,catalog,bridge=replay_fixture()
        with self.assertRaises(TimeoutError):
            replay_environment(prefix,catalog,bridge,Path('unused'),deadline=10,clock=lambda:10)
        bridge.request.assert_not_called()

    def test_failed_setup_charges_attempt_with_unknown_effect_and_never_retries(self):
        prefix,catalog,bridge=replay_fixture();account={}
        bridge.request.side_effect=TimeoutError('after possible write')
        with self.assertRaises(TimeoutError):
            replay_environment(prefix,catalog,bridge,Path('unused'),deadline=10,
                               clock=lambda:0,accounting=account)
        self.assertEqual(account['api_requests'],1)
        self.assertEqual(account['unknown_effect_requests'],1)
        self.assertEqual(account['observation_matches'],0)
        self.assertEqual(bridge.request.call_count,1)

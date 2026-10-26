"""Independent handwritten P134 boundary cases; no actual trials or model APIs."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from test_public_output_grounding import TASK
from partitioned_export_monitor import PartitionedExportMonitor
from observed_field_obligations import ObservedFieldObligations, CheckpointDisclosure, capture
from observed_obligation_runtime import ObservedObligationRuntime
from observed_obligation_execution import execute_obligation_response

def monitor(*,scope='synthetic-scope',ids=(1,2)):
    m=PartitionedExportMonitor(deepcopy(TASK),execution_scope=scope)
    for kind in ('song','album'):
        m._page(kind,{'page_index':0,'page_limit':20},[])
    m._page('playlist',{'page_index':0,'page_limit':20,'is_public':False},[
        {'playlist_id':1,'song_ids':list(ids),'is_public':False}])
    m._page('playlist',{'page_index':0,'page_limit':20,'is_public':True},[])
    return m

def store(m):
    # Exact trusted class with handwritten monitor state; production constructor
    # public-source verification is reviewed separately, not bypassed in live code.
    st=object.__new__(ObservedFieldObligations)
    st.monitor=m;st.query_counts={'snapshot':0,'page':0,'stale':0}
    return st

def arguments(op='snapshot',handle=None,cursor=0,limit=16):
    return dict(op=op,handle=handle,cursor=cursor,limit=limit)

class BoundaryTests(unittest.TestCase):
    def runtime(self,m):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        out=Path(temp.name)
        with patch('observed_obligation_runtime.ObservedFieldObligations',return_value=store(m)):
            runtime=ObservedObligationRuntime(TASK,out,execution_scope='synthetic-scope',public_source_directory=out)
        return runtime,out

    def over_bound(self):
        m=monitor(ids=tuple(range(1,513)))
        # A second complete partition contributes one additional source ID.
        m.playlist_partition_pages[True]={20:{0:[(2,(513,))]}}
        return m

    def test_contract_overflow_is_sticky_not_caller_feedback(self):
        runtime,_=self.runtime(self.over_bound())
        with self.assertRaisesRegex(RuntimeError,'obligation_query_contract_failed'):
            runtime.query(arguments(),call_id='call_001',tool_index=1)
        self.assertTrue(runtime.failed)
        self.assertEqual(runtime.queries[0]['status'],'failed')
        self.assertEqual(runtime.summary()['query_rejections'],0)

    def test_bad_cursor_is_recoverable(self):
        runtime,_=self.runtime(monitor())
        first=runtime.query(arguments(),call_id='call_001',tool_index=1)
        bad=runtime.query(arguments('page',first['snapshot']['handle'],99),call_id='call_001',tool_index=2)
        self.assertEqual(bad['status'],'invalid_obligation_query');self.assertFalse(runtime.failed)
        good=runtime.query(arguments('page',first['snapshot']['handle']),call_id='call_001',tool_index=3)
        self.assertEqual([r['song_id']for r in good['rows']],[1,2])

    def test_core_failure_stops_later_same_response_program(self):
        runtime,out=self.runtime(self.over_bound());called=[];recorded=[]
        message={'tool_calls':[
            {'function':{'name':'read_obligations','arguments':json.dumps(arguments())}},
            {'function':{'name':'run_python','arguments':json.dumps({'code':'pass','span_ids':[]})}}]}
        def forbidden_program(*a,**kw):called.append(1);raise AssertionError('must never execute')
        with self.assertRaisesRegex(RuntimeError,'obligation_query_contract_failed'):
            execute_obligation_response(message,None,None,[],recorded.append,
                out=out,storage=out,call_id='call_001',remaining_api=lambda:80,
                may_continue=lambda:True,remaining_wall=lambda:60,read_archive=lambda *a:None,
                program=forbidden_program,obligation_runtime=runtime)
        self.assertEqual(called,[]);self.assertEqual(recorded,[])

    def test_handle_does_not_cross_execution_or_requirement(self):
        first=store(monitor());handle=first.capture()['sha256']
        second=store(monitor(scope='different-execution'))
        answer=second.query(**arguments('page',handle))
        self.assertEqual(answer['status'],'stale_snapshot');self.assertEqual(answer['rows'],[])
        third=store(monitor());third.monitor.requirement_sha256='a'*64
        self.assertEqual(third.query(**arguments('page',handle))['status'],'stale_snapshot')

    def test_unknown_does_not_turn_old_handle_into_empty_completion(self):
        m=monitor();s=store(m);old=s.capture()['sha256'];m.taints.add('unknown_or_untyped_API_effect')
        stale=s.query(**arguments('page',old));fresh=s.query(**arguments('page',stale['snapshot']['handle']))
        self.assertEqual(stale['status'],'stale_snapshot');self.assertEqual(fresh['status'],'unknown')
        self.assertIsNone(fresh['total']);self.assertFalse(fresh['complete_page'])
        self.assertIsNone(fresh['snapshot']['counts'])

    def test_raw_and_main_arms_capture_same_state_but_actor_only_notice(self):
        original=[{'role':'system','content':'common'},{'role':'user','content':'synthetic'}]
        packets=[];views=[]
        for mode in ('raw_anchor','counts_only','entity_fields'):
            c=CheckpointDisclosure(mode);packets.append(c.prepare(store(monitor()),1,accepted=True))
            views.append(c.actor_view(original));self.assertEqual(c.captures,1)
            c.model_submitted(attempted=True);self.assertEqual(c.actor_view(original),original)
        self.assertEqual(packets[0],packets[1]);self.assertEqual(packets[1],packets[2])
        self.assertEqual(views[0],original);self.assertEqual(original[0]['content'],'common')
        self.assertNotEqual(views[1],views[2]);self.assertEqual(views[1][1:],views[2][1:])

    def test_evidence_change_after_count_cannot_silently_change_send(self):
        m=monitor();st=store(m);c=CheckpointDisclosure('entity_fields')
        c.prepare(st,1,accepted=True);messages=[{'role':'system','content':'common'}]
        c.actor_view(messages)
        m._song({'song_id':1,'title':'observed','artists':[{'id':9,'name':'artist'}]},1)
        with self.assertRaisesRegex(ValueError,'capture_boundary_changed_before_actor'):
            c.actor_view(messages)
        self.assertIsNotNone(c.pending)

    def test_single_huge_dependency_row_is_contract_failure(self):
        m=monitor(ids=(1,));m._song({'id':1,'title':'observed','artist_ids':[10**40+n for n in range(512)]},partial=True)
        runtime,_=self.runtime(m);handle=runtime.store.capture()['sha256']
        with self.assertRaisesRegex(RuntimeError,'obligation_query_contract_failed'):
            runtime.query(arguments('page',handle),call_id='call_001',tool_index=1)
        self.assertTrue(runtime.failed)

if __name__=='__main__':unittest.main(verbosity=2)

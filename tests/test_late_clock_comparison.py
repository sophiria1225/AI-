import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from late_clock_comparison import (REQUIRED_SOURCES,cell_id,config_for,initial_conversation,
    run_order,summarize,validate_plan)
from protocol_stable_history import StableReferenceConversation
from stable_clock_observation import POLICIES,StableClockInference
from budget_signal import digest
from local_llama import payload_for
from public_display import CODE_TOOLS
import audit_late_clock_comparison as auditor
import run_late_clock_cell as worker
import test_budget_visibility_worker as external_fixture

ROOT=Path(__file__).resolve().parents[1]


def plan():
    value=json.loads((ROOT/'configs/P80_budget_visibility_v01.json').read_text())
    value.update(experiment='P82',batch_id='P82_batch_v01',time_policies=list(POLICIES),
        repetitions=[1,2],remaining_time_fraction=[1,2],max_cells=24,max_model_calls=1920,
        max_reserved_tokens=10800000,server_max_lifetime_seconds=64800,fresh_seed_search=False,
        threshold_search=False,new_task_requirements_read=0,
        protocol_references='source_protocol_fields_before_rendering',
        primary_question='late_time_observation_whole_task_cost_and_quality',
        prior_cohort='reports/P80_comparison.json',required_closed_cohort='reports/P81_repetitions.json')
    value['source_sha256'].update({name:'0'*64 for name in REQUIRED_SOURCES})
    return value


def rows():
    return [{'run_id':cell_id(rep,n,p),'repetition':rep,'task_id':str(n),'time_visibility':p,
        'record_status':'evaluated','success':True,'unknown_usage_calls':0,'known_total_tokens':cost}
        for rep in (1,2) for n in range(1,5)
        for p,cost in zip(POLICIES,(100,90,80))]


def fixture(**kwargs):
    with patch.dict(sys.modules,{'run_budget_visibility_cell':worker}),\
         patch.object(external_fixture,'run_cell',worker.run_cell):
        return external_fixture.fixture(**kwargs)


def audit_fixture(folder,result,policy):
    trial=Path(folder)/'records/context_pilot/BOC_P80_fixture'
    read=lambda name:json.loads((trial/(name+'.json')).read_text())
    config,comparison,public=read('plan'),read('comparison_plan'),read('public_task')
    original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    base,_=initial_conversation(original,public).for_model(config['observation_page_characters'])
    for i,capture in enumerate(result['captured'],1):
        call=trial/f'call_{i:03d}'
        (call/'request.json').write_text(json.dumps(payload_for(capture['cfg'],capture['messages'],CODE_TOOLS)))
        response=call/'response.json'
        if response.exists():(call/'raw_response.json').write_text(response.read_text())
    with patch.object(auditor,'config_for',return_value=config),\
         patch.object(auditor,'parse_response',side_effect=lambda x:x):
        return auditor.audit_cell(trial,ROOT,comparison,original,{'task_id':'fixture','public_task':public},
            policy,{'base_messages_sha256':digest(base)},False)


class LateClockComparisonTests(unittest.TestCase):
    def test_all_three_controls_are_new_and_order_reverses_per_task(self):
        order=run_order();self.assertEqual(len(order),24)
        self.assertEqual(len({cell_id(*v) for v in order}),24)
        for n in range(1,5):
            a=[p for rep,k,p in order if rep==1 and k==n]
            b=[p for rep,k,p in order if rep==2 and k==n]
            self.assertEqual(set(a),set(POLICIES));self.assertEqual(a,b[::-1])
        for rep,n,p in [(True,1,'measured'),(3,1,'measured'),(1,5,'measured'),(1,1,'other')]:
            with self.assertRaises(ValueError):cell_id(rep,n,p)

    def test_fixed_scope_requires_closed_dependencies_and_finite_whole_cohort(self):
        p=plan();validate_plan(p)
        total=sum(p[k] for k in ('max_setup_seconds','max_wall_seconds','max_cleanup_seconds',
            'max_idle_wait_seconds','max_evaluation_seconds'))*p['max_cells']
        self.assertLess(total+1200,p['server_max_lifetime_seconds'])
        for key,value in [('max_cells',16),('threshold_search',True),('model_seed',58),
            ('remaining_time_fraction',[1,3]),('time_policies',['measured','late_half']),
            ('protocol_references','canonical_in_both_before_counting')]:
            with self.assertRaises(ValueError):validate_plan({**p,key:value})
        for name in REQUIRED_SOURCES:
            bad=copy.deepcopy(p);bad['source_sha256'].pop(name)
            with self.assertRaises(ValueError):validate_plan(bad)

    def test_each_baseline_must_be_beaten_in_both_repetitions(self):
        result=summarize(rows(),[]);self.assertTrue(result['all_repetition_gates_met'])
        self.assertEqual(len(result['repetitions']),2)
        bad=rows()
        for r in bad:
            if r['time_visibility']=='late_half' and r['repetition']==2:r['known_total_tokens']=95
        result=summarize(bad,[]);self.assertFalse(result['all_repetition_gates_met'])
        comparisons=result['repetitions'][1]['comparisons']
        self.assertTrue(comparisons[0]['development_gate_met'])
        self.assertFalse(comparisons[1]['development_gate_met'])

    def test_missing_usage_loss_all_failure_and_errors_cannot_pass(self):
        for kind in ('unknown','unevaluated','loss','all_failed','audit'):
            bad=rows();errors=[]
            if kind=='unknown':bad[1]['unknown_usage_calls']=1
            if kind=='unevaluated':bad[1].update(record_status='not_run',success=None)
            if kind=='loss':bad[2]['success']=False
            if kind=='all_failed':
                for r in bad:r['success']=False
            if kind=='audit':errors=['synthetic discrepancy']
            result=summarize(bad,errors)
            self.assertFalse(result['all_repetition_gates_met'])
            if kind in ('unknown','unevaluated'):
                self.assertFalse(result['all_twenty_four_complete_with_known_usage'])
        for bad in (rows()[:-1],rows()[:-1]+[rows()[0]]):
            with self.assertRaises(ValueError):summarize(bad,[])

    def test_failure_cost_and_successful_task_cost_remain_separate(self):
        data=rows()
        for r in data:
            if r['task_id']=='4':r['success']=False
        result=summarize(data,[])
        comparison=result['repetitions'][0]['comparisons'][0]
        self.assertEqual(comparison['paired_successful_token_difference'],-60)
        self.assertEqual(comparison['both_failed_token_difference'],-20)

    def test_real_worker_switches_only_late_control_and_accounts_all_calls(self):
        for policy,sequence in [('measured',['measured']*3),('not_exposed',['not_exposed']*3),
            ('late_half',['not_exposed','not_exposed','measured'])]:
            with tempfile.TemporaryDirectory() as folder:
                r=fixture(folder=folder,policy=policy,actions=('echo','echo','finish'),response_delay=16)
                self.assertEqual(r['result']['phase'],'P82')
                self.assertEqual(r['result']['stop_reason'],'agent_declared_complete')
                self.assertEqual(r['result']['known_total_tokens'],150)
                self.assertEqual(r['result']['api_requests'],3)
                self.assertEqual([s['effective_time_visibility'] for s in r['saved']['budget_observations']],sequence)
                audit=audit_fixture(folder,r,policy)
                self.assertEqual(audit['known_total_tokens'],150)
                p=Path(folder)/'records/context_pilot/BOC_P80_fixture/budget_observations.json'
                signals=json.loads(p.read_text());signals[-1]['effective_time_visibility']='wrong'
                p.write_text(json.dumps(signals))
                with self.assertRaisesRegex(ValueError,'effective_time_policy'):
                    audit_fixture(folder,r,policy)

    def test_unknown_dispatch_and_expired_response_keep_cost_and_do_not_retry(self):
        for actions,delay,known,unknown,api in [(('echo','transport_error'),0,50,1,1),(('echo','finish'),61,50,0,0)]:
            with tempfile.TemporaryDirectory() as folder:
                result=fixture(folder=folder,policy='late_half',actions=actions,response_delay=delay)
                audit=audit_fixture(folder,result,'late_half')
                self.assertEqual(audit['known_total_tokens'],known)
                self.assertEqual(audit['unknown_usage_calls'],unknown)
                self.assertEqual(audit['api_requests'],api)

    def test_source_mismatch_stops_before_counting_or_generation(self):
        p=plan();original=json.loads((ROOT/p['source_plan']).read_text())
        cfg=config_for(original,p,p['known_tasks'][0]['task_id'],'late_half')
        c=StableReferenceConversation('system',{})
        with tempfile.TemporaryDirectory() as folder:
            r=StableClockInference(cfg,Path(folder),conversation=c,time_visibility='late_half')
            with patch('residual_output_budget.count_input') as count,patch('residual_output_budget.model_call') as send:
                with self.assertRaisesRegex(ValueError,'supplied_history'):
                    r.call('agent',[{'role':'user','content':'unbound input'}],[])
                count.assert_not_called();send.assert_not_called()


if __name__=='__main__':unittest.main()

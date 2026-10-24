from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'tests'))
from public_only_history_worker_fixture import fixture, audit_fixture, auditor
from receipt_history_worker_fixture import fixture as original_fixture
from receipt_reasoning_history import strip_reasoning
from whole_task_public_only_history import (
    HISTORICAL_POLICIES, cell_id, run_order, summarize, token_bounds, validate_plan,
)
import run_whole_task_public_only_history as runner
from budget_observation import notification
from api_error_comparison import task_snapshot
from tool_choice_local_llama import payload_for
from public_display import CODE_TOOLS
from budget_signal import digest
from residual_output_budget import admission
from run_context_comparison import write_json


def fixture_plan():
    p = json.loads((ROOT/'configs/P111_whole_task_receipt_history_v01.json').read_text())
    p.update(experiment='P114', batch_id='P114_batch_v01', reasoning_display_policies=['public_only'],
        max_cells=4, max_model_calls=320, max_reserved_tokens=1800000,
        max_reserved_environment_api_requests=400, server_max_lifetime_seconds=14400,
        primary_question='public_only_from_start_ordinary_control_calibration',
        required_closed_diagnostic='reports/P113_receipt_history_trajectories.json',
        required_predecessor_phase='P111', historical_reference_phase='P111',
        contemporaneous_comparison=False, remove_latest_reasoning=True, selection_uses_receipt_eligibility=False)
    for name in ('scripts/public_only_reasoning_history.py', 'reports/P111_comparison.json',
                 'reports/P111_server_session.json', 'reports/P111_initial_checks.json',
                 'configs/P111_whole_task_receipt_history_v01.json',
                 'reports/P113_receipt_history_trajectories.json',
                 'docs/experiments/P114_whole_task_public_only_history.md'):
        p['source_sha256'][name] = '0'*64
    return p


def synthetic_rows():
    def row(n,p,cost):
        return dict(task_id=str(n), reasoning_display_policy=p, record_status='evaluated',
                    success=True, known_total_tokens=cost, unknown_usage_calls=0)
    return ([row(n,'public_only',80) for n in range(1,5)],
            [row(n,p,100) for n in range(1,5) for p in HISTORICAL_POLICIES])


class PublicOnlyHistoryTests(unittest.TestCase):
    def test_latest_and_failed_reasoning_are_omitted_but_archive_is_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(actions=('echo','fail','echo','finish'),folder=folder)
            checked=audit_fixture(folder,result,'public_only')
            self.assertEqual(checked['model_calls'],4)
            self.assertEqual(checked['invocation_exceptions'],1)
            for n,c in enumerate(result['captured']):
                assistants=[m for m in c['messages'] if m['role']=='assistant']
                self.assertEqual(len(assistants),n)
                self.assertTrue(all('reasoning_content' not in m for m in assistants))
                self.assertEqual(result['saved']['reasoning_history_views'][n]['projection']['removed_reasoning_turns'],list(range(1,n+1)))
            archive=result['saved']['conversation_private']
            self.assertEqual(sum(m.get('reasoning_content')=='synthetic test text' for m in archive),4)
            self.assertEqual(result['result']['reasoning_display']['projections_redisplaying_reasoning'],0)

    def test_public_content_first_request_and_counted_messages_match_frozen_worker(self):
        new=fixture(actions=('echo','echo','finish'))
        old=original_fixture(policy='full',actions=('echo','echo','finish'))
        self.assertEqual(new['captured'][0],old['captured'][0])
        for a,b in zip(new['captured'],old['captured'],strict=True):
            self.assertEqual(a['messages'],strip_reasoning(b['messages']))
            self.assertEqual(a['cfg'],b['cfg'])
        self.assertEqual(new['counted'],[c['messages'] for c in new['captured']])

    def test_unknown_usage_retained_and_response_not_executed_or_retried(self):
        for action in ('unknown','transport_error'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as folder:
                result=fixture(actions=('echo',action),folder=folder)
                checked=audit_fixture(folder,result,'public_only')
                self.assertEqual(checked['unknown_usage_calls'],1)
                self.assertEqual(checked['known_total_tokens'],50)
                self.assertEqual(result['programs'],['echo'])
                self.assertEqual(len(result['saved']['reasoning_execution_records']),1)

    def test_terminal_unattempted_projection_is_audited_without_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(token_limit=50,folder=folder)
            checked=audit_fixture(folder,result,'public_only')
            self.assertEqual(checked['model_calls'],1)
            self.assertEqual(checked['known_total_tokens'],50)
            self.assertEqual(len(result['saved']['reasoning_history_views']),2)
            self.assertFalse(result['saved']['budget_observations'][-1]['model_attempted'])

    def test_tampered_public_or_reasoning_input_is_detected(self):
        for field,value in [('reasoning_content','injected'),('content','changed public text')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as folder:
                result=fixture(actions=('echo','echo','finish'),folder=folder)
                audit_fixture(folder,result,'public_only')
                trial=Path(folder)/'records/context_pilot/BOC_P114_fixture'
                path=trial/'call_003/request.json';request=json.loads(path.read_text())
                next(m for m in request['messages'] if m['role']=='assistant')[field]=value
                path.write_text(json.dumps(request))
                cfg=json.loads((trial/'plan.json').read_text());plan=json.loads((trial/'comparison_plan.json').read_text())
                public=json.loads((trial/'public_task.json').read_text())
                original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
                base,_=runner.initial_conversation(original,public).for_model(cfg['observation_page_characters'])
                with patch.object(auditor,'config_for',return_value=cfg),patch.object(auditor,'parse_response',side_effect=lambda x:x):
                    with self.assertRaisesRegex(ValueError,'actual_request_differs'):
                        auditor.audit_cell(trial,ROOT,plan,original,{'task_id':'fixture','public_task':public},'public_only',{'base_messages_sha256':digest(base)},False)

    def test_api_uncertainty_cleanup_and_cache_failures_stop_batch(self):
        from api_error_comparison import disposition
        for options in ({'unknown_api':True},{'cleanup_ok':False},{'first_cached':1}):
            self.assertEqual(disposition(fixture(**options)['result']),'stop_batch')

    def test_user_stop_prevents_next_generation(self):
        result=fixture(stop_after_api=True)
        self.assertEqual(result['result']['stop_reason'],'user_stop')
        self.assertEqual(len(result['captured']),1)


class PublicOnlyPlanTests(unittest.TestCase):
    def test_scope_has_exactly_four_new_controls_and_finite_unchanged_per_task_budget(self):
        validate_plan(fixture_plan())
        self.assertEqual(run_order(),[(n,'public_only') for n in range(1,5)])
        self.assertEqual(len({cell_id(n,p) for n,p in run_order()}),4)
        for key,value in [('max_calls',81),('server_max_lifetime_seconds',14401),('reasoning_budget_tokens',2048),
                          ('remove_latest_reasoning',False),('contemporaneous_comparison',True),
                          ('selection_uses_receipt_eligibility',True),('read_views_enabled',True)]:
            plan=fixture_plan();plan[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_plan(plan)

    def test_all_historical_rows_retained_and_descriptive_criterion_is_not_adoption(self):
        new,old=synthetic_rows();out=summarize(new,[],old)
        self.assertTrue(all(c['descriptive_cost_quality_criterion_met'] for c in out['comparisons']))
        self.assertFalse(out['development_gate_met']);self.assertFalse(out['contemporaneous_comparison'])
        self.assertEqual(out['historical_reference_rows'],12)
        with self.assertRaises(ValueError):summarize(new[:-1],[],old)
        with self.assertRaises(ValueError):summarize(new,[],old[:-1])

    def test_unknowns_have_only_valid_nonnegative_bounds_and_absent_slots_have_none(self):
        new,old=synthetic_rows();new[0]['unknown_usage_calls']=1
        first=summarize(new,[],old)['comparisons'][0]
        self.assertEqual(first['public_only_minus_historical_tokens'],{'exact':None,'lower':-80,'upper':None})
        self.assertFalse(first['descriptive_cost_quality_criterion_met'])
        new,old=synthetic_rows();old[0]['unknown_usage_calls']=1
        first=summarize(new,[],old)['comparisons'][0]
        self.assertEqual(first['public_only_minus_historical_tokens'],{'exact':None,'lower':None,'upper':-80})
        new[0].update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        self.assertEqual(token_bounds(new),dict(lower=None,upper=None,exact=None))

    def test_cheap_failure_audit_error_and_lost_success_prevent_descriptive_criterion(self):
        new,old=synthetic_rows()
        for r in new+old:
            r['known_total_tokens']=100
            if r['task_id']=='4':
                r['success']=False;r['known_total_tokens']=1 if r in new else 10000
        self.assertTrue(all(not c['descriptive_cost_quality_criterion_met'] for c in summarize(new,[],old)['comparisons']))
        new,old=synthetic_rows();new[0]['success']=False
        self.assertTrue(all(not c['descriptive_cost_quality_criterion_met'] for c in summarize(new,[],old)['comparisons']))
        new,old=synthetic_rows()
        self.assertTrue(all(not c['descriptive_cost_quality_criterion_met'] for c in summarize(new,[{'error':'fixture'}],old)['comparisons']))

    def run_preflight(self, change=None):
        plan=fixture_plan();original=json.loads((ROOT/plan['source_plan']).read_text())
        items=[dict(t,public_task={'instruction':'synthetic task','ground_truth_loaded':False}) for t in plan['known_tasks']]
        identity=dict(model_revision='synthetic',runtime={'commit':'synthetic'},ctx_size=65536,pid=20)
        calls=[]
        def count(*args,**kwargs):
            calls.append(1)
            return dict(input_tokens=101 if change=='count' else 100,wall_seconds=0,method='synthetic')
        with tempfile.TemporaryDirectory() as folder:
            storage=Path(folder)/'storage';root=Path(folder)/'repo';(root/'reports').mkdir(parents=True)
            historical=dict(status='complete',all_twelve_inputs_checked=True,input_count_requests=12,
                failed_input_count_requests=0,model_identity={**identity,'pid':10},rows=[])
            for item in items:
                base,_=runner.initial_conversation(original,item['public_task']).for_model()
                cfg=runner.config_for(original,plan,item['task_id'],'public_only')
                state=task_snapshot(cfg,[],0,0);supplied,visible=notification(base,state,'not_exposed')
                model={**cfg['model'],'temperature':original['agent_temperature'],'seed':plan['model_seed'],
                    'num_predict':original['max_output_tokens'],'cache_prompt':False}
                request=payload_for(model,supplied,CODE_TOOLS)
                if change=='request':request['seed']+=1
                conditions={}
                for policy in HISTORICAL_POLICIES:
                    path=storage/'records/context_pilot/P111_preflight_v01'/(item['source_run']+'_'+policy+'_request_private.json')
                    path.parent.mkdir(parents=True,exist_ok=True)
                    write_json(path,request)
                    conditions[policy]=dict(base_messages_sha256=digest(base),model_messages_sha256=digest(supplied),
                        measured_state=state,visible_state=visible,input_tokens=100,
                        admission=admission(450000,100,4096,65536,'residual'),reasoning_budget_tokens=-1,
                        tool_choice='auto',count_request_sha256=runner.sha(path))
                    if change=='archive':path.write_text('{}')
                historical['rows'].append(dict(task_id=item['task_id'],source_run=item['source_run'],conditions=conditions))
            if change=='runtime':historical['model_identity']['runtime']={'commit':'different'}
            write_json(root/'reports/P111_initial_checks.json',historical)
            with patch.object(runner,'sources',return_value=(plan,original,[],items)), \
                 patch.object(runner,'frozen_hashes',return_value={'synthetic':'bound'}), \
                 patch.object(runner,'frozen_sources',return_value='synthetic-head'), \
                 patch.object(runner,'live_identity',return_value=(identity,'lease-end')), \
                 patch.object(runner,'check_resume',return_value={'synthetic':True}), \
                 patch.object(runner,'count_input',side_effect=count):
                if change:
                    with self.assertRaises(ValueError):runner.preflight(storage,root)
                else:runner.preflight(storage,root)
            result=json.loads((root/runner.PREFLIGHT).read_text())
        return result,len(calls)

    def test_preflight_matches_twelve_historical_requests_and_counts_with_four_new_counts(self):
        result,calls=self.run_preflight()
        self.assertEqual(calls,4);self.assertTrue(result['all_four_inputs_checked_against_P111'])
        self.assertTrue(all(r['historical_initial_check']['exact_requests_and_counts_match'] for r in result['rows']))
        self.assertEqual(result['model_generations'],0)

    def test_historical_request_count_runtime_or_archive_mismatch_stops_before_generation(self):
        for change in ('request','count','runtime','archive'):
            with self.subTest(change=change):
                result,calls=self.run_preflight(change)
                self.assertEqual(calls,1);self.assertEqual(result['status'],'failed')
                self.assertFalse(result['all_four_inputs_checked_against_P111'])
                self.assertEqual(result['model_generations'],0)


if __name__=='__main__':unittest.main()

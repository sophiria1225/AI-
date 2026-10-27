"""P142 handwritten accounting, closed-publication and evaluator-binding boundaries.

Fixtures are synthetic metadata, not real model/world/evaluator executions.
"""
from contextlib import ExitStack
from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import whole_task_threshold_object_p142 as study
from test_checkpoint_prefix_identity_p140 import fixture as identity_fixture

BUILDER = 'scripts/build_p142_results.py'


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows():
    result=[]
    for number, mode in study.run_order():
        prefix=identity_fixture('control' if mode==study.MODES[0] else 'candidate')[2]
        result.append(dict(run_id=study.cell_id(number,mode), task_id=study.TASKS[number-1],
            object_timing_mode=mode, checkpoint_representation_mode=mode, model_seed=157,
            record_status='evaluated',success=True,known_total_tokens=1000 if mode==study.MODES[0] else 900,
            unknown_usage_calls=0,request_checks=[],**prefix,
            prefix_exposure_contract_failed=False,prefix_exposure_accounting_complete=True,
            checkpoint_representation_contract_failed=False,checkpoint_representation_accounting_complete=True,
            delta_envelope_contract_failed=False,delta_envelope_accounting_complete=True,
            object_prompt_known_focus_calls=int(mode==study.MODES[1]),
            actual_delta_known_actor_calls=int(mode==study.MODES[1])))
    return result


def plan():
    return dict(study.fixed_fields(),known_tasks=[dict(task_id=t,source_run=f'P29_{n:02d}_CODE')
        for n,t in enumerate(study.TASKS,1)],source_sha256={name:'a'*64 for name in study.REQUIRED_SOURCES})


def closed_fixture(root, data, errors=()):
    for name in study.REQUIRED_SOURCES:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((ROOT/name).read_bytes() if name==BUILDER else b'handwritten fixture source\n')
    p=plan();p['source_sha256']={name:sha(root/name) for name in study.REQUIRED_SOURCES}
    put(root/study.PLAN,p)
    audit=dict(phase='P142',batch_status='stopped',owned_processes_absent=True,
        rows=data,audit_errors=list(errors),plan_sha256=sha(root/study.PLAN),**study.summarize(data,list(errors)))
    put(root/'reports/P142_comparison.json',audit)
    put(root/'reports/P142_server_session.json',dict(phase='P142',status='stopped',
        owned_processes_absent=True,audit_source_sha256=sha(root/'reports/P142_comparison.json')))
    spec=importlib.util.spec_from_file_location('synthetic_P142_builder',root/BUILDER)
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    return builder


class ThresholdObjectReportingTests(unittest.TestCase):
    def test_all_four_pairs_known_and_separate_strict_canonical(self):
        result=study.summarize(rows(),[])
        self.assertEqual(result['planned_rows'],8)
        self.assertEqual(result['model_seed'],157)
        self.assertEqual(len(result['comparisons']),1)
        comparison=result['comparisons'][0]
        self.assertEqual(len(comparison['pairs']),4)
        self.assertTrue(all(p['strict_prefix_match'] is False and p['canonical_prefix_match'] is True
                            for p in comparison['pairs']))
        self.assertEqual(comparison['all_task_token_difference'],-400)
        self.assertEqual(comparison['common_success_token_difference'],-400)
        self.assertFalse(result['prior_results_pooled'])
        self.assertFalse(result['novel_method_claim'])
        self.assertTrue(result['development_gate_met'])

    def test_success_loss_is_not_hidden_by_equal_success_counts(self):
        data=rows()
        next(r for r in data if r['task_id']==study.TASKS[0] and r['object_timing_mode']==study.MODES[0])['success']=False
        next(r for r in data if r['task_id']==study.TASKS[1] and r['object_timing_mode']==study.MODES[1]).update(success=False,known_total_tokens=1)
        result=study.summarize(data,[])
        self.assertEqual(list(result['success_counts'].values()),[3,3])
        self.assertFalse(result['development_gate_met'])
        self.assertEqual(sum(p['success_lost'] is True for p in result['comparisons'][0]['pairs']),1)

    def test_unknown_and_missing_remain_distinct_from_zero(self):
        data=rows();data[-1]['unknown_usage_calls']=1
        result=study.summarize(data,[])
        self.assertEqual(result['recorded_unknown_usage_calls'],1)
        self.assertEqual(result['usage_count_missing_conditions'],0)
        self.assertIsNone(result['comparisons'][0]['all_task_token_difference'])
        self.assertIsNone(result['comparisons'][0]['common_success_token_difference'])
        self.assertTrue(all(x is None for x in result['total_tokens_by_mode'].values()))
        self.assertFalse(result['development_gate_met'])
        for r in data:r.update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        result=study.summarize(data,[])
        self.assertEqual(result['usage_count_missing_conditions'],8)
        self.assertEqual(result['recorded_unknown_usage_calls'],0)
        self.assertIsNone(result['comparisons'][0]['all_task_token_difference'])

    def test_empty_common_and_no_known_intervention_cannot_pass(self):
        data=rows()
        for r in data:r['success']=False
        result=study.summarize(data,[])
        self.assertIsNone(result['comparisons'][0]['common_success_token_difference'])
        self.assertFalse(result['development_gate_met'])
        for key in ('object_prompt_known_focus_calls','actual_delta_known_actor_calls'):
            for value in (0,None,True):
                data=rows()
                for r in data:r[key]=value
                self.assertFalse(study.summarize(data,[])['development_gate_met'])

    def test_invalid_prefix_or_contract_cannot_pass(self):
        for kind in ('missing','changed','contract'):
            data=rows();r=next(r for r in data if r['object_timing_mode']==study.MODES[1])
            if kind=='missing':r['representation_second_opportunity']=None
            elif kind=='changed':r['representation_second_opportunity']['candidate_cutoff']+=1
            else:r['delta_envelope_contract_failed']=True
            with self.subTest(kind=kind):self.assertFalse(study.summarize(data,[])['development_gate_met'])

    def test_boolean_usage_and_quality_are_not_valid_measurements(self):
        for key,value in [('success',1),('known_total_tokens',True),('unknown_usage_calls',False)]:
            data=rows();data[-1][key]=value
            try:result=study.summarize(data,[])
            except ValueError:continue
            self.assertFalse(result['development_gate_met'])

    def test_fixed_new_seed_and_all_eight_slots(self):
        good=plan();study.validate_plan(good)
        self.assertEqual(len(study.run_order()),8)
        self.assertEqual(good['model_seed'],157)
        for key,value in [('model_seed',57),('max_cells',4)]:
            bad=deepcopy(good);bad[key]=value
            with self.assertRaises(ValueError):study.validate_plan(bad)
        for data in (rows()[:-1], rows()[:-1]+[rows()[0]], rows()+[rows()[0]]):
            with self.assertRaises(ValueError):study.summarize(data,[])

    def test_closed_build_keeps_all_rows_and_pair_nulls_and_exclusivity(self):
        data=rows();data[-1].update(record_status='audit_error',success=None,known_total_tokens=None,unknown_usage_calls=None)
        data[0]['request_checks']=[dict(call_id='call_001',role='agent',status='ok',input_tokens=900,output_tokens=100,cached_input_tokens=800)]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);builder=closed_fixture(root,data,['handwritten audit error'])
            result=builder.build(root)
            self.assertEqual(len(result['conditions']),8)
            self.assertIsNone(result['conditions'][-1]['known_total_tokens'])
            self.assertFalse(result['development_gate_met'])
            with (root/study.MATERIAL/'pairs.csv').open() as f:pairs=list(csv.DictReader(f))
            self.assertEqual(len(pairs),4)
            with (root/study.MATERIAL/'model_calls.csv').open() as f:calls=list(csv.DictReader(f))
            self.assertEqual(calls[0]['model_seed'],'157')
            self.assertEqual(calls[0]['cached_input_tokens'],'800')
            self.assertTrue(any(p['candidate_minus_baseline_tokens']=='' for p in pairs))
            manifest=json.loads((root/study.MATERIAL/'build_manifest.json').read_text())
            self.assertTrue(all(sha(root/study.MATERIAL/n)==h for n,h in manifest['artifact_sha256'].items()))
            with self.assertRaises(FileExistsError):builder.build(root)

    def test_live_wrong_phase_changed_source_or_gate_cannot_publish(self):
        for kind in ('phase','live','source','gate'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                root=Path(td);builder=closed_fixture(root,rows())
                if kind=='source':(root/study.REQUIRED_SOURCES[0]).write_text('changed')
                elif kind=='gate':
                    p=root/'reports/P142_comparison.json';v=json.loads(p.read_text());v['development_gate_met']=not v['development_gate_met'];put(p,v)
                    p=root/'reports/P142_server_session.json';v=json.loads(p.read_text());v['audit_source_sha256']=sha(root/'reports/P142_comparison.json');put(p,v)
                else:
                    p=root/'reports/P142_server_session.json';v=json.loads(p.read_text());v['phase' if kind=='phase' else 'owned_processes_absent']='P141' if kind=='phase' else False;put(p,v)
                with self.assertRaises(ValueError):builder.build(root)
                self.assertFalse((root/study.MATERIAL).exists())


class ThresholdObjectAuditBindingTests(unittest.TestCase):
    def fixture(self, storage, *, evaluated=True, unknown=False):
        import audit_whole_task_threshold_object_p142 as audit
        original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        original['api_budget_by_task']=dict(zip(study.TASKS,(160,80,80,80)))
        p=plan();mode=study.MODES[1];item={**p['known_tasks'][0],'public_task':{'instruction':'handwritten fixture','ground_truth_loaded':False}}
        folder=storage/'records/context_pilot'/study.cell_id(1,mode);folder.mkdir(parents=True)
        config=study.config_for(original,p,item['task_id'],mode)
        put(folder/'plan.json',config);put(folder/'comparison_plan.json',p);put(folder/'public_task.json',item['public_task'])
        summary=dict(phase='P142',arm=study.ERROR_POLICY,time_visibility='not_exposed',object_timing_mode=mode,
            checkpoint_policy='rolling_separate',checkpoint_representation_mode=mode,reasoning_budget_tokens=-1,
            checkpoint_timing='threshold',checkpoint_representation='delta',model_seed=157,
            task_id=item['task_id'],run_id=folder.name,prefix_api_requests=0,stop_reason='wall_limit_during_model_call' if unknown else 'completed',
            model_calls=3 if unknown else 2,known_total_tokens=150,unknown_usage_calls=int(unknown),api_requests=0,
            wall_seconds=1,full_wall_seconds=2,cleanup_wall_seconds=0.5,
            setup={'status':'initial_public_state_matched','wall_seconds':0.5},unknown_effect_requests=0,cleanup_confirmed=True)
        put(folder/'summary.json',summary)
        usage=[dict(role='agent',status='ok',input_tokens=90,output_tokens=10,cached_input_tokens=80),
               dict(role='focus',status='ok',input_tokens=40,output_tokens=10,cached_input_tokens=30)]
        if unknown:usage.append(dict(role='agent',status='error',input_tokens=None,output_tokens=None,cached_input_tokens=None))
        put(folder/'usage.json',usage)
        dbs=storage/'.runtime/appworld/r18_probe_01/experiments/outputs'/folder.name/'tasks'/item['task_id']/'dbs'
        dbs.mkdir(parents=True);(dbs/'synthetic.db').write_bytes(b'handwritten bytes, no database opened')
        evaluation=dict(execution_summary_sha256=sha(folder/'summary.json'),evaluation_returned_to_model=False,
            official_success=False,evaluation_script_sha256=sha(ROOT/'scripts/evaluate_context_trial.py'),
            frozen_database_hashes={'synthetic.db':sha(dbs/'synthetic.db')})
        if evaluated:put(folder/'evaluation.json',evaluation)
        conversation=study.initial_conversation(original,item['public_task']);messages,_=conversation.for_model(config['observation_page_characters'])
        pre={'base_messages_sha256':audit.digest(messages)}
        return audit,folder,p,original,item,mode,pre

    def test_cached_actor_and_focus_input_not_deducted_unknown_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            audit,folder,p,original,item,mode,pre=self.fixture(Path(td),unknown=True)
            with patch.object(audit,'audit_trace',return_value={'checkpoint_installed':False}):
                row=audit.audit_cell(folder,ROOT,p,original,item,mode,pre,True)
            self.assertEqual((row['input_tokens'],row['output_tokens'],row['cached_input_tokens']),(130,20,110))
            self.assertEqual(row['known_total_tokens'],150)
            self.assertEqual(row['unknown_usage_calls'],1)
            self.assertIs(row['success'],False)
            self.assertEqual(row['model_seed'],157)

    def test_unevaluated_does_not_open_or_invent_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            audit,folder,p,original,item,mode,pre=self.fixture(Path(td),evaluated=False)
            with patch.object(audit,'audit_trace',return_value={'checkpoint_installed':False}):
                row=audit.audit_cell(folder,ROOT,p,original,item,mode,pre,False)
            self.assertIsNone(row['success']);self.assertIsNone(row['evaluation_sha256'])
            self.assertEqual(row['record_status'],'unevaluated')

    def test_closed_stopped_batch_retains_all_eight_missing_slots(self):
        import audit_whole_task_threshold_object_p142 as audit
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'repo';storage=Path(td)/'storage';root.mkdir();storage.mkdir()
            p=plan();put(root/study.PLAN,p)
            prepared=[dict(x,public_task={'instruction':'handwritten fixture'}) for x in p['known_tasks']]
            put(root/audit.PREFLIGHT,{'rows':[]})
            put(root/audit.ACTIVATION,{'source_hashes':{},'preflight_sha256':sha(root/audit.PREFLIGHT)})
            pipeline=storage/'records/context_pilot/P142_pipeline_v01'
            put(pipeline/'status.json',{'status':'stopped','server_stopped':True,'server_supervisor_pid':99991})
            put(pipeline/'server_final.json',{'status':'stopped','pid':99992,'supervisor_pid':99991})
            expected=[study.cell_id(*slot) for slot in study.run_order()]
            batch=storage/'records/context_pilot'/p['batch_id']/'status.json'
            put(batch,{'phase':'P142','status':'stopped','planned':expected,'completed':[],'active':None})
            # A begun cell without summary stays incomplete; all other cells stay not_run.
            (storage/'records/context_pilot'/expected[0]).mkdir()
            with patch.object(audit,'sources',return_value=(p,{},[],prepared)), \
                 patch.object(audit,'frozen_hashes',return_value={}), \
                 patch.object(audit.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                result=audit.run(storage,root)
                self.assertEqual(len(result['rows']),8)
                self.assertEqual(result['rows'][0]['record_status'],'incomplete_worker')
                self.assertTrue(all(r['record_status']=='not_run' for r in result['rows'][1:]))
                self.assertTrue(all(r['known_total_tokens'] is None and r['success'] is None for r in result['rows']))
                self.assertFalse(result['development_gate_met'])
                with self.assertRaises(FileExistsError):audit.run(storage,root)

    def test_real_new_worker_to_trace_and_cohort_audit_for_both_policies(self):
        import audit_whole_task_threshold_object_p142 as audit
        from threshold_object_worker_fixture_p142 import fixture, write_wire_fixture, configuration
        for mode in study.MODES:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                result=fixture(mode=mode,folder=td,actions=('echo',)*12+('finish',),max_calls=30)
                folder=write_wire_fixture(td,result)
                p=json.loads((folder/'comparison_plan.json').read_text())
                original,_,item=configuration();original['api_budget_by_task'][item['task_id']]=80
                messages,_=study.initial_conversation(original,item['public_task']).for_model()
                row=audit.audit_cell(folder,ROOT,p,original,item,mode,{'base_messages_sha256':audit.digest(messages)},False)
                self.assertEqual(row['model_seed'],157)
                self.assertEqual(row['object_timing_mode'],mode)
                self.assertEqual(row['known_total_tokens'],result['result']['known_total_tokens'])
                self.assertEqual(row['input_tokens']+row['output_tokens'],row['known_total_tokens'])
                self.assertEqual(sum(v['input_tokens']+v['output_tokens'] for v in row['usage_by_role'].values()),row['known_total_tokens'])
                if mode==study.MODES[1]:
                    self.assertGreater(row['object_prompt_known_focus_calls'],0)
                    self.assertGreater(row['actual_delta_known_actor_calls'],0)
                else:self.assertEqual(row['object_prompt_known_focus_calls'],0)

    def test_wrong_seed_evaluation_or_database_hash_rejected(self):
        for kind in ('seed','evaluation','database','model_return'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                audit,folder,p,original,item,mode,pre=self.fixture(Path(td))
                path=folder/('summary.json' if kind=='seed' else 'evaluation.json');v=json.loads(path.read_text())
                if kind=='seed':v['model_seed']=57
                elif kind=='evaluation':v['execution_summary_sha256']='f'*64
                elif kind=='database':v['frozen_database_hashes']['synthetic.db']='f'*64
                else:v['evaluation_returned_to_model']=0
                put(path,v)
                with patch.object(audit,'audit_trace',return_value={'checkpoint_installed':False}),self.assertRaises(ValueError):
                    audit.audit_cell(folder,ROOT,p,original,item,mode,pre,True)

class ThresholdObjectSessionTests(unittest.TestCase):
    def test_started_missing_wall_is_not_zero(self):
        from inspect_whole_task_threshold_object_session_p142 import cell_time_totals, attempt_time_totals
        result=cell_time_totals([{'record_status':'not_run'}, {'record_status':'incomplete_worker'},
                                {'record_status':'evaluated','full_wall_seconds':5.0}])
        self.assertEqual(result['known_cell_full_wall_seconds'],5.0)
        self.assertEqual(result['unknown_cell_full_wall_count'],1)
        self.assertIsNone(result['cell_full_wall_seconds'])
        timing=attempt_time_totals([{}, {'evaluation_started_at':'synthetic'},
                                   {'evaluation_started_at':'synthetic','evaluation_wall_seconds':3.0}], 'evaluation')
        self.assertEqual((timing['known_subtotal'],timing['unknown_attempts'],timing['attempts']),(3.0,1,2))
        self.assertIsNone(timing['exact_total'])

if __name__=='__main__':unittest.main()

"""Real new worker/rolling code with handwritten transport, no model/API/code execution."""
import copy, json, shutil, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from observed_obligations_worker_fixture import ROOT, fixture, audit_fixture, configuration, CONTRACT_ID
from audit_observed_obligation_trace import audit_trace
import audit_whole_task_observed_obligations as cohort
import inspect_whole_task_observed_obligations_session as session
import build_observed_obligations_summary as report
from whole_task_observed_obligations import initial_conversation, run_order, cell_id, SEEDS, MODES, summarize
from receipt_reasoning_history import digest
from run_handoff_factors import sha

def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
def replay(folder,result):
    p=Path(folder)/'records/context_pilot'/result['result']['run_id'];cfg=read(p/'plan.json')
    original=read(ROOT/'configs/P29_stateful_code_v01.json')
    with patch('observed_field_obligations.verify_partitioned_export_sources',return_value=CONTRACT_ID):
        return audit_trace(p,cfg,initial_conversation(original,read(p/'public_task.json'),cfg['obligation_mode']))

class TraceTests(unittest.TestCase):
    def test_all_modes_real_worker_capture_disclosure_and_role_costs(self):
        for mode in MODES:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                result=fixture(mode=mode,actions=('seed',)+('echo',)*7+('finish',),folder=td)
                checked=audit_fixture(td,result)
                self.assertEqual(result['result']['stop_reason'],'agent_declared_complete')
                self.assertEqual(checked['obligation_checkpoint_captures'],2)
                self.assertEqual(checked['obligation_notice_actor_calls'],0 if mode=='raw_anchor' else 2)
                self.assertEqual(checked['obligation_entity_rows_exposed'],4 if mode=='entity_fields' else 0)
                self.assertEqual(checked['known_total_tokens'],result['result']['known_total_tokens'])
                self.assertTrue(checked['obligation_accounting_complete'])

    def test_explicit_queries_same_response_order_and_raw_cannot_gain_tool(self):
        for mode in MODES:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                result=fixture(mode=mode,actions=('seed','query','query_page','query_stale','query_bad','query_jsonbad','query_then_echo','partial','artist','finish'),folder=td)
                checked=audit_fixture(td,result)
                self.assertEqual(result['result']['stop_reason'],'agent_declared_complete')
                self.assertEqual(checked['obligation_queries'],0 if mode=='raw_anchor' else 4)
                self.assertEqual(checked['obligation_final_enumeration'],'closed')

    def test_unknown_failed_budget_and_invalid_summary_paths(self):
        variants=[dict(actions=('seed',)+('echo',)*12+('finish',)),
            dict(actions=('seed',)+('echo',)*9,summary_mode='unknown'),
            dict(actions=('seed',)+('echo',)*9,summary_mode='transport_error'),
            dict(actions=('seed',)+('echo',)*8+('unknown',)),
            dict(actions=('seed',)+('echo',)*8+('transport_error',)),
            dict(actions=('seed',)+('echo',)*8+('finish',),summary_mode='invalid'),
            dict(actions=('seed',)+('echo',)*8,summary_mode=('valid','unknown')),
            dict(actions=('seed',)+('echo',)*8,token_limit=55000),
            dict(actions=('seed',)+('echo',)*8,focus_input_tokens=64000),
            dict(first_cached=1),dict(count_delay=61),dict(unknown_api=True),
            dict(cleanup_ok=False),dict(stop_after_api=True),dict(actions=('finish',))]
        for mode in MODES:
            for opts in variants:
                with self.subTest(mode=mode,opts=opts),tempfile.TemporaryDirectory() as td:
                    result=fixture(mode=mode,folder=td,**opts);checked=audit_fixture(td,result)
                    self.assertEqual(checked['unknown_usage_calls'],result['result']['unknown_usage_calls'])
                    self.assertEqual(checked['known_total_tokens'],result['result']['known_total_tokens'])

    def test_capture_packet_prefix_revision_and_exposure_tampering_rejected(self):
        changes=[('obligation_captures_private',lambda a:a[0].__setitem__('after_records',999)),
            ('obligation_captures_private',lambda a:a[0].__setitem__('source_boundary_sha256','0'*64)),
            ('obligation_captures_private',lambda a:a[0]['packet']['payload'].__setitem__('pending',[])),
            ('obligation_boundaries_private',lambda a:a[0].__setitem__('checkpoint_revision',99)),
            ('obligation_inference_views',lambda a:next(v for v in a if v['obligation_included']).__setitem__('model_attempted',False)),
            ('obligation_records_private',lambda a:a.pop())]
        for name,change in changes:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                result=fixture(mode='entity_fields',actions=('seed',)+('echo',)*7+('finish',),folder=td)
                audit_fixture(td,result);p=Path(td)/'records/context_pilot'/result['result']['run_id']/(name+'.json')
                value=read(p);change(value);write(p,value)
                with self.assertRaises(ValueError):replay(td,result)

    def test_query_rows_or_index_are_not_authority(self):
        for target in ('query_value','query_record_prefix','event_index','actual_request'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as td:
                result=fixture(mode='entity_fields',actions=('seed','query','query_page','query_then_echo','finish'),folder=td)
                audit_fixture(td,result);trial=Path(td)/'records/context_pilot'/result['result']['run_id']
                if target.startswith('query'):
                    p=trial/'obligation_queries_private.json';v=read(p)
                    if target=='query_value':v[1]['observation']['rows'][0]['song_id']=999
                    else:v[1]['after_records']=0
                elif target=='event_index':
                    p=trial/'events.json';v=read(p);next(e for e in v if 'obligation_query_index'in e)['obligation_query_index']=999
                else:
                    p=trial/'call_002/request.json';v=read(p);v['messages'][0]['content']='forged input'
                write(p,v)
                with self.assertRaises(ValueError):replay(td,result)

    def test_initialization_failure_cannot_certify_missing_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            result=fixture(mode='entity_fields',initial_mismatch=True,folder=td)
            self.assertEqual(result['result']['stop_reason'],'setup_failure')
            with self.assertRaises((ValueError,FileNotFoundError)):audit_fixture(td,result)


def closed_fixture(base,*,missing=False,unknown=False,corrupt=False,lost_completed=False):
    storage=base/'storage';storage.mkdir();root=base/'repo';root.mkdir()
    for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER,'scripts/evaluate_context_trial.py'):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    original,plan,item=configuration();original['api_budget_by_task'][item['task_id']]=80
    plan.update(experiment='P134',batch_id='P134_batch_v01',max_calls=20,max_total_tokens=450000,
        known_tasks=[{k:item[k] for k in ('task_id','source_run')}],obligation_modes=list(MODES),model_seeds=list(SEEDS))
    mapping={name:sha(root/name) for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER)}
    plan['source_sha256']=mapping;write(root/report.PLAN,plan)
    pre_rows=[];completed=[];batch_rows=[]
    for rep in (1,2):
        conditions={}
        for mode in MODES:
            cfg=cohort.config_for(original,plan,item['task_id'],mode,rep)
            initial,_=initial_conversation(original,item['public_task'],mode).for_model(cfg['observation_page_characters'])
            conditions[mode]=dict(base_messages_sha256=digest(initial))
        pre_rows.append(dict(replication=rep,model_seed=SEEDS[rep-1],task_id=item['task_id'],conditions=conditions))
    for rep,number,mode in run_order():
        rid=cell_id(rep,number,mode)
        if missing and rep==2:continue
        opts=dict(actions=('seed',)+('echo',)*7+('finish',))
        if unknown and rep==1 and mode=='entity_fields':opts=dict(actions=('seed',)+('echo',)*8,summary_mode='unknown')
        result=fixture(mode=mode,replication=rep,folder=storage,**opts);audit_fixture(storage,result)
        trial=storage/'records/context_pilot'/rid;write(trial/'comparison_plan.json',plan)
        dbs=storage/'.runtime/appworld/r18_probe_01/experiments/outputs'/rid/'tasks'/item['task_id']/'dbs'
        write(dbs/'synthetic.json',{'synthetic':True})
        write(trial/'evaluation.json',dict(execution_summary_sha256=sha(trial/'summary.json'),
            evaluation_returned_to_model=False,official_success=True,
            evaluation_script_sha256=sha(root/'scripts/evaluate_context_trial.py'),
            frozen_database_hashes={'synthetic.json':sha(dbs/'synthetic.json')}))
        completed.append(rid);batch_rows.append(dict(run_id=rid,evaluation_started_at='synthetic',evaluation_wall_seconds=.1))
        if corrupt and rep==2 and mode=='entity_fields':
            p=trial/'obligation_captures_private.json';value=read(p);value[0]['after_records']=999;write(p,value)
        if lost_completed and rep==2 and mode=='entity_fields':shutil.rmtree(trial)
    write(root/report.PREFLIGHT,dict(rows=pre_rows))
    write(root/report.ACTIVATION,dict(source_hashes=mapping,preflight_sha256=sha(root/report.PREFLIGHT)))
    p=storage/'records/context_pilot/P134_pipeline_v01';record=storage/'records/p2_servers/synthetic'
    server=dict(status='stopped',stop_reason='synthetic',supervisor_pid=10000001,pid=10000002,
        record_directory=str(record.relative_to(storage)),started_at='synthetic',wall_seconds=100,
        load_wall_seconds=1,sampled_peak_rss_bytes=100,peak_system_swap_bytes=0,exit_code=0,
        model_revision='synthetic',runtime='synthetic',ctx_size=64000,cache_type_k='f16',cache_type_v='f16',memory_note='synthetic')
    write(record/'summary.json',server);(record/'memory.jsonl').write_text(json.dumps({'rss_bytes':100,'swap_used_bytes':0})+'\n')
    write(p/'server_final.json',server)
    write(p/'status.json',dict(status='stopped' if missing else 'complete',server_stopped=True,
        server_supervisor_pid=server['supervisor_pid'],wall_seconds=100,stages=[dict(mode='batch',wall_seconds=90)]))
    write(storage/'records/context_pilot/P134_batch_v01/status.json',dict(phase='P134',status='stopped' if missing else 'complete',
        completed=completed,rows=batch_rows,active=None))
    with patch('run_whole_task_observed_obligations.sources',return_value=(plan,original,[],[item])), \
         patch('run_whole_task_observed_obligations.frozen_hashes',return_value=mapping), \
         patch('observed_field_obligations.verify_partitioned_export_sources',return_value=CONTRACT_ID), \
         patch.object(cohort.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
        audited=cohort.run(storage,root);server_report=session.inspect(storage,root)
    write(root/report.SESSION,server_report)
    with patch.object(report,'ROOT',root):published=report.build(root)
    return audited,published,root,storage


class ReportingTests(unittest.TestCase):
    def test_six_workers_through_audit_session_and_public_report(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,root,_=closed_fixture(Path(td))
            self.assertEqual(audit['audit_errors'],[]);self.assertEqual(len(pub['conditions']),6)
            self.assertEqual(pub['all_conditions']['evaluated_conditions'],6)
            self.assertIsNotNone(pub['all_conditions']['exact_total_tokens'])
            self.assertEqual(sum(r['obligation_entity_rows_exposed']for r in pub['conditions']),8)
            self.assertEqual(set(pub['comparison_costs']),{'primary','raw_anchor'})
            self.assertFalse(pub['audited_criteria']['development_gate_met'])
            self.assertNotIn('Observed title',(root/report.TARGET/'summary.json').read_text())
            with patch.object(report,'ROOT',root),self.assertRaises(FileExistsError):report.build(root)

    def test_unknown_keeps_nested_exact_usage_null(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,_,_=closed_fixture(Path(td),unknown=True)
            self.assertEqual(audit['audit_errors'],[]);self.assertIsNone(pub['all_conditions']['exact_total_tokens'])
            for field in ('input_tokens','output_tokens','cached_input_tokens'):
                self.assertIsNone(pub['all_conditions']['measures'][field]['exact_all_condition_total'])
            self.assertFalse(pub['audited_criteria']['development_gate_met'])

    def test_unrun_and_completed_but_lost_are_retained(self):
        for option,status,count in [('missing','not_run',3),('lost_completed','incomplete_worker',1)]:
            with self.subTest(option=option),tempfile.TemporaryDirectory() as td:
                audit,pub,_,_=closed_fixture(Path(td),**{option:True})
                selected=[r for r in pub['conditions']if r['record_status']==status]
                self.assertEqual(len(selected),count);self.assertEqual(len(pub['conditions']),6)
                self.assertTrue(all(r['known_total_tokens']is None for r in selected))
                self.assertIsNone(pub['all_conditions']['exact_total_tokens'])

    def test_tampered_capture_is_audit_error_not_zero_cost(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,_,_=closed_fixture(Path(td),corrupt=True)
            self.assertEqual(len(audit['audit_errors']),1)
            bad=next(r for r in pub['conditions']if r['record_status']=='audit_error')
            self.assertIsNone(bad['known_total_tokens']);self.assertIsNone(bad['obligation_entity_rows_exposed'])
            self.assertFalse(pub['audited_criteria']['development_gate_met'])

if __name__=='__main__':unittest.main(verbosity=2)

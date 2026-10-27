"""Real new worker/rolling code with handwritten transport, no model/API/code execution."""
import copy, json, shutil, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from late_obligations_worker_fixture_p136 import ROOT, fixture, audit_fixture, configuration, CONTRACT_ID
from audit_late_obligation_trace_p136 import audit_trace
import audit_whole_task_late_obligations_p136 as cohort
import inspect_whole_task_late_obligations_session_p136 as session
import build_late_obligations_summary_p136 as report
from whole_task_late_obligations_p136 import initial_conversation, run_order, cell_id, SEEDS, MODES, summarize
from receipt_reasoning_history import digest
from run_handoff_factors import sha

def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
def replay(folder,result):
    p=Path(folder)/'records/context_pilot'/result['result']['run_id'];cfg=read(p/'plan.json')
    original=read(ROOT/'configs/P29_stateful_code_v01.json')
    with patch('late_obligation_core_p136.verify_late_obligation_sources',return_value=CONTRACT_ID):
        return audit_trace(p,cfg,initial_conversation(original,read(p/'public_task.json'),cfg['obligation_mode']))


def closed_fixture(base,*,missing=False,unknown=False,corrupt=False,lost_completed=False,full_historical_source_closure=False):
    storage=base/'storage';storage.mkdir();root=base/'repo';root.mkdir()
    for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER,'scripts/evaluate_context_trial.py'):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    original,plan,item=configuration();original['api_budget_by_task'][item['task_id']]=80
    plan.update(experiment='P136',batch_id='P136_batch_v01',max_calls=20,max_total_tokens=450000,
        known_tasks=[{k:item[k] for k in ('task_id','source_run')}],obligation_modes=list(MODES),model_seeds=list(SEEDS))
    mapping={}
    if full_historical_source_closure:
        historical=read(ROOT/'configs/P135_whole_task_observed_obligations_v01.json')['source_sha256']
        if len(historical)!=1498:raise AssertionError('full_historical_map_required')
        for name,expected_hash in historical.items():
            source=ROOT/name
            if sha(source)!=expected_hash:raise AssertionError('historical_source_changed')
            destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        mapping.update(historical)
    mapping.update({name:sha(root/name) for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER)})
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
    p=storage/'records/context_pilot/P136_pipeline_v01';record=storage/'records/p2_servers/synthetic'
    server=dict(status='stopped',stop_reason='synthetic',supervisor_pid=10000001,pid=10000002,
        record_directory=str(record.relative_to(storage)),started_at='synthetic',wall_seconds=100,
        load_wall_seconds=1,sampled_peak_rss_bytes=100,peak_system_swap_bytes=0,exit_code=0,
        model_revision='synthetic',runtime='synthetic',ctx_size=64000,cache_type_k='f16',cache_type_v='f16',memory_note='synthetic')
    write(record/'summary.json',server);(record/'memory.jsonl').write_text(json.dumps({'rss_bytes':100,'swap_used_bytes':0})+'\n')
    write(p/'server_final.json',server)
    write(p/'status.json',dict(status='stopped' if missing else 'complete',server_stopped=True,
        server_supervisor_pid=server['supervisor_pid'],wall_seconds=100,stages=[dict(mode='batch',wall_seconds=90)]))
    write(storage/'records/context_pilot/P136_batch_v01/status.json',dict(phase='P136',status='stopped' if missing else 'complete',
        completed=completed,rows=batch_rows,active=None))
    with patch('run_whole_task_late_obligations_p136.sources',return_value=(plan,original,[],[item])), \
         patch('run_whole_task_late_obligations_p136.frozen_hashes',return_value=mapping), \
         patch('late_obligation_core_p136.verify_late_obligation_sources',return_value=CONTRACT_ID), \
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
            self.assertEqual(sum(r['obligation_entity_rows_exposed']for r in pub['conditions']),16)
            self.assertEqual(sum(r['obligation_field_rows_exposed']for r in pub['conditions']),8)
            self.assertTrue(all(r['obligation_queries']==r['obligation_query_rejections']==0 for r in pub['conditions']))
            self.assertTrue(all(r['obligation_field_rows_exposed']==0 for r in pub['conditions'] if r['obligation_mode']!='entity_fields'))
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


class CompleteFrozenSourceRegressionTests(unittest.TestCase):
    def test_all_1498_real_P135_frozen_paths_and_hashes_are_accepted(self):
        # This exact historical source map contains public materials/papers.
        # It belongs to the closed P135 source lineage and contains no raw trial records.
        mapping = read(ROOT/'configs/P135_whole_task_observed_obligations_v01.json')['source_sha256']
        self.assertEqual(len(mapping),1498)
        extra = {name for name in mapping if name.split('/')[0] in ('materials','papers')}
        self.assertEqual(extra,set(report.RECOVERED_PUBLIC_SOURCE_PATHS))
        self.assertEqual(len(extra),7)
        self.assertEqual(report.validate_source_map(ROOT,mapping,frozen_scope=mapping),1498)

    def test_real_1498_source_closure_through_full_six_slot_report_build(self):
        with tempfile.TemporaryDirectory() as temp:
            audit,pub,root,_=closed_fixture(Path(temp),full_historical_source_closure=True)
            self.assertEqual(audit['audit_errors'],[]);self.assertEqual(len(pub['conditions']),6)
            frozen=read(root/report.PLAN)['source_sha256']
            self.assertEqual(len(frozen),1502)
            self.assertTrue(report.RECOVERED_PUBLIC_SOURCE_PATHS <= frozen.keys())
            manifest=read(root/report.TARGET/'build_manifest.json')
            self.assertEqual(manifest['activation_bound_source_count'],1502)

    def test_previous_public_path_rejects_the_seven_regression_cases(self):
        from build_p132_report import public_path as previous
        for name in report.RECOVERED_PUBLIC_SOURCE_PATHS:
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'repository_public_source_path_required'):
                previous(ROOT,name)

    def test_extra_file_requires_frozen_membership_and_exact_hash(self):
        name=next(iter(report.RECOVERED_PUBLIC_SOURCE_PATHS))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/name;p.parent.mkdir(parents=True);p.write_text('public fixture')
            for scope in (None,{}, {name:'0'*64}):
                with self.subTest(scope=scope),self.assertRaises(ValueError):report.public_path(root,name,source_sha256=scope)
            expected=sha(p);self.assertEqual(report.public_path(root,name,source_sha256={name:expected}),p.resolve())
            p.write_text('changed public fixture')
            with self.assertRaisesRegex(ValueError,'extra_public_source_hash_changed'):report.public_path(root,name,source_sha256={name:expected})

    def test_arbitrary_materials_papers_and_private_paths_stay_forbidden(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('materials/unfrozen.json','papers/unfrozen.tex','records/private.json','.runtime/private.json'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
                with self.subTest(name=name),self.assertRaisesRegex(ValueError,'repository_public_source_scope_required'):
                    report.public_path(root,name,source_sha256={name:sha(p)})

    def test_traversal_absolute_noncanonical_and_symlink_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'scripts').mkdir();(root/'scripts/ok.py').write_text('x')
            for name in ('/etc/passwd','scripts/../scripts/ok.py','scripts//ok.py','scripts/./ok.py','scripts\\ok.py'):
                with self.subTest(name=name),self.assertRaises(ValueError):report.public_path(root,name)
            (root/'scripts/link.py').symlink_to(root/'scripts/ok.py')
            with self.assertRaisesRegex(ValueError,'symlink'):report.public_path(root,'scripts/link.py')
            (root/'docs').symlink_to(root/'scripts',target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):report.public_path(root,'docs/ok.py')

    def test_complete_source_map_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'scripts').mkdir();(root/'scripts/a.py').write_text('public')
            scope={'scripts/a.py':sha(root/'scripts/a.py')};changed={**scope,'scripts/a.py':'0'*64}
            with self.assertRaisesRegex(ValueError,'frozen_public_source_changed'):
                report.validate_source_map(root,changed,frozen_scope=scope)

if __name__=='__main__':unittest.main(verbosity=2)

"""Real new worker/rolling code with handwritten transport, no model/API/code execution."""
import copy, json, shutil, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from remaining_late_obligations_worker_fixture_p137 import ROOT, fixture, audit_fixture, configuration, CONTRACT_ID
from audit_late_obligation_trace_p136 import audit_trace
import audit_whole_task_remaining_late_obligations_p137 as cohort
import inspect_whole_task_remaining_late_obligations_session_p137 as session
import build_remaining_late_obligations_summary_p137 as report
from whole_task_remaining_late_obligations_p137 import initial_conversation, run_order, cell_id, SEEDS, MODES, summarize, modes_for_replication
from receipt_reasoning_history import digest
from run_handoff_factors import sha

def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
def replay(folder,result):
    p=Path(folder)/'records/context_pilot'/result['result']['run_id'];cfg=read(p/'plan.json')
    original=read(ROOT/'configs/P29_stateful_code_v01.json')
    with patch('late_obligation_core_p136.verify_late_obligation_sources',return_value=CONTRACT_ID):
        return audit_trace(p,cfg,initial_conversation(original,read(p/'public_task.json'),cfg['obligation_mode']))


def closed_fixture(base,*,missing=False,unknown=False,corrupt=False,lost_completed=False,unevaluated=False,publish=True):
    storage=base/'storage';storage.mkdir();root=base/'repo';root.mkdir()
    for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER,'scripts/evaluate_context_trial.py'):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    original,plan,item=configuration();original['api_budget_by_task'][item['task_id']]=80
    plan.update(experiment='P137',batch_id='P137_batch_v01',max_calls=20,max_total_tokens=450000,
        known_tasks=[{k:item[k] for k in ('task_id','source_run')}],obligation_modes=list(MODES),model_seeds=list(SEEDS))
    mapping={}
    mapping.update({name:sha(root/name) for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER)})
    plan['source_sha256']=mapping;write(root/report.PLAN,plan)
    pre_rows=[];completed=[];batch_rows=[]
    for rep in (1,2):
        conditions={}
        for mode in modes_for_replication(rep):
            cfg=cohort.config_for(original,plan,item['task_id'],mode,rep)
            initial,_=initial_conversation(original,item['public_task'],mode).for_model(cfg['observation_page_characters'])
            conditions[mode]=dict(base_messages_sha256=digest(initial))
        pre_rows.append(dict(replication=rep,model_seed=SEEDS[rep-1],task_id=item['task_id'],conditions=conditions))
    for rep,number,mode in run_order():
        rid=cell_id(rep,number,mode)
        if missing and rep==2:continue
        opts=dict(actions=('seed',)+('echo',)*7+('finish',))
        if unknown and rep==2 and mode=='entity_fields':opts=dict(actions=('seed',)+('echo',)*8,summary_mode='unknown')
        result=fixture(mode=mode,replication=rep,folder=storage,**opts);audit_fixture(storage,result)
        trial=storage/'records/context_pilot'/rid;write(trial/'comparison_plan.json',plan)
        dbs=storage/'.runtime/appworld/r18_probe_01/experiments/outputs'/rid/'tasks'/item['task_id']/'dbs'
        write(dbs/'synthetic.json',{'synthetic':True})
        write(trial/'evaluation.json',dict(execution_summary_sha256=sha(trial/'summary.json'),
            evaluation_returned_to_model=False,official_success=True,
            evaluation_script_sha256=sha(root/'scripts/evaluate_context_trial.py'),
            frozen_database_hashes={'synthetic.json':sha(dbs/'synthetic.json')}))
        if not (unevaluated and rep==2 and mode=='entity_fields'):completed.append(rid)
        batch_rows.append(dict(run_id=rid,evaluation_started_at='synthetic',evaluation_wall_seconds=.1))
        if corrupt and rep==2 and mode=='entity_fields':
            p=trial/'obligation_captures_private.json';value=read(p);value[0]['after_records']=999;write(p,value)
        if lost_completed and rep==2 and mode=='entity_fields':shutil.rmtree(trial)
    write(root/report.PREFLIGHT,dict(rows=pre_rows))
    write(root/report.ACTIVATION,dict(source_hashes=mapping,preflight_sha256=sha(root/report.PREFLIGHT)))
    p=storage/'records/context_pilot/P137_pipeline_v01';record=storage/'records/p2_servers/synthetic'
    server=dict(status='stopped',stop_reason='synthetic',supervisor_pid=10000001,pid=10000002,
        record_directory=str(record.relative_to(storage)),started_at='synthetic',wall_seconds=100,
        load_wall_seconds=1,sampled_peak_rss_bytes=100,peak_system_swap_bytes=0,exit_code=0,
        model_revision='synthetic',runtime='synthetic',ctx_size=64000,cache_type_k='f16',cache_type_v='f16',memory_note='synthetic')
    write(record/'summary.json',server);(record/'memory.jsonl').write_text(json.dumps({'rss_bytes':100,'swap_used_bytes':0})+'\n')
    write(p/'server_final.json',server)
    write(p/'status.json',dict(status='stopped' if missing or unevaluated else 'complete',server_stopped=True,
        server_supervisor_pid=server['supervisor_pid'],wall_seconds=100,stages=[dict(mode='batch',wall_seconds=90)]))
    write(storage/'records/context_pilot/P137_batch_v01/status.json',dict(phase='P137',status='stopped' if missing or unevaluated else 'complete',
        planned=[cell_id(rep,n,mode) for rep,n,mode in run_order()],completed=completed,rows=batch_rows,active=None))
    with patch('run_whole_task_remaining_late_obligations_p137.sources',return_value=(plan,original,[],[item])), \
         patch('run_whole_task_remaining_late_obligations_p137.frozen_hashes',return_value=mapping), \
         patch('late_obligation_core_p136.verify_late_obligation_sources',return_value=CONTRACT_ID), \
         patch.object(cohort.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
        audited=cohort.run(storage,root);server_report=session.inspect(storage,root)
    write(root/report.SESSION,server_report)
    published=None
    if publish:
        with patch.object(report,'ROOT',root):published=report.build(root)
    return audited,published,root,storage


class ReportingTests(unittest.TestCase):
    def test_four_workers_through_audit_session_and_public_report(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,root,_=closed_fixture(Path(td))
            self.assertEqual(audit['audit_errors'],[])
            self.assertEqual(len(pub['conditions']),4)
            self.assertEqual(pub['all_conditions']['evaluated_conditions'],4)
            self.assertIsNotNone(pub['all_conditions']['exact_total_tokens'])
            self.assertEqual([(r['replication'],1,r['obligation_mode'])for r in pub['conditions']],run_order())
            self.assertFalse(pub['balanced_repetitions'])
            self.assertEqual(pub['seed57_unpaired']['condition'],pub['conditions'][0])
            self.assertEqual(pub['seed57_unpaired']['aggregate']['planned_conditions'],1)
            self.assertFalse(pub['seed57_unpaired']['comparison_performed'])
            self.assertEqual(pub['by_policy']['entity_fields']['planned_conditions'],2)
            self.assertTrue(pub['by_policy_totals_are_descriptive_only'])
            self.assertFalse(pub['development_gate_met'])
            self.assertFalse(pub['scientific_adoption_evaluated'])
            self.assertFalse(pub['prior_results_pooled'])
            self.assertFalse(pub['original_P136_gate_replaced'])
            for comparison in pub['comparison_costs'].values():
                self.assertEqual(comparison['planned_pairs'],1)
                self.assertEqual(comparison['comparable_model_seeds'],[157])
                self.assertTrue(comparison['seed57_unpaired_excluded'])
                for policy in comparison['all_pairs_by_policy'].values():
                    self.assertEqual(policy['planned_conditions'],1)
            for comparison in pub['by_replication']['1']['comparison_costs'].values():
                self.assertEqual(comparison['planned_pairs'],0)
                for policy in comparison['all_pairs_by_policy'].values():
                    self.assertEqual(policy['planned_conditions'],0)
                    self.assertIsNone(policy['exact_total_tokens'])
            self.assertTrue(all(r['obligation_queries']==r['obligation_query_rejections']==0 for r in pub['conditions']))
            self.assertTrue(all(r['obligation_field_rows_exposed']==0 for r in pub['conditions']if r['obligation_mode']!='entity_fields'))
            content=(root/report.TARGET/'summary.json').read_text()
            self.assertNotIn('Observed title',content)
            self.assertNotIn('synthetic-token',content)
            self.assertIn('2048', (root/report.TARGET/'README.md').read_text())
            self.assertIn('2091', (root/report.TARGET/'README.md').read_text())
            manifest=read(root/report.TARGET/'build_manifest.json')
            self.assertTrue(all(manifest[k]==0 for k in ('new_model_calls','new_API_requests','new_tokenizer_calls','new_evaluations')))
            self.assertIn(report.INSPECTOR,manifest['source_sha256'])
            self.assertFalse(any('P136_comparison' in n for n in manifest['source_sha256']))
            with patch.object(report,'ROOT',root),self.assertRaises(FileExistsError):report.build(root)

    def test_unknown_preserves_known_subtotal_and_null_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,_,_=closed_fixture(Path(td),unknown=True)
            self.assertEqual(audit['audit_errors'],[])
            self.assertGreater(pub['all_conditions']['known_token_subtotal'],0)
            self.assertEqual(pub['all_conditions']['recorded_unknown_usage_calls'],1)
            self.assertIsNone(pub['all_conditions']['exact_total_tokens'])
            for field in ('input_tokens','output_tokens','cached_input_tokens'):
                self.assertIsNone(pub['all_conditions']['measures'][field]['exact_all_condition_total'])
            for name in ('primary_comparison','raw_anchor_comparison'):
                self.assertIsNone(pub['audited_criteria'][name]['candidate_minus_baseline_whole_task_tokens'])
            self.assertFalse(pub['audited_criteria']['development_gate_met'])

    def test_unrun_and_lost_worker_are_retained(self):
        for option,status,count in [('missing','not_run',3),('lost_completed','incomplete_worker',1)]:
            with self.subTest(option=option),tempfile.TemporaryDirectory() as td:
                _,pub,_,_=closed_fixture(Path(td),**{option:True})
                selected=[r for r in pub['conditions']if r['record_status']==status]
                self.assertEqual(len(selected),count)
                self.assertEqual(len(pub['conditions']),4)
                self.assertTrue(all(r['known_total_tokens']is None and r['success']is None for r in selected))
                self.assertIsNone(pub['all_conditions']['exact_total_tokens'])
                self.assertEqual(pub['all_conditions']['unknown_usage_count_missing_conditions'],count)
                self.assertIsNone(pub['audited_criteria']['primary_comparison']['candidate_minus_baseline_whole_task_tokens'])

    def test_unevaluated_costs_preserved_without_inventing_success(self):
        with tempfile.TemporaryDirectory() as td:
            _,pub,_,_=closed_fixture(Path(td),unevaluated=True)
            row=next(r for r in pub['conditions']if r['record_status']=='unevaluated')
            self.assertIsNone(row['success']);self.assertIsNone(row['evaluation_sha256'])
            self.assertGreater(row['known_total_tokens'],0)
            self.assertIsNotNone(pub['all_conditions']['exact_total_tokens'])
            self.assertIsNone(pub['audited_criteria']['primary_comparison']['candidate_minus_baseline_whole_task_tokens'])

    def test_tampered_capture_becomes_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,_,_=closed_fixture(Path(td),corrupt=True)
            self.assertEqual(len(audit['audit_errors']),1)
            row=next(r for r in pub['conditions']if r['record_status']=='audit_error')
            self.assertIsNone(row['known_total_tokens']);self.assertIsNone(row['obligation_entity_rows_exposed'])
            self.assertIsNone(pub['all_conditions']['exact_total_tokens'])
            self.assertFalse(pub['audited_criteria']['development_gate_met'])

    def test_prior_namespace_and_extra_six_slot_rows_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            audit,_,root,_=closed_fixture(Path(td),publish=False)
            original=copy.deepcopy(audit)
            variants=[]
            changed=copy.deepcopy(original);changed['phase']='P136';variants.append(changed)
            changed=copy.deepcopy(original);changed['rows'][0]['run_id']=changed['rows'][0]['run_id'].replace('P137','P136');variants.append(changed)
            changed=copy.deepcopy(original);changed['rows']+=copy.deepcopy(changed['rows'][:2]);variants.append(changed)
            changed=copy.deepcopy(original);changed['development_gate_met']=True;variants.append(changed)
            for changed in variants:
                with self.subTest(kind=changed['phase'],rows=len(changed['rows'])):
                    write(root/report.AUDIT,changed)
                    server=read(root/report.SESSION);server['audit_source_sha256']=sha(root/report.AUDIT);write(root/report.SESSION,server)
                    with patch.object(report,'ROOT',root),self.assertRaises(ValueError):report.build(root)
                    self.assertFalse((root/report.TARGET).exists())


class DescriptiveScopeTests(unittest.TestCase):
    def rows(self):
        return [dict(run_id=cell_id(rep,n,mode),task_id='synthetic',replication=rep,
            model_seed=SEEDS[rep-1],obligation_mode=mode,record_status='evaluated',success=True,
            known_total_tokens=(999999 if rep==1 else 10 if mode=='entity_fields'else 100),
            unknown_usage_calls=0,obligation_field_rows_exposed=1 if mode=='entity_fields'else 0,
            obligation_contract_failed=False,obligation_accounting_complete=True)
            for rep,n,mode in run_order()]

    def test_large_seed57_value_never_enters_seed157_pair(self):
        rows=self.rows();criteria=summarize(rows,[])
        self.assertFalse(criteria['development_gate_met'])
        self.assertFalse(criteria['scientific_adoption_evaluated'])
        for comparison in report.all_comparisons(rows,criteria).values():
            costs=comparison['all_pairs_by_policy']
            self.assertEqual(costs['entity_fields']['exact_total_tokens'],10)
            self.assertEqual(costs[comparison['baseline']]['exact_total_tokens'],100)
            self.assertEqual(comparison['planned_pairs'],1)
        self.assertEqual(criteria['primary_comparison']['candidate_minus_baseline_whole_task_tokens'],-90)
        self.assertEqual(criteria['seed57_unpaired_result']['known_total_tokens'],999999)

    def test_empty_common_success_and_quality_loss_not_savings(self):
        rows=self.rows();rows[1]['success']=False
        criteria=summarize(rows,[])
        self.assertEqual(criteria['primary_comparison']['paired_success_losses'],1)
        self.assertIsNone(criteria['primary_comparison']['paired_successful_token_difference'])
        self.assertEqual(criteria['primary_comparison']['paired_results'][0]['quality_transition'],'quality_loss')
        for comparison in report.all_comparisons(rows,criteria).values():
            self.assertEqual(comparison['outcome_groups']['common_success']['pairs'],0)
            self.assertIsNone(comparison['outcome_groups']['common_success']['by_policy']['entity_fields']['exact_total_tokens'])
        self.assertFalse(criteria['development_gate_met'])

    def test_none_for_all_four_unstarted_is_not_exact_zero(self):
        rows=self.rows()
        for row in rows:
            row.update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None,
                obligation_field_rows_exposed=None,obligation_contract_failed=None,obligation_accounting_complete=None)
        criteria=summarize(rows,[]);total=report.aggregate(rows)
        self.assertEqual(total['known_token_subtotal'],0)
        self.assertEqual(total['accounted_conditions'],0)
        self.assertEqual(total['unknown_usage_count_missing_conditions'],4)
        self.assertIsNone(total['exact_total_tokens'])
        self.assertIsNone(criteria['no_paired_success_loss_against_either_control'])
        self.assertFalse(criteria['development_gate_met'])

    def test_public_row_forbids_omitted_prior_slots_and_bool_replication(self):
        row=dict(run_id='BOC_P137_R01_01_RAW_ANCHOR',task_id='synthetic',replication=1,model_seed=57,
            obligation_mode='raw_anchor',checkpoint_policy='rolling_separate',record_status='not_run',success=None)
        with self.assertRaises(ValueError):report.public_row(row)
        row.update(run_id=cell_id(1,1,'entity_fields'),obligation_mode='entity_fields',replication=True)
        with self.assertRaises(ValueError):report.public_row(row)


class SourceScopeTests(unittest.TestCase):
    def test_seven_legacy_public_paths_require_frozen_membership_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            mapping={}
            for name in report.RECOVERED_PUBLIC_SOURCE_PATHS:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('public fixture')
                mapping[name]=sha(path)
                with self.assertRaises(ValueError):report.public_path(root,name)
            self.assertEqual(report.validate_source_map(root,mapping,frozen_scope=mapping),7)
            name=next(iter(mapping));(root/name).write_text('changed')
            with self.assertRaises(ValueError):report.validate_source_map(root,mapping,frozen_scope=mapping)

    def test_private_traversal_unbound_material_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'scripts').mkdir();(root/'scripts/ok.py').write_text('public')
            for name in ('records/private.json','materials/unbound.json','papers/unbound.tex','/etc/passwd',
                         'scripts/../scripts/ok.py','scripts//ok.py','scripts/./ok.py','scripts\\ok.py'):
                with self.subTest(name=name),self.assertRaises(ValueError):report.public_path(root,name)
            (root/'scripts/link.py').symlink_to(root/'scripts/ok.py')
            with self.assertRaises(ValueError):report.public_path(root,'scripts/link.py')


if __name__=='__main__':unittest.main(verbosity=2)

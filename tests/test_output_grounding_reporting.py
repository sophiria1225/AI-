from copy import deepcopy
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_output_grounding_summary as reporting
import inspect_whole_task_output_grounding_session as session


class OutputGroundingReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        p=patch.object(reporting,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        for name in (reporting.BUILDER,reporting.AUDITOR,reporting.INSPECTOR,reporting.HELPER):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# synthetic source\n')
        self.write(reporting.PREFLIGHT,{'synthetic':True})
        sources={n:reporting.sha(self.root/n) for n in (reporting.BUILDER,reporting.AUDITOR,reporting.INSPECTOR,reporting.HELPER)}
        self.write(reporting.PLAN,dict(experiment='P129',grounding_modes=list(reporting.POLICIES),model_seeds=list(reporting.SEEDS),known_tasks=[{'task_id':'synthetic-CSV'}],source_sha256=sources))
        self.write(reporting.ACTIVATION,dict(source_hashes=sources,preflight_sha256=reporting.sha(self.root/reporting.PREFLIGHT)))
        self.rows=[self.row(rep,n,mode) for rep,n,mode in reporting.run_order()]
        self.refresh()
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value)+'\n')
    def row(self,rep,n,mode):
        d=mode=='repair';rt={k:0 for k in reporting.RUNTIME_COUNTS};rt.update({k:.01 for k in reporting.RUNTIME_TIMES});rt.update({k:True for k in reporting.RUNTIME_FLAGS})
        rt.update(policy='explicit_joined_fields',projection_failed=False,program_attempts=2,program_evidence_records=2,explicit_field_interface_shared_between_policies=True,joined_provider_shared_between_policies=True)
        row=dict(run_id=reporting.cell_id(rep,n,mode),task_id='synthetic-CSV',replication=rep,model_seed=reporting.SEEDS[rep-1],grounding_mode=mode,projection_policy='explicit_joined_fields',checkpoint_policy='rolling_separate',record_status='evaluated',success=True,stop_reason='completed',model_calls=2,known_total_tokens=90 if d else 100,unknown_usage_calls=0,api_requests=2,input_tokens=70 if d else 80,output_tokens=20,cached_input_tokens=0,projection_hits=0,setup_wall_seconds=.1,wall_seconds=1.,cleanup_wall_seconds=.2,full_wall_seconds=1.3,checkpoint_installed=False,checkpoint_opportunity=0,checkpoint_installations=0,projection_contract_failed=False,projection_runtime=rt,summary_sha256='a'*64,usage_sha256='b'*64,evaluation_sha256='c'*64)
        row.update({k:0 for k in reporting.GROUNDING_COUNTS})
        row.update(grounding_write_checks=1,grounding_feedback_blocks=int(mode=='feedback'),grounding_repair_attempts=int(d),grounding_sent_repairs=int(d),grounding_repairs=int(d),grounding_contract_failed=False,grounding_accounting_complete=True,grounding_wall_seconds=.02,grounding_ledger_sha256='f'*64)
        return row
    def refresh(self):
        for row in self.rows:
            if row['record_status'] in ('evaluated','unevaluated'):
                row['grounding_runtime'] = {v:row[k] for k,v in reporting.GROUNDING_MAP.items()}
                row['grounding_runtime'].update(mode=row['grounding_mode'],contract_intact=not row['grounding_contract_failed'])
        self.report=dict(phase='P129',batch_status='complete',rows=self.rows,owned_processes_absent=True,audit_errors=[],plan_sha256=reporting.sha(self.root/reporting.PLAN),activation_sha256=reporting.sha(self.root/reporting.ACTIVATION),auditor_sha256=reporting.sha(self.root/reporting.AUDITOR),pipeline_status_sha256='d'*64,server_final_sha256='e'*64,**reporting.summarize(self.rows,[]))
        self.write(reporting.AUDIT,self.report)
        self.write(reporting.SESSION,dict(phase='P129',status='stopped',owned_processes_absent=True,pipeline_source_sha256='d'*64,source_sha256='e'*64,inspector_sha256=reporting.sha(self.root/reporting.INSPECTOR),audit_source_sha256=reporting.sha(self.root/reporting.AUDIT),wall_seconds=30))
    def by(self,rep,mode):return next(r for r in self.rows if r['replication']==rep and r['grounding_mode']==mode)
    def test_six_public_rows_source_binding_privacy_and_exclusive_publication(self):
        self.rows[0]['private_csv']='PRIVATE_SENTINEL';self.refresh()
        out=reporting.build(self.root);target=self.root/reporting.TARGET
        self.assertEqual(out['all_conditions']['exact_total_tokens'],580)
        self.assertEqual(out['independent_tasks'],1)
        self.assertTrue(out['audited_criteria']['development_gate_met'])
        self.assertEqual(out['by_replication']['2']['by_policy']['repair']['exact_total_tokens'],90)
        self.assertEqual(out['comparison_costs']['feedback']['outcome_groups']['common_success']['pairs'],2)
        with (target/'conditions.csv').open() as f:self.assertEqual(len(list(csv.DictReader(f))),6)
        self.assertNotIn('PRIVATE_SENTINEL',''.join(p.read_text() for p in target.iterdir()))
        before={p.name:p.read_bytes() for p in target.iterdir()}
        with self.assertRaises(FileExistsError):reporting.build(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in target.iterdir()})
    def test_sent_repair_without_verified_backup_is_not_gate_activity(self):
        for r in self.rows:
            if r['grounding_mode']=='repair':r['grounding_repairs']=0
        self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['by_policy']['repair']['measures']['grounding_sent_repairs']['exact_all_condition_total'],2)
        self.assertEqual(out['by_policy']['repair']['measures']['grounding_repairs']['exact_all_condition_total'],0)
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_unknown_keeps_known_subtotals_and_nulls_component_exact_values(self):
        self.rows[0]['unknown_usage_calls']=1;self.refresh();out=reporting.build(self.root)
        total=out['all_conditions'];self.assertEqual(total['known_token_subtotal'],580)
        self.assertIsNone(total['exact_total_tokens'])
        for key in ('input_tokens','output_tokens','cached_input_tokens'):
            self.assertIsNone(total['measures'][key]['exact_all_condition_total'])
        self.assertEqual(total['measures']['api_requests']['exact_all_condition_total'],12)
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_primary_and_auxiliary_common_success_are_different_sets(self):
        self.by(1,'off')['success']=False
        self.by(2,'feedback')['success']=False
        self.refresh();out=reporting.build(self.root)
        a=out['comparison_costs']['feedback']['outcome_groups'];b=out['comparison_costs']['off']['outcome_groups']
        self.assertEqual(a['common_success']['pairs'],1);self.assertEqual(a['quality_gain']['pairs'],1)
        self.assertEqual(b['common_success']['pairs'],1);self.assertEqual(b['quality_gain']['pairs'],1)
        self.assertEqual(out['by_replication']['1']['comparisons']['feedback']['outcome_groups']['common_success']['pairs'],1)
        self.assertEqual(out['by_replication']['1']['comparisons']['off']['outcome_groups']['common_success']['pairs'],0)
    def test_quality_gain_alone_has_no_common_success_token_gate(self):
        for r in self.rows:
            if r['grounding_mode']!='repair':r['success']=False
        self.refresh();out=reporting.build(self.root)
        groups=out['comparison_costs']['feedback']['outcome_groups']
        self.assertEqual(groups['quality_gain']['pairs'],2)
        self.assertIsNone(groups['common_success']['by_policy']['repair']['exact_total_tokens'])
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_cheap_failure_and_auxiliary_success_loss_are_retained(self):
        self.by(1,'feedback')['success']=False
        r=self.by(1,'repair');r.update(success=False,input_tokens=0,output_tokens=1,known_total_tokens=1)
        self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['comparison_costs']['feedback']['outcome_groups']['both_failed']['pairs'],1)
        self.assertEqual(out['comparison_costs']['off']['outcome_groups']['quality_loss']['pairs'],1)
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_contract_stop_and_official_success_can_coexist(self):
        self.by(1,'repair').update(grounding_contract_failed=True,grounding_accounting_complete=False)
        self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['all_conditions']['successful_conditions'],6)
        self.assertFalse(out['audited_criteria']['mechanism_contracts_intact'])
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_aggregate_gate_does_not_silently_require_each_seed_token_gain(self):
        self.by(1,'repair').update(input_tokens=10,known_total_tokens=30)
        self.by(2,'repair').update(input_tokens=90,known_total_tokens=110)
        self.refresh();out=reporting.build(self.root)
        self.assertTrue(out['audited_criteria']['development_gate_met'])
        self.assertFalse(out['audited_criteria']['comparisons']['feedback']['every_seed_tokens_lower'])
        self.assertEqual(out['by_replication']['2']['by_policy']['repair']['exact_total_tokens'],110)
    def test_missing_slot_measurements_remain_null_not_zero(self):
        row={k:self.rows[0][k] for k in ('run_id','task_id','replication','model_seed','grounding_mode','projection_policy','checkpoint_policy')}
        row.update(record_status='audit_error',success=None,known_total_tokens=None,unknown_usage_calls=None,projection_contract_failed=None,grounding_contract_failed=None,grounding_repairs=None)
        self.rows[0]=row;self.refresh();out=reporting.build(self.root)
        self.assertEqual(len(out['conditions']),6)
        self.assertEqual(out['all_conditions']['accounted_conditions'],5)
        self.assertIsNone(out['conditions'][0]['grounding_repairs']);self.assertIsNone(out['all_conditions']['exact_total_tokens'])
        self.assertEqual(out['comparison_costs']['off']['outcome_groups']['not_both_evaluated']['pairs'],1)
    def test_partial_grounding_accounting_keeps_known_counts_without_exact_total(self):
        self.by(1,'repair').update(grounding_accounting_complete=False,grounding_pending_notices=1)
        self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['by_policy']['repair']['measures']['grounding_repairs']['known_subtotal'],2)
        self.assertIsNone(out['by_policy']['repair']['measures']['grounding_repairs']['exact_all_condition_total'])
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_invalid_counts_bool_mode_and_source_binding_are_rejected(self):
        original=deepcopy(self.rows)
        for case in ('missing','seed_bool','repair_count','off_repair','ledger_mapping','source'):
            self.rows=deepcopy(original);self.refresh()
            if case=='missing':self.report['rows'].pop()
            elif case=='seed_bool':self.report['rows'][0]['replication']=True
            elif case=='repair_count':self.report['rows'][2]['grounding_repairs']=2
            elif case=='off_repair':self.report['rows'][0]['grounding_repair_attempts']=1
            elif case=='ledger_mapping':self.report['rows'][2]['grounding_runtime']['grounding_repairs']=0
            else:(self.root/reporting.HELPER).write_text('# modified\n')
            self.write(reporting.AUDIT,self.report)
            s=json.loads((self.root/reporting.SESSION).read_text());s['audit_source_sha256']=reporting.sha(self.root/reporting.AUDIT);self.write(reporting.SESSION,s)
            with self.subTest(case=case),self.assertRaises(ValueError):reporting.build(self.root)


class OutputGroundingSessionTests(unittest.TestCase):
    def test_unstarted_versus_missing_measurement_and_timing_overlap(self):
        r=session.cell_time_totals([dict(record_status='not_run'),dict(record_status='evaluated',full_wall_seconds=0.),dict(record_status='incomplete_worker')])
        self.assertEqual(r['known_cell_full_wall_seconds'],0.);self.assertEqual(r['unknown_cell_full_wall_count'],1);self.assertIsNone(r['cell_full_wall_seconds'])
        self.assertEqual(session.attempt_time_totals([{'evaluation_started_at':'synthetic'},{'evaluation_wall_seconds':0.},{}],'evaluation'),dict(known_subtotal=0.,unknown_attempts=1,attempts=2,exact_total=None))
    def test_invalid_timing_is_unknown(self):
        for value in (-1,True,float('nan')):
            self.assertIsNone(session.cell_time_totals([dict(record_status='evaluated',full_wall_seconds=value)])['cell_full_wall_seconds'])
    def test_session_checks_all_six_exact_identities_before_process_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'records/context_pilot/P129_pipeline_v01';folder.mkdir(parents=True)
            for name,value in [('status.json',dict(status='complete',server_stopped=True,server_supervisor_pid=1)),('server_final.json',dict(status='stopped',supervisor_pid=1))]:
                (folder/name).write_text(json.dumps(value))
            report=dict(audit_errors=[],rows=[dict(run_id=session.cell_id(rep,n,mode),replication=rep,model_seed=session.SEEDS[rep-1],grounding_mode=mode) for rep,n,mode in session.run_order()],owned_processes_absent=True,pipeline_status_sha256=session.sha(folder/'status.json'),server_final_sha256=session.sha(folder/'server_final.json'))
            report['rows'][0]['grounding_mode']='repair'
            target=root/'reports';target.mkdir();(target/'P129_comparison.json').write_text(json.dumps(report))
            with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run') as process:
                with self.assertRaisesRegex(ValueError,'all_six_fixed'):session.inspect(root)
                process.assert_not_called()
    def test_closed_session_keeps_missing_started_costs_and_all_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'records/context_pilot/P129_pipeline_v01'
            record=root/'records/p2_servers/synthetic'
            def write(path,value):
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(value)+'\n')
            state=dict(status='stopped',server_stopped=True,server_supervisor_pid=2,
                       wall_seconds=100,stages=[dict(mode='batch',wall_seconds=90)])
            server=dict(status='stopped',stop_reason='synthetic',pid=1,supervisor_pid=2,
                record_directory=str(record),started_at='synthetic',wall_seconds=100,
                load_wall_seconds=1,sampled_peak_rss_bytes=0,peak_system_swap_bytes=0,
                exit_code=0,model_revision='synthetic',runtime='synthetic',ctx_size=65536,
                cache_type_k='synthetic',cache_type_v='synthetic',memory_note='synthetic')
            write(folder/'status.json',state);write(folder/'server_final.json',server)
            write(record/'summary.json',server);write(record/'memory.jsonl',dict(swap_used_bytes=0))
            rows=[dict(run_id=session.cell_id(rep,n,mode),replication=rep,
                model_seed=session.SEEDS[rep-1],grounding_mode=mode,
                record_status='evaluated',full_wall_seconds=10)
                for rep,n,mode in session.run_order()]
            rows[-1].pop('full_wall_seconds');rows[-1]['record_status']='incomplete_worker'
            write(root/'reports/P129_comparison.json',dict(rows=rows,audit_errors=[{'type':'synthetic'}],
                owned_processes_absent=True,pipeline_status_sha256=session.sha(folder/'status.json'),
                server_final_sha256=session.sha(folder/'server_final.json')))
            write(root/'records/context_pilot/P129_batch_v01/status.json',dict(
                rows=[dict(evaluation_wall_seconds=2),dict(evaluation_started_at='synthetic')],
                completed=['synthetic']))
            with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run',
                    return_value=SimpleNamespace(returncode=1,stdout='')) as process:
                result=session.inspect(root)
            self.assertEqual(process.call_count,2)
            self.assertEqual(result['known_cell_full_wall_seconds'],50)
            self.assertEqual(result['unknown_cell_full_wall_count'],1)
            self.assertIsNone(result['cell_full_wall_seconds'])
            self.assertIsNone(result['batch_other_wall_seconds'])
            self.assertEqual(result['known_evaluation_wall_seconds'],2)
            self.assertEqual(result['unknown_evaluation_wall_count'],1)
            self.assertIsNone(result['evaluation_wall_seconds'])
            self.assertEqual(result['cell_audit_error_count'],1)


if __name__=='__main__':unittest.main()

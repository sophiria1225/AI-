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
import build_receipt_disclosure_summary as reporting
import inspect_whole_task_receipt_disclosure_session as session


class ReceiptReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        p=patch.object(reporting,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        for name in (reporting.BUILDER,reporting.AUDITOR,reporting.INSPECTOR,reporting.HELPER):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# synthetic source\n')
        self.write(reporting.PREFLIGHT,{'synthetic':True})
        sources={n:reporting.sha(self.root/n) for n in (reporting.BUILDER,reporting.AUDITOR,reporting.INSPECTOR,reporting.HELPER)}
        self.plan=dict(experiment='P128',receipt_modes=list(reporting.POLICIES),model_seeds=list(reporting.SEEDS),known_tasks=[{'task_id':f'synthetic-{n}'} for n in range(1,5)],source_sha256=sources)
        self.write(reporting.PLAN,self.plan)
        self.write(reporting.ACTIVATION,dict(source_hashes=sources,preflight_sha256=reporting.sha(self.root/reporting.PREFLIGHT)))
        self.rows=[self.row(rep,n,mode) for rep,n,mode in reporting.run_order()]
        self.refresh()
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value)+'\n')
    def row(self,rep,n,mode):
        d=mode=='disclose';rt={k:0 for k in reporting.RUNTIME_COUNTS};rt.update({k:0.01 for k in reporting.RUNTIME_TIMES});rt.update({k:True for k in reporting.RUNTIME_FLAGS})
        rt.update(policy='explicit_joined_fields',projection_failed=False,program_attempts=2,program_evidence_records=2,explicit_field_interface_shared_between_policies=True,joined_provider_shared_between_policies=True)
        receipt=dict(mode=mode,closed_turns=2,eligible_turns=1,disclosed_turns=int(d),receipt_read_span_actions=1,receipt_read_span_returned_characters=100,removed_receipt_UTF8_bytes=100*int(d),snapshot_sha256='f'*64,disclosure_contract_intact=True,sidecar_complete=True)
        return dict(run_id=reporting.cell_id(rep,n,mode),task_id=f'synthetic-{n}',replication=rep,model_seed=reporting.SEEDS[rep-1],receipt_mode=mode,projection_policy='explicit_joined_fields',checkpoint_policy='rolling_separate',record_status='evaluated',success=True,stop_reason='completed',model_calls=2,known_total_tokens=90 if d else 100,unknown_usage_calls=0,api_requests=2,input_tokens=70 if d else 80,output_tokens=20,cached_input_tokens=0,projection_hits=0,setup_wall_seconds=.1,wall_seconds=1.0,cleanup_wall_seconds=.2,full_wall_seconds=1.3,checkpoint_installed=False,checkpoint_opportunity=0,checkpoint_installations=0,projection_contract_failed=False,projection_runtime=rt,receipt_disclosure=receipt,receipt_disclosures=int(d),receipt_disclosed_turns=int(d),receipt_disclosure_contract_failed=False,receipt_disclosure_contract_intact=True,receipt_disclosure_audit_complete=True,summary_sha256='a'*64,usage_sha256='b'*64,evaluation_sha256='c'*64)
    def refresh(self):
        self.report=dict(phase='P128',batch_status='complete',rows=self.rows,owned_processes_absent=True,audit_errors=[],plan_sha256=reporting.sha(self.root/reporting.PLAN),activation_sha256=reporting.sha(self.root/reporting.ACTIVATION),auditor_sha256=reporting.sha(self.root/reporting.AUDITOR),pipeline_status_sha256='d'*64,server_final_sha256='e'*64,**reporting.summarize(self.rows,[]))
        self.write(reporting.AUDIT,self.report)
        self.write(reporting.SESSION,dict(phase='P128',status='stopped',owned_processes_absent=True,pipeline_source_sha256='d'*64,source_sha256='e'*64,inspector_sha256=reporting.sha(self.root/reporting.INSPECTOR),audit_source_sha256=reporting.sha(self.root/reporting.AUDIT),wall_seconds=30))
    def test_full_sixteen_publication_and_no_private_body_or_overwrite(self):
        self.rows[0]['private_prompt']='PRIVATE_SENTINEL';self.rows[0]['receipt_disclosure']['private_value']='PRIVATE_SENTINEL';self.refresh()
        result=reporting.build(self.root);target=self.root/reporting.TARGET
        self.assertEqual(result['all_conditions']['exact_total_tokens'],1520)
        self.assertEqual(result['common_successful_task_seed_pairs'],8)
        self.assertEqual(result['independent_tasks'],4);self.assertEqual(result['repetitions'],2)
        self.assertTrue(result['audited_criteria']['development_gate_met'])
        self.assertEqual(result['by_replication']['1']['all_conditions']['exact_total_tokens'],760)
        self.assertEqual(result['by_replication']['2']['by_policy']['disclose']['exact_total_tokens'],360)
        with (target/'conditions.csv').open() as f:self.assertEqual(len(list(csv.DictReader(f))),16)
        self.assertNotIn('PRIVATE_SENTINEL',''.join(p.read_text() for p in target.iterdir()))
        before={p.name:p.read_bytes() for p in target.iterdir()}
        with self.assertRaises(FileExistsError):reporting.build(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in target.iterdir()})
    def test_final_only_disclosure_is_not_paid_model_exposure(self):
        for row in self.rows:
            if row['receipt_mode']=='disclose':row['receipt_disclosures']=0
        self.refresh();r=reporting.build(self.root)
        exposed=r['by_policy']['disclose']['measures']['receipt_disclosures']
        final=r['by_policy']['disclose']['measures']['receipt_disclosed_turns']
        self.assertEqual(exposed['exact_all_condition_total'],0)
        self.assertEqual(final['exact_all_condition_total'],8)
        self.assertFalse(r['audited_criteria']['development_gate_met'])

    def test_unknown_components_never_become_exact_when_rows_have_numeric_subtotals(self):
        self.rows[0]['unknown_usage_calls']=1;self.refresh();r=reporting.build(self.root)
        self.assertIsNone(r['all_conditions']['exact_total_tokens'])
        for k in ('input_tokens','output_tokens','cached_input_tokens'):
            self.assertIsNone(r['all_conditions']['measures'][k]['exact_all_condition_total'])
        self.assertEqual(r['all_conditions']['known_token_subtotal'],1520)
        self.assertEqual(r['all_conditions']['measures']['api_requests']['exact_all_condition_total'],32)
        self.assertFalse(r['audited_criteria']['development_gate_met'])
    def test_one_seed_cannot_mask_other_seed_loss(self):
        for row in self.rows:
            if row['receipt_mode']=='disclose':row.update(input_tokens=10 if row['replication']==1 else 90,known_total_tokens=30 if row['replication']==1 else 110)
        self.refresh();r=reporting.build(self.root)
        self.assertLess(r['audited_criteria']['disclose_minus_full_whole_task_tokens'],0)
        self.assertFalse(r['audited_criteria']['development_gate_met'])
        self.assertGreater(r['audited_criteria']['per_seed'][1]['paired_successful_token_difference'],0)
    def test_missing_audit_error_kept_as_one_of_sixteen(self):
        original=self.rows[0];row={k:original[k] for k in ('run_id','task_id','replication','model_seed','receipt_mode','projection_policy','checkpoint_policy')}
        row.update(record_status='audit_error',success=None,known_total_tokens=None,unknown_usage_calls=None,projection_hits=None,projection_contract_failed=None,receipt_disclosures=None,receipt_disclosure_contract_failed=None)
        self.rows[0]=row;self.refresh();r=reporting.build(self.root)
        self.assertEqual(len(r['conditions']),16);self.assertEqual(r['all_conditions']['accounted_conditions'],15)
        self.assertIsNone(r['conditions'][0]['receipt_disclosures']);self.assertIsNone(r['all_conditions']['exact_total_tokens'])
        self.assertFalse(r['audited_criteria']['development_gate_met'])
    def test_common_success_is_scoped_to_replication(self):
        self.rows[1]['success']=False;self.refresh();r=reporting.build(self.root)
        self.assertEqual(r['common_successful_task_seed_pairs'],7)
        self.assertEqual(r['by_replication']['1']['common_success_task_pairs'],3)
        self.assertEqual(r['by_replication']['2']['common_success_task_pairs'],4)
        self.assertEqual(r['common_success_costs_by_policy']['full']['exact_total_tokens'],700)
    def test_missing_cached_measurement_and_zero_known_unknown_call(self):
        self.rows[0].update(input_tokens=0,output_tokens=0,known_total_tokens=0,unknown_usage_calls=1,cached_input_tokens=0)
        self.rows[1]['cached_input_tokens']=None;self.refresh();r=reporting.build(self.root)
        self.assertIsNone(r['all_conditions']['measures']['cached_input_tokens']['exact_all_condition_total'])
        self.assertIsNone(r['all_conditions']['measures']['input_tokens']['exact_all_condition_total'])
        self.assertEqual(r['conditions'][0]['known_total_tokens'],0);self.assertIsNone(r['conditions'][0]['exact_total_tokens'])
    def test_identity_field_tamper_and_frozen_source_rejected(self):
        original=deepcopy(self.rows)
        for case in ('missing','seed','mode','receipt_count','source'):
            self.rows=deepcopy(original);self.refresh()
            if case=='missing':self.report['rows'].pop()
            elif case=='seed':self.report['rows'][0]['model_seed']=999
            elif case=='mode':self.report['rows'][0]['receipt_mode']='disclose'
            elif case=='receipt_count':self.report['rows'][0]['receipt_disclosure']['disclosed_turns']=9
            else:(self.root/reporting.HELPER).write_text('# changed\n')
            self.write(reporting.AUDIT,self.report)
            s=json.loads((self.root/reporting.SESSION).read_text());s['audit_source_sha256']=reporting.sha(self.root/reporting.AUDIT);self.write(reporting.SESSION,s)
            with self.subTest(case=case),self.assertRaises(ValueError):reporting.build(self.root)


class ReceiptSessionTests(unittest.TestCase):
    def test_unstarted_versus_unknown_and_overlapping_time(self):
        r=session.cell_time_totals([dict(record_status='not_run'),dict(record_status='evaluated',full_wall_seconds=0.0),dict(record_status='incomplete_worker')])
        self.assertEqual(r['known_cell_full_wall_seconds'],0.0);self.assertEqual(r['unknown_cell_full_wall_count'],1);self.assertIsNone(r['cell_full_wall_seconds'])
        a=session.attempt_time_totals([{'evaluation_started_at':'fixture'}, {'evaluation_wall_seconds':0.0}, {}],'evaluation')
        self.assertEqual(a,dict(known_subtotal=0.0,unknown_attempts=1,attempts=2,exact_total=None))
    def test_negative_bool_nan_timings_remain_unknown(self):
        for v in (-1,True,float('nan')):
            self.assertIsNone(session.cell_time_totals([dict(record_status='evaluated',full_wall_seconds=v)])['cell_full_wall_seconds'])
            self.assertIsNone(session.attempt_time_totals([dict(evaluation_wall_seconds=v)],'evaluation')['exact_total'])


if __name__=='__main__':unittest.main()

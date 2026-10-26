"""P130 public data-only reporting from bounded handwritten audited rows."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_p130_report as reporting


class P130ReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        p=patch.object(reporting,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        for name in (reporting.BUILDER,reporting.AUDITOR,reporting.INSPECTOR,reporting.HELPER):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# synthetic source\n')
        self.write(reporting.PREFLIGHT,{'synthetic':True})
        sources={n:reporting.sha(self.root/n) for n in (reporting.BUILDER,reporting.AUDITOR,reporting.INSPECTOR,reporting.HELPER)}
        self.write(reporting.PLAN,dict(experiment='P130',inventory_modes=list(reporting.POLICIES),grounding_mode='feedback',
            model_seeds=list(reporting.SEEDS),known_tasks=[{'task_id':'synthetic-CSV'}],source_sha256=sources))
        self.write(reporting.ACTIVATION,dict(source_hashes=sources,preflight_sha256=reporting.sha(self.root/reporting.PREFLIGHT)))
        self.rows=[self.row(rep,n,mode) for rep,n,mode in reporting.run_order()];self.refresh()
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value)+'\n')
    def row(self,rep,n,mode):
        shown=mode=='checkpoint_inventory';rt={k:0 for k in reporting.RUNTIME_COUNTS}
        rt.update({k:.01 for k in reporting.RUNTIME_TIMES});rt.update({k:True for k in reporting.RUNTIME_FLAGS})
        rt.update(policy='explicit_joined_fields',projection_failed=False,program_attempts=2,program_evidence_records=2,
            explicit_field_interface_shared_between_policies=True,joined_provider_shared_between_policies=True)
        row=dict(run_id=reporting.cell_id(rep,n,mode),task_id='synthetic-CSV',replication=rep,model_seed=reporting.SEEDS[rep-1],
            inventory_mode=mode,grounding_mode='feedback',projection_policy='explicit_joined_fields',checkpoint_policy='rolling_separate',
            record_status='evaluated',success=True,stop_reason='completed',model_calls=2,known_total_tokens=90 if shown else 100,
            unknown_usage_calls=0,api_requests=2,input_tokens=70 if shown else 80,output_tokens=20,cached_input_tokens=0,projection_hits=0,
            setup_wall_seconds=.1,wall_seconds=1.,cleanup_wall_seconds=.2,full_wall_seconds=1.3,checkpoint_installed=True,
            checkpoint_opportunity=1,checkpoint_installations=1,projection_contract_failed=False,projection_runtime=rt,
            summary_sha256='a'*64,usage_sha256='b'*64,evaluation_sha256='c'*64)
        row.update({k:0 for k in reporting.GROUNDING_COUNTS})
        row.update(grounding_write_checks=1,grounding_feedback_blocks=1,grounding_contract_failed=False,
            grounding_accounting_complete=True,grounding_wall_seconds=.02,grounding_ledger_sha256='f'*64,
            inventory_notice_actor_calls=int(shown),inventory_captures=1,inventory_capture_wall_seconds=.03,
            inventory_request_bytes=80,inventory_response_bytes=100,inventory_contract_failed=False,inventory_accounting_complete=True)
        return row
    def refresh(self):
        for r in self.rows:
            if r['record_status'] in ('evaluated','unevaluated'):
                r['grounding_runtime']={v:r[k] for k,v in reporting.GROUNDING_MAP.items()}
                r['grounding_runtime'].update(mode='feedback',contract_intact=not r['grounding_contract_failed'])
                r['inventory_runtime']=dict(mode=r['inventory_mode'],contract_failed=r['inventory_contract_failed'],
                    actual_inventory_exposures=r['inventory_notice_actor_calls'],dispatched_actor_views=2,
                    raw_archive_unchanged=True,focus_requests_unchanged=True,all_model_roles_and_inventory_input_share_budget=True,
                    disclosure_activity_requires_actual_dispatch=True,capture=dict(captures=r['inventory_captures'],
                        successful_captures=1,known_request_bytes=r['inventory_request_bytes'],known_response_bytes=r['inventory_response_bytes'],
                        capture_wall_seconds=r['inventory_capture_wall_seconds'],capture_accounting_complete=True,
                        values_disclosed=False,scalar_lengths_disclosed=False,environment_API_requests=0,model_calls=0))
        self.report=dict(phase='P130',batch_status='complete',rows=self.rows,owned_processes_absent=True,audit_errors=[],
            plan_sha256=reporting.sha(self.root/reporting.PLAN),activation_sha256=reporting.sha(self.root/reporting.ACTIVATION),
            auditor_sha256=reporting.sha(self.root/reporting.AUDITOR),pipeline_status_sha256='d'*64,server_final_sha256='e'*64,
            **reporting.summarize(self.rows,[]));self.persist()
    def persist(self):
        self.write(reporting.AUDIT,self.report)
        self.write(reporting.SESSION,dict(phase='P130',status='stopped',owned_processes_absent=True,pipeline_source_sha256='d'*64,
            source_sha256='e'*64,inspector_sha256=reporting.sha(self.root/reporting.INSPECTOR),
            audit_source_sha256=reporting.sha(self.root/reporting.AUDIT),wall_seconds=30))
    def by(self,rep,mode):return next(r for r in self.rows if r['replication']==rep and r['inventory_mode']==mode)
    def test_four_rows_shared_costs_privacy_and_exclusive_publication(self):
        self.rows[0]['inventory_runtime']['private_names_values']='PRIVATE_SENTINEL';self.persist()
        out=reporting.build(self.root);target=self.root/reporting.TARGET
        self.assertEqual(out['all_conditions']['exact_total_tokens'],380)
        self.assertEqual(out['independent_tasks'],1);self.assertTrue(out['audited_criteria']['development_gate_met'])
        self.assertEqual(out['by_policy']['off']['measures']['inventory_captures']['exact_all_condition_total'],2)
        self.assertEqual(out['by_policy']['off']['measures']['inventory_notice_actor_calls']['exact_all_condition_total'],0)
        self.assertEqual(out['by_policy']['checkpoint_inventory']['measures']['inventory_notice_actor_calls']['exact_all_condition_total'],2)
        self.assertEqual(out['comparison_costs']['outcome_groups']['common_success']['pairs'],2)
        with (target/'conditions.csv').open() as f:self.assertEqual(len(list(csv.DictReader(f))),4)
        self.assertNotIn('PRIVATE_SENTINEL',''.join(p.read_text() for p in target.iterdir()))
        before={p.name:p.read_bytes() for p in target.iterdir()}
        with self.assertRaises(FileExistsError):reporting.build(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in target.iterdir()})
    def test_prepared_capture_without_actual_input_is_not_gate_activity(self):
        for r in self.rows:r['inventory_notice_actor_calls']=0
        self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['all_conditions']['measures']['inventory_captures']['exact_all_condition_total'],4)
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_unknown_cost_retains_exposure_and_null_exact_component_totals(self):
        self.by(1,'checkpoint_inventory')['unknown_usage_calls']=1;self.refresh();out=reporting.build(self.root)
        total=out['all_conditions'];self.assertEqual(total['known_token_subtotal'],380)
        self.assertIsNone(total['exact_total_tokens'])
        for key in ('input_tokens','output_tokens','cached_input_tokens'):self.assertIsNone(total['measures'][key]['exact_all_condition_total'])
        self.assertEqual(total['measures']['inventory_notice_actor_calls']['known_subtotal'],2)
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_quality_gain_and_cheap_failure_are_separate_from_common_success(self):
        self.by(1,'off')['success']=False
        r=self.by(2,'checkpoint_inventory');r.update(success=False,input_tokens=0,output_tokens=1,known_total_tokens=1)
        self.refresh();out=reporting.build(self.root);groups=out['comparison_costs']['outcome_groups']
        self.assertEqual(groups['quality_gain']['pairs'],1);self.assertEqual(groups['quality_loss']['pairs'],1)
        self.assertIsNone(groups['common_success']['by_policy']['checkpoint_inventory']['exact_total_tokens'])
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_contract_stop_keeps_official_success_and_known_counts(self):
        r=self.by(1,'checkpoint_inventory');r.update(inventory_contract_failed=True,inventory_accounting_complete=False)
        self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['all_conditions']['successful_conditions'],4)
        self.assertEqual(out['all_conditions']['measures']['inventory_captures']['known_subtotal'],4)
        self.assertIsNone(out['all_conditions']['measures']['inventory_captures']['exact_all_condition_total'])
        self.assertFalse(out['audited_criteria']['mechanism_contracts_intact']);self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_shared_grounding_or_projection_failure_prevents_gate_without_erasing_cost(self):
        r=self.by(1,'off');r.update(grounding_contract_failed=True,grounding_accounting_complete=False,projection_contract_failed=True)
        r['projection_runtime']['projection_failed']=True;self.refresh();out=reporting.build(self.root)
        self.assertEqual(out['all_conditions']['exact_total_tokens'],380)
        self.assertFalse(out['audited_criteria']['development_gate_met'])
    def test_missing_cells_keep_all_slots_and_nulls(self):
        for status in ('not_run','incomplete_worker','audit_error','unevaluated'):
            original=deepcopy(self.rows)
            r=self.rows[0]
            if status=='unevaluated':r.update(record_status=status,success=None,evaluation_sha256=None)
            else:
                self.rows[0]={k:r[k] for k in ('run_id','task_id','replication','model_seed','inventory_mode','grounding_mode','projection_policy','checkpoint_policy')}
                self.rows[0].update(record_status=status,success=None)
            self.refresh();out=reporting.build(self.root)
            self.assertEqual(len(out['conditions']),4);self.assertFalse(out['audited_criteria']['development_gate_met'])
            if status!='unevaluated':
                self.assertIsNone(out['conditions'][0]['inventory_notice_actor_calls']);self.assertIsNone(out['all_conditions']['exact_total_tokens'])
            import shutil;shutil.rmtree(self.root/reporting.TARGET);self.rows=original
    def test_per_seed_costs_remain_visible_without_new_gate_condition(self):
        self.by(1,'checkpoint_inventory').update(input_tokens=10,known_total_tokens=30)
        self.by(2,'checkpoint_inventory').update(input_tokens=90,known_total_tokens=110)
        self.refresh();out=reporting.build(self.root)
        self.assertTrue(out['audited_criteria']['development_gate_met'])
        self.assertEqual(out['by_replication']['2']['by_policy']['checkpoint_inventory']['exact_total_tokens'],110)
    def test_counts_scope_mapping_and_exaggerated_claims_rejected(self):
        original=deepcopy(self.rows)
        for case in ('missing','seed_bool','off_exposure','exposure_count','runtime_mapping','raw_values','feedback_changed','gate_claim','source','root'):
            self.rows=deepcopy(original);self.refresh();r=self.rows[1]
            if case=='missing':self.report['rows'].pop()
            elif case=='seed_bool':r['replication']=True
            elif case=='off_exposure':self.rows[0]['inventory_notice_actor_calls']=1
            elif case=='exposure_count':r['inventory_notice_actor_calls']=2
            elif case=='runtime_mapping':r['inventory_runtime']['actual_inventory_exposures']=0
            elif case=='raw_values':r['inventory_runtime']['capture']['values_disclosed']=True
            elif case=='feedback_changed':r['grounding_mode']='repair'
            elif case=='gate_claim':self.report['novel_method_claim']=True
            elif case=='source':(self.root/reporting.HELPER).write_text('# changed\n')
            self.persist()
            with self.subTest(case=case),self.assertRaises(ValueError):reporting.build(self.root/'other' if case=='root' else self.root)
            if case=='source':(self.root/reporting.HELPER).write_text('# synthetic source\n')
    def test_rolling_opportunity_types_and_known_zero_are_preserved(self):
        for value in (0,1,3):
            r=deepcopy(self.rows[0]);r.update(checkpoint_opportunity=value,checkpoint_installations=min(1,value),checkpoint_installed=bool(value))
            r['inventory_captures']=min(1,value);r['inventory_runtime']['capture'].update(captures=min(1,value),successful_captures=min(1,value))
            self.assertEqual(reporting.public_row(r)['checkpoint_opportunity'],value)
        for value in (None,False,1.0,'1'):
            r=deepcopy(self.rows[0]);r['checkpoint_opportunity']=value
            with self.assertRaises(ValueError):reporting.public_row(r)


    def test_real_synthetic_worker_auditor_rows_fit_public_schema(self):
        # Exercise the actual producer shapes using handwritten synthetic data;
        # the saved Python is never replayed by either audit or report code.
        from test_whole_task_checkpoint_inventory_worker import fixture, ROOT
        from test_whole_task_output_grounding_audit import transport_records
        from joined_public_read_views import JOINED_CONTRACT_ID
        from public_output_grounding import PUBLIC_CONTRACT_ID
        from audit_whole_task_checkpoint_inventory import audit_cell
        from whole_task_checkpoint_inventory import initial_conversation
        from budget_signal import digest
        for mode,unknown in (('off',False),('checkpoint_inventory',False),('checkpoint_inventory',True)):
            with self.subTest(mode=mode,unknown=unknown),tempfile.TemporaryDirectory() as temp:
                data=fixture(Path(temp),mode,checkpoint=True,unknown_after_inventory=unknown)
                transport_records(data);folder=data['folder'];config=json.loads((folder/'plan.json').read_text())
                conv=initial_conversation(data['original'],data['public'])
                pre=dict(base_messages_sha256=digest(conv.for_model(config['observation_page_characters'])[0]))
                with patch('region_projection_runtime.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
                     patch('demand_joined_read_adapter.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
                     patch('audit_output_grounding_runtime.verify_public_export_sources',return_value=PUBLIC_CONTRACT_ID), \
                     patch('audit_checkpoint_inventory_trace.expected_inventory_python',return_value=sys.version.split()[0]):
                    row=audit_cell(folder,ROOT,data['plan'],data['original'],data['item'],mode,1,pre,False,tools=data['tools'])
                public=reporting.public_row(row)
                self.assertEqual(public['inventory_notice_actor_calls'],row['inventory_notice_actor_calls'])
                self.assertNotIn('inventory_runtime',public)
                self.assertEqual(public['unknown_usage_calls'],int(unknown))
                self.assertEqual(public['exact_total_tokens'],None if unknown else row['known_total_tokens'])


if __name__=='__main__':unittest.main()

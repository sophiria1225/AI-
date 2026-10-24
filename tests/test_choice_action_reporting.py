import copy
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit_choice_action_execution as audit
import build_choice_action_execution_report as reporting
from choice_action_execution import FIXED, execution_comparisons, source_slots
from choice_context_replay import schedule
from run_saved_action_execution import write, sha
from test_choice_action_execution import source_fixture

ROOT=Path(__file__).resolve().parents[1]


def fixture_values(known=36,unknown=False,stop_at=None):
    source=source_fixture(known=known,unknown=unknown)
    for row in source['rows']:
        if row['record_status']=='audited':row['structure']={'tool_calls':1}
    rows=[]
    for index,slot in enumerate(source_slots(source)):
        row=dict(slot,status='not_attempted',prefix_programs=[],prefix_api_requests=0,public_prefix_matched=False)
        if stop_at is not None and index>=stop_at:
            if index==stop_at:row.update(status='stopped',typed_requests_started=1,saved_program_executions=1,
                prefix_api_requests=1,active_wall_seconds=1.,cleanup_wall_seconds=.1,full_wall_seconds=1.1)
        elif not slot['should_execute']:row['status']='source_unavailable'
        else:
            row.update(status='complete',prefix_programs=[{'public_prefix_matches':True} for _ in range(12)],
                prefix_api_requests=28,public_prefix_matched=True,structured_submissions=1,
                suffix_saved_programs=1,saved_program_executions=13,suffix_api_requests=1,
                suffix_request_sequence_sha256='a'*64,suffix_execution_evidence_sha256='b'*64,
                transport_attempts=29,typed_requests_started=29,typed_status_counts={'returned':29},
                cleanup_errors=[],owned_bridge_absent=True,python_cleanup={'container_removed':True},
                bridge_cleanup={'graceful':True},container_controls={str(i):True for i in range(14)},
                active_wall_seconds=1.,cleanup_wall_seconds=.1,full_wall_seconds=1.1,
                suffix_public_results=[{'status':'ok','format_error_present':False}])
        rows.append(row)
    plan=dict(FIXED,schedule=schedule(),execution_ready=True,source_sha256={})
    report=dict(phase='P102',status='stopped' if stop_at is not None else 'complete',conditions=rows,
        model_generations=0,evaluator_calls=0,reserved_scenarios_read=0,automatic_retries=0,
        original_full_state_restored=False,task_quality_measured=False,new_method_claim=False,
        available_saved_outputs=known,completed_conditions=sum(r['status']=='complete' for r in rows),
        unavailable_source_slots=sum(r['status']=='source_unavailable' for r in rows),
        unattempted_execution_slots=sum(r['status']=='not_attempted' for r in rows),
        environment_api_requests=sum(r.get('typed_requests_started',0) for r in rows),
        saved_program_executions=sum(r.get('saved_program_executions',0) for r in rows),
        execution_comparisons=execution_comparisons(rows),wall_seconds=41.)
    return plan,source,report


def reporting_fixture(root,**kwargs):
    plan,source,report=fixture_values(**kwargs)
    for name in ('configs','reports','scripts'):(root/name).mkdir(parents=True)
    write(root/audit.PLAN,plan);write(root/audit.SOURCE,source)
    report.update(plan_sha256=sha(root/audit.PLAN),source_audit_sha256=sha(root/audit.SOURCE))
    write(root/audit.REPORT,report)
    path='scripts/audit_choice_action_execution.py';shutil.copyfile(ROOT/path,root/path)
    write(root/audit.AUDIT,dict(status='complete',audit_errors=[],checked_slots=36,
        auditor_sha256=sha(root/path),wall_seconds=.2,
        source_sha256={n:sha(root/n) for n in (audit.PLAN,audit.SOURCE,audit.REPORT)}))
    return plan,source,report


class ChoiceActionReportingTests(unittest.TestCase):
    def test_complete_all_slots_and_pair_denominators(self):
        plan,source,report=fixture_values();audit.validate_closed(plan,source,report)
        self.assertEqual(report['environment_api_requests'],1044)
        self.assertEqual(len(report['execution_comparisons']['cross']),66)

    def test_source_unknown_and_unattempted_are_not_regenerated(self):
        plan,source,report=fixture_values(known=3,unknown=True)
        audit.validate_closed(plan,source,report)
        self.assertEqual(report['completed_conditions'],3)
        self.assertEqual(report['unavailable_source_slots'],33)
        self.assertIsNone(report['conditions'][3]['source_known_total_tokens'])

    def test_stopped_prefix_costs_and_all_later_slots_remain(self):
        plan,source,report=fixture_values(stop_at=1);audit.validate_closed(plan,source,report)
        self.assertEqual(report['environment_api_requests'],30)
        self.assertEqual(report['unattempted_execution_slots'],34)
        changed=copy.deepcopy(report);changed['environment_api_requests']-=1
        with self.assertRaisesRegex(ValueError,'total_mismatch'):audit.validate_closed(plan,source,changed)

    def test_reordered_or_removed_slot_and_removed_comparison_rejected(self):
        for change in ('order','slot','pair'):
            plan,source,report=fixture_values()
            if change=='order':report['conditions'][0],report['conditions'][1]=report['conditions'][1],report['conditions'][0]
            elif change=='slot':report['conditions'].pop()
            else:report['execution_comparisons']['cross'].pop()
            with self.subTest(change=change),self.assertRaises(ValueError):audit.validate_closed(plan,source,report)

    def test_runtime_open_or_task_quality_claim_rejected(self):
        for key,val in [('status','running'),('task_quality_measured',True),('model_generations',1)]:
            plan,source,report=fixture_values();report[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):audit.validate_closed(plan,source,report)

    def test_missing_cleanup_or_false_prefix_match_rejected(self):
        for key,val in [('owned_bridge_absent',False),('prefix_api_requests',27),('structured_submissions',0)]:
            plan,source,report=fixture_values();report['conditions'][0][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):audit.validate_closed(plan,source,report)

    def test_all_artifacts_keep_original_denominators(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=base/'repo';reporting_fixture(root)
            result=reporting.build(base/'report',root)
            self.assertEqual(result['pages'],8)
            for name,n in [('all_36_execution_slots.csv',36),('all_12_groups.csv',12),
                ('all_12_within_group_comparisons.csv',12),('all_66_cross_group_comparisons.csv',66)]:
                with (base/'report'/name).open() as f:self.assertEqual(len(list(csv.DictReader(f))),n)
            self.assertFalse(result['task_quality_measured']);self.assertFalse(result['visual_reviewed'])

    def test_unknown_usage_remains_blank_in_public_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=base/'repo';reporting_fixture(root,known=3,unknown=True)
            result=reporting.build(base/'report',root)
            with (base/'report/all_36_execution_slots.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(rows[3]['source_known_total_tokens'],'')
            self.assertEqual(rows[4]['suffix_api_requests'],'')
            self.assertEqual(result['recorded_costs']['P101_unknown_usage_calls'],1)

    def test_audit_binding_tamper_or_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=base/'repo';reporting_fixture(root);out=base/'report';out.mkdir()
            with self.assertRaises(FileExistsError):reporting.build(out,root)
            path=root/audit.AUDIT;value=json.loads(path.read_text());value['checked_slots']=35;write(path,value)
            with self.assertRaisesRegex(ValueError,'record_audit_required'):reporting.validated(root)


class SavedExecutionReceiptTests(unittest.TestCase):
    def fixture(self,storage):
        plan={'private_output':'records/context_pilot/P102_choice_action_execution_v01'}
        folder=storage/plan['private_output']/'call_001';folder.mkdir(parents=True)
        row=dict(id='call_001',status='stopped',bridge_attempts=1,typed_requests_started=1,
                 typed_status_counts={'unknown':1},saved_program_executions=0)
        write(folder/'progress.json',row)
        write(folder/'bridge_01_private.json',dict(command={'op':'call_typed'},raw_request_started=True,
              error={'type':'TimeoutError'},wall_seconds=1.))
        return plan,row,folder

    def test_unknown_receipt_preserves_sent_attempt_without_execution_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            storage=Path(temp);plan,row,_=self.fixture(storage)
            audit.inspect_private_slot(storage,plan,row,lambda p:json.loads(p.read_text()),time.monotonic()+5)

    def test_tampered_raw_dispatch_accounting_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            storage=Path(temp);plan,row,folder=self.fixture(storage)
            path=folder/'bridge_01_private.json';data=json.loads(path.read_text());data['raw_request_started']=False
            write(path,data)
            with self.assertRaisesRegex(ValueError,'sent_API_count'):
                audit.inspect_private_slot(storage,plan,row,lambda p:json.loads(p.read_text()),time.monotonic()+5)

    def test_unattempted_slot_with_hidden_execution_directory_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            storage=Path(temp);plan,row,_=self.fixture(storage);row['status']='not_attempted'
            with self.assertRaisesRegex(ValueError,'unattempted_slot_has'):
                audit.inspect_private_slot(storage,plan,row,lambda p:json.loads(p.read_text()),time.monotonic()+5)


if __name__=='__main__':unittest.main()

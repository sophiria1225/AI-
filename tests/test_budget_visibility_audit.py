import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_budget_visibility_comparison import audit_cell, development_gate
from budget_signal import digest
from local_llama import payload_for
from api_error_comparison import initial_conversation
from public_display import CODE_TOOLS
from test_budget_visibility_worker import fixture

ROOT=Path(__file__).resolve().parents[1]


def rows():
    return [{'task_id':str(task),'time_visibility':policy,'record_status':'evaluated',
             'success':True,'unknown_usage_calls':0,'known_total_tokens':cost}
            for task in range(4) for policy,cost in [('measured',100),('not_exposed',90)]]


def audit_fixture(folder, result):
    trial=Path(folder)/'records/context_pilot/BOC_P80_fixture'
    read=lambda name:json.loads((trial/(name+'.json')).read_text())
    config=read('plan'); plan=read('comparison_plan'); public=read('public_task')
    item={'task_id':'fixture','public_task':public}
    original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    base,_=initial_conversation(original,public).for_model(config['observation_page_characters'])
    for i,capture in enumerate(result['captured'],1):
        call=trial/f'call_{i:03d}'
        (call/'request.json').write_text(json.dumps(payload_for(capture['cfg'],capture['messages'],CODE_TOOLS)))
        response=call/'response.json'
        if response.exists(): (call/'raw_response.json').write_text(response.read_text())
    # Synthetic transport responses are already normalized; only this decoder
    # is replaced. Admission, sent payload, history, costs and receipts are real.
    with patch('audit_budget_visibility_comparison.config_for',return_value=config), \
         patch('audit_budget_visibility_comparison.parse_response',side_effect=lambda x:x):
        return audit_cell(trial,ROOT,plan,original,item,'not_exposed',
                          {'base_messages_sha256':digest(base)},False)


class VisibilityAuditTests(unittest.TestCase):
    def test_complete_lower_cost_with_no_losses_meets_only_descriptive_gate(self):
        result=development_gate(rows(),[])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual(result['not_exposed_minus_measured_whole_task_tokens'],-40)
        self.assertFalse(result['general_quality_preservation_claim'])
        self.assertFalse(result['novel_method_claim'])

    def test_any_success_loss_increase_missing_usage_or_audit_error_rejects(self):
        for reason in ('loss','increase','unknown','unevaluated','audit'):
            data=rows(); errors=[]
            if reason=='loss': data[1]['success']=False
            if reason=='increase': data[1]['known_total_tokens']=200
            if reason=='unknown': data[1]['unknown_usage_calls']=1
            if reason=='unevaluated': data[1].update(record_status='not_run',success=None)
            if reason=='audit': errors=['synthetic audit mismatch']
            with self.subTest(reason=reason):
                result=development_gate(data,errors)
                self.assertFalse(result['development_gate_met'])
                if reason in ('unknown','unevaluated'):
                    self.assertIsNone(result['not_exposed_minus_measured_whole_task_tokens'])

    def test_duplicate_or_missing_policy_is_not_silently_aggregated(self):
        for data in (rows()+[rows()[0]],rows()[:-1]):
            with self.assertRaises(ValueError): development_gate(data,[])

    def test_worker_history_protocol_cost_and_notice_reconstruct(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(folder=folder)
            audited=audit_fixture(folder,result)
            self.assertEqual(audited['model_calls'],2)
            self.assertEqual(audited['known_total_tokens'],100)
            self.assertEqual(audited['api_requests'],2)
            trial=Path(folder)/'records/context_pilot/BOC_P80_fixture'
            p=trial/'budget_observations.json'; data=json.loads(p.read_text())
            data[0]['visible_state']['remaining']['wall_seconds_at_snapshot']=999
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'visible_budget_policy'):
                audit_fixture(folder,result)

    def test_missing_terminal_retains_known_prefix_and_unknown_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(folder=folder,actions=('echo','transport_error'))
            audited=audit_fixture(folder,result)
            self.assertEqual(audited['known_total_tokens'],50)
            self.assertEqual(audited['unknown_usage_calls'],1)
            self.assertFalse(audited['request_checks'][-1]['terminal_usage_recorded'])
            self.assertIsNone(audited['request_checks'][-1]['response_sha256'])

    def test_late_known_response_is_charged_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(folder=folder,response_delay=61)
            audited=audit_fixture(folder,result)
            self.assertEqual(audited['known_total_tokens'],50)
            self.assertEqual(audited['unknown_usage_calls'],0)
            self.assertEqual(audited['api_requests'],0)


if __name__=='__main__': unittest.main()

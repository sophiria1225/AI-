import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from receipt_history_worker_fixture import fixture, audit_fixture, auditor
from unittest.mock import patch
from receipt_reasoning_history import strip_reasoning


class ReceiptHistoryLiveTests(unittest.TestCase):
    def test_three_policies_share_first_input_and_residual_admission(self):
        starts=[]
        for policy in ('full','recent','execution_gated'):
            with self.subTest(policy=policy),tempfile.TemporaryDirectory() as folder:
                result=fixture(policy=policy,folder=folder)
                checked=audit_fixture(folder,result,policy)
                self.assertEqual(checked['reasoning_display_policy'],policy)
                self.assertEqual(checked['known_total_tokens'],100)
                self.assertEqual(result['result']['stop_reason'],'agent_declared_complete')
                self.assertTrue(result['result']['cleanup_confirmed'])
                self.assertEqual([a['policy'] for a in result['saved']['admissions']],['residual']*2)
                self.assertEqual([c['cfg']['tool_choice'] for c in result['captured']],['auto']*2)
                self.assertEqual([c['cfg']['cache_prompt'] for c in result['captured']],[False,True])
                self.assertEqual(result['counted'],[c['messages'] for c in result['captured']])
                starts.append(result['captured'][0]['messages'])
        self.assertEqual(starts[0],starts[1]);self.assertEqual(starts[1],starts[2])

    def test_confirmed_failure_restores_exact_archived_reasoning_in_live_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(policy='execution_gated',actions=('echo','echo','fail','echo','finish'),folder=folder)
            checked=audit_fixture(folder,result,'execution_gated')
            views=result['saved']['reasoning_history_views']
            self.assertEqual(views[2]['projection']['removed_reasoning_turns'],[1])
            self.assertEqual(views[3]['projection']['removed_reasoning_turns'],[])
            self.assertEqual(views[3]['projection']['redisplayed_reasoning_turns'],[1])
            self.assertEqual(views[4]['projection']['removed_reasoning_turns'],[1,2])
            actual=[m for m in result['captured'][3]['messages'] if m['role']=='assistant']
            self.assertTrue(all(m['reasoning_content']=='synthetic test text' for m in actual))
            archive=result['saved']['conversation_private']
            self.assertEqual(sum(m['role']=='assistant' and 'reasoning_content' in m for m in archive),5)
            self.assertEqual(checked['api_requests'],5)
            self.assertEqual(checked['invocation_exceptions'],1)
            self.assertEqual(result['result']['reasoning_display']['projections_redisplaying_reasoning'],1)

    def test_public_instructions_code_and_observations_match_all_views(self):
        runs=[fixture(policy=p,actions=('echo','echo','finish')) for p in ('full','recent','execution_gated')]
        for i in range(3):
            public=[strip_reasoning(r['captured'][i]['messages']) for r in runs]
            self.assertEqual(public[0],public[1]);self.assertEqual(public[1],public[2])
        self.assertNotEqual(runs[0]['captured'][2]['messages'],runs[2]['captured'][2]['messages'])

    def test_unknown_model_usage_stops_without_execution_retry_or_new_receipt(self):
        for action in ('unknown','transport_error'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as folder:
                result=fixture(policy='execution_gated',actions=('echo',action),folder=folder)
                checked=audit_fixture(folder,result,'execution_gated')
                self.assertEqual(checked['unknown_usage_calls'],1)
                self.assertEqual(checked['model_calls'],2)
                self.assertEqual(result['programs'],['echo'])
                self.assertEqual(len(result['saved']['reasoning_execution_records']),1)

    def test_budget_stop_preserves_unattempted_projection_and_does_not_generate(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(policy='execution_gated',token_limit=50,folder=folder)
            checked=audit_fixture(folder,result,'execution_gated')
            self.assertEqual(checked['model_calls'],1)
            self.assertEqual(len(result['saved']['reasoning_history_views']),2)
            self.assertFalse(result['saved']['budget_observations'][-1]['model_attempted'])

    def test_changed_projected_history_is_detected_by_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(policy='execution_gated',actions=('echo','echo','finish'),folder=folder)
            audit_fixture(folder,result,'execution_gated')
            trial=Path(folder)/'records/context_pilot/BOC_P111_fixture'
            path=trial/'call_003/request.json';value=json.loads(path.read_text())
            next(m for m in value['messages'] if m['role']=='assistant')['reasoning_content']='injected'
            path.write_text(json.dumps(value))
            config=json.loads((trial/'plan.json').read_text());plan=json.loads((trial/'comparison_plan.json').read_text())
            public=json.loads((trial/'public_task.json').read_text())
            from whole_task_receipt_history import initial_conversation
            from budget_signal import digest
            original=json.loads((Path(auditor.__file__).parents[1]/'configs/P29_stateful_code_v01.json').read_text())
            base,_=initial_conversation(original,public).for_model(config['observation_page_characters'])
            with patch.object(auditor,'config_for',return_value=config),patch.object(auditor,'parse_response',side_effect=lambda x:x):
                with self.assertRaisesRegex(ValueError,'actual_request_differs'):
                    auditor.audit_cell(trial,Path(auditor.__file__).parents[1],plan,original,
                        {'task_id':'fixture','public_task':public},'execution_gated',{'base_messages_sha256':digest(base)},False)

    def test_execution_evidence_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(policy='execution_gated',folder=folder)
            trial=Path(folder)/'records/context_pilot/BOC_P111_fixture'
            path=trial/'reasoning_execution_records.json';value=json.loads(path.read_text())
            value[0]['evidence']['eligible']=False;path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'recorded_execution_evidence_differs'):
                audit_fixture(folder,result,'execution_gated')

    def test_unknown_API_effect_or_cleanup_failure_stays_a_batch_stop(self):
        from api_error_comparison import disposition
        for options in ({'unknown_api':True},{'cleanup_ok':False},{'first_cached':1}):
            result=fixture(policy='execution_gated',**options)
            self.assertEqual(disposition(result['result']),'stop_batch')

    def test_stop_marker_after_API_prevents_another_model_call(self):
        result=fixture(policy='execution_gated',stop_after_api=True)
        self.assertEqual(result['result']['stop_reason'],'user_stop')
        self.assertEqual(len(result['captured']),1)


if __name__=='__main__':unittest.main()

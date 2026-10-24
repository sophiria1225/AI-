import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from choice_action_execution import FIXED, validate_plan, source_slots, execution_comparisons
from choice_context_replay import schedule
import run_choice_action_execution as runner


def source_fixture(known=3,unknown=True):
    rows=[]
    for index,item in enumerate(schedule()):
        row=dict(**item,source_context='P83_CSV_call_014',record_status='unattempted',status='unattempted',
                 input_tokens=None,output_tokens=None)
        if index<known:
            row.update(record_status='audited',status='ok',input_tokens=100,output_tokens=10,
                known_total_tokens=110,response_sha256='a'*64,public_output_sha256='b'*64,
                complete_generation=True,complete_static_submission=True)
        elif index==known and unknown:row.update(record_status='unknown_usage',status='error')
        rows.append(row)
    return dict(phase='P101',pipeline_status='complete' if known==36 else 'stopped',
        audit_errors=[],owned_processes_absent=True,server=dict(status='stopped'),rows=rows,
        model_calls_attempted=known+int(unknown),unknown_usage_calls=int(unknown),
        known_total_tokens=known*110,all_36_audited=known==36)


def executed_fixture():
    return [dict(**item,status='complete',public_prefix_matched=True,structured_submissions=1,
        suffix_saved_programs=1,suffix_api_requests=1,suffix_request_sequence_sha256='requests',
        suffix_execution_evidence_sha256='execution',source_complete_generation=True) for item in schedule()]


class ChoiceActionExecutionTests(unittest.TestCase):
    def test_design_matches_the_predeclared_all_slot_plan(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/runner.DESIGN).read_text());validate_plan(plan)
        for key in ('max_api_requests_total','active_deadline_seconds','model_generations'):
            changed=copy.deepcopy(plan);changed[key]+=1
            with self.assertRaises(ValueError):validate_plan(changed)

    def test_unknown_and_unattempted_outputs_are_never_executable(self):
        source=source_fixture();before=copy.deepcopy(source);slots=source_slots(source)
        self.assertEqual(len(slots),36)
        self.assertEqual(sum(x['should_execute'] for x in slots),3)
        self.assertEqual(slots[3]['unavailable_reason'],'unknown_usage')
        self.assertTrue(all(x['unavailable_reason']=='unattempted' for x in slots[4:]))
        self.assertEqual(source,before)

    def test_known_text_only_invalid_or_truncated_output_is_not_selected_away(self):
        source=source_fixture()
        source['rows'][0]['complete_static_submission']=False
        source['rows'][1].update(complete_generation=False,complete_static_submission=False)
        self.assertTrue(all(x['should_execute'] for x in source_slots(source)[:3]))

    def test_missing_or_reordered_slot_and_imputed_unknown_rejected(self):
        for change in ('missing','reordered','imputed','unknown_then_known'):
            source=source_fixture()
            if change=='missing':source['rows'].pop()
            elif change=='reordered':source['rows'][0],source['rows'][1]=source['rows'][1],source['rows'][0]
            elif change=='imputed':source['rows'][3]['input_tokens']=0
            else:
                source['rows'][0].update(record_status='unknown_usage',status='error',input_tokens=None,output_tokens=None)
            with self.subTest(change=change),self.assertRaises(ValueError):source_slots(source)

    def test_open_owner_or_audit_mismatch_prevents_source_use(self):
        for key,value in [('owned_processes_absent',False),('audit_errors',['mismatch']),
                          ('pipeline_status','generation'),('known_total_tokens',329)]:
            source=source_fixture();source[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):source_slots(source)

    def test_all_66_cross_and_12_within_groups_retained(self):
        result=execution_comparisons(executed_fixture())
        self.assertEqual(len(result['cross']),66)
        self.assertEqual(sum(x['pairs'] for x in result['cross']),594)
        self.assertEqual(len(result['within']),12)
        self.assertEqual(sum(x['pairs'] for x in result['within']),36)
        self.assertTrue(all(x['nonempty_API_request_sequences_equal']==9 for x in result['cross']))

    def test_empty_sequences_do_not_become_matching_executed_requests(self):
        rows=executed_fixture()
        for row in rows:row.update(suffix_api_requests=0,suffix_saved_programs=0,structured_submissions=0)
        result=execution_comparisons(rows)
        self.assertTrue(all(x['both_empty_API_sequences']==9 for x in result['cross']))
        self.assertTrue(all(x['nonempty_API_request_sequences_equal']==0
                            and x['Python_execution_evidence_equal']==0 for x in result['cross']))

    def test_executed_python_without_api_is_separate_from_sent_requests(self):
        rows=executed_fixture()
        for row in rows:row['suffix_api_requests']=0
        first=execution_comparisons(rows)['cross'][0]
        self.assertEqual(first['both_submitted_Python_executed'],9)
        self.assertEqual(first['Python_execution_evidence_equal'],9)
        self.assertEqual(first['both_nonempty_API_sequences'],0)

    def test_failed_prefix_is_unavailable_not_zero_api_agreement(self):
        rows=executed_fixture();rows[0].update(status='stopped',public_prefix_matched=False)
        result=execution_comparisons(rows)
        self.assertTrue(any(x['unavailable_pairs']>0 for x in result['cross']))
        rows.pop()
        with self.assertRaises(ValueError):execution_comparisons(rows)


class ChoiceActionRunnerTests(unittest.TestCase):
    def fixture(self,root,known=0):
        storage=root/'storage';repo=root/'repo';(repo/'configs').mkdir(parents=True);(repo/'reports').mkdir()
        storage.mkdir()
        plan=dict(FIXED,schedule=schedule(),private_output='records/context_pilot/P102_choice_action_execution_v01',
            experiment_prefix='P102_ACTION_V01',stop_marker='.runtime/P102.stop')
        (repo/runner.PLAN).write_text(json.dumps(plan))
        slots=source_slots(source_fixture(known=known,unknown=False))
        messages=[{'tool_calls':[]} if s['should_execute'] else None for s in slots]
        (repo/'reports/P101_choice_context.json').write_text('{}')
        return storage,repo,([],[],{}, {},messages,slots,{'owned_processes_absent':True})

    def test_all_unavailable_sources_create_no_world_or_python_process(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,repo,prepared=self.fixture(Path(temp))
            with patch.object(runner,'check_resume',return_value={}),patch.object(runner,'checked_ci',return_value=[]),\
                 patch.object(runner.subprocess,'check_output',side_effect=['a'*40,'']),\
                 patch.object(runner,'prepare',return_value=prepared),\
                 patch.object(runner,'TypedBridgeProcess') as bridge,patch.object(runner,'PersistentApiPython') as python:
                result=runner.run(storage,repo)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(result['unavailable_source_slots'],36)
            self.assertEqual(result['environment_api_requests'],0)
            bridge.assert_not_called();python.assert_not_called()
            self.assertTrue((repo/'reports/P102_choice_action_execution.json').is_file())

    def test_prefix_mismatch_prevents_suffix_and_later_worlds_and_keeps_spent_cost(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,repo,prepared=self.fixture(Path(temp),known=3)
            raw=Mock(process=SimpleNamespace(pid=123));raw.close.return_value={'graceful':True}
            recorded=Mock(attempts=[{'raw_request_started':True,'command':{'op':'call_typed'}}])
            transport=Mock(receipts=[{'status':'returned'}])
            session=Mock(controls={str(i):True for i in range(14)},programs=[{}])
            session.close.return_value={'container_removed':True}
            def mismatch(*args):
                args[-1]['prefix_api_requests']=1
                raise ValueError('prefix_observable_mismatch_no_suffix')
            with patch.object(runner,'check_resume',return_value={}),patch.object(runner,'checked_ci',return_value=[]),\
                 patch.object(runner.subprocess,'check_output',side_effect=['a'*40,'']),\
                 patch.object(runner,'prepare',return_value=prepared),\
                 patch.object(runner,'TypedBridgeProcess',return_value=raw) as bridge,\
                 patch.object(runner,'RecordedBridge',return_value=recorded),\
                 patch.object(runner,'PublicResultTransport',return_value=transport),\
                 patch.object(runner,'confirm_initial_world'),patch.object(runner,'PublicNameCatalog'),\
                 patch.object(runner,'PersistentApiPython',return_value=session),\
                 patch.object(runner,'reconstruct',side_effect=mismatch),patch.object(runner,'suffix') as suffix,\
                 patch.object(runner.os,'kill',side_effect=ProcessLookupError):
                result=runner.run(storage,repo)
            self.assertEqual(result['status'],'stopped')
            self.assertEqual(result['environment_api_requests'],1)
            self.assertEqual(result['unattempted_execution_slots'],35)
            self.assertEqual(result['conditions'][0]['status'],'stopped')
            self.assertEqual(bridge.call_count,1);suffix.assert_not_called();session.close.assert_called_once()
            raw.close.assert_called_once()

    def predecessor_fixture(self,root):
        storage=root/'storage';repo=root/'repo'
        folder=storage/'records/context_pilot/P101_pipeline_v01';folder.mkdir(parents=True)
        record=storage/'runtime/server';record.mkdir(parents=True)
        (repo/'reports').mkdir(parents=True)
        server=dict(status='stopped',supervisor_pid=100,pid=101,record_directory='runtime/server')
        (folder/'server_final.json').write_text(json.dumps(server,indent=2))
        (record/'summary.json').write_text(json.dumps(server,separators=(',',':')))
        pipeline=dict(status='complete',server_stopped=True,git_commit=runner.PREDECESSOR_HEAD,
                      server_supervisor_pid=100)
        (folder/'status.json').write_text(json.dumps(pipeline))
        pre=dict(status='complete',git_commit=runner.PREDECESSOR_HEAD,source_sha256={})
        (repo/'reports/P101_initial_checks.json').write_text(json.dumps(pre))
        source=dict(pipeline_status_sha256=runner.sha(folder/'status.json'),
            server_summary_sha256=runner.sha(record/'summary.json'),source_sha256={},
            preflight_sha256=runner.sha(repo/'reports/P101_initial_checks.json'))
        return storage,repo,source,folder

    def test_closed_server_copies_may_differ_only_in_json_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,repo,source,_=self.predecessor_fixture(Path(temp))
            with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                closure=runner.previous_closed(storage,repo,FIXED,source)
            self.assertNotEqual(closure['server_final_sha256'],source['server_summary_sha256'])
            self.assertTrue(closure['owned_processes_absent'])

    def test_existing_owner_pid_prevents_any_environment_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,repo,source,_=self.predecessor_fixture(Path(temp))
            with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='100')):
                with self.assertRaisesRegex(ValueError,'process_still_exists'):
                    runner.previous_closed(storage,repo,FIXED,source)

    def test_open_pipeline_cannot_be_closed_by_a_stale_stopped_server_record(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,repo,source,folder=self.predecessor_fixture(Path(temp))
            pipeline=json.loads((folder/'status.json').read_text());pipeline['status']='generation'
            (folder/'status.json').write_text(json.dumps(pipeline))
            source['pipeline_status_sha256']=runner.sha(folder/'status.json')
            with self.assertRaisesRegex(ValueError,'closed_owned_P101'):
                runner.previous_closed(storage,repo,FIXED,source)

    def test_design_only_cannot_start_before_final_evidence_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'final_P102_execution_plan_required'):
                runner.prepare(Path(temp),Path(temp),dict(FIXED,schedule=schedule(),
                    execution_ready=False,implementation_ready=False))


if __name__=='__main__':unittest.main()

import copy
import json
from pathlib import Path
import tempfile
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from checkpoint_payback_worker_fixture import ROOT, fixture, audit_fixture, configuration
from audit_empirical_payback_trace import audit_trace
import audit_whole_task_checkpoint_payback as cohort
import build_checkpoint_payback_summary as report
import inspect_whole_task_checkpoint_payback_session as session
from whole_task_checkpoint_payback import initial_conversation, run_order, cell_id, SEEDS, MODES, summarize
from budget_signal import digest
from run_handoff_factors import sha


def read(p): return json.loads(p.read_text())
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x))


def replay(folder, result):
    trial=Path(folder)/'records/context_pilot'/result['result']['run_id']
    original=read(ROOT/'configs/P29_stateful_code_v01.json')
    return audit_trace(trial,read(trial/'plan.json'),initial_conversation(original,read(trial/'public_task.json')))


class PaybackTraceTests(unittest.TestCase):
    def test_real_new_worker_and_all_shared_cost_roles(self):
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                result=fixture(mode=mode,actions=('echo',)*8+('finish',),max_calls=10,folder=folder)
                checked=audit_fixture(folder,result)
                self.assertEqual(checked['model_calls'],result['result']['model_calls'])
                self.assertEqual(checked['known_total_tokens'],result['result']['known_total_tokens'])
                self.assertEqual(checked['payback_rejections'],int(mode=='empirical_payback'))
                self.assertTrue(checked['payback_accounting_complete'])
                self.assertFalse(checked['payback_clock_independently_remeasured'])

    def test_known_failed_unknown_and_undispatched_paths_reconstruct(self):
        variants=[
            dict(actions=('echo',)*12+('finish',)),
            dict(actions=('echo',)*3+('finish',),max_calls=4),
            dict(actions=('echo',)*3+('finish',),token_limit=55000),
            dict(actions=('echo',)*3+('finish',),focus_input_tokens=64000),
            dict(actions=('echo',)*9,summary_mode='unknown'),
            dict(actions=('echo',)*9,summary_mode='transport_error'),
            dict(actions=('echo',)*9,summary_mode=('valid','unknown')),
            dict(actions=('echo',)*9,summary_mode=('valid','transport_error')),
            dict(actions=('echo',)*12+('finish',),summary_mode='invalid'),
            dict(actions=('echo',)*7+('unknown',)),
            dict(actions=('echo',)*7+('transport_error',)),
            dict(first_cached=1),dict(count_delay=61),dict(stop_after_api=True),
            dict(unknown_api=True),dict(cleanup_ok=False),dict(actions=('finish',)),
        ]
        for mode in MODES:
            for opts in variants:
                with self.subTest(mode=mode,opts=opts), tempfile.TemporaryDirectory() as folder:
                    result=fixture(mode=mode,folder=folder,**opts)
                    checked=audit_fixture(folder,result)
                    self.assertEqual(checked['unknown_usage_calls'],result['result']['unknown_usage_calls'])
                    self.assertEqual(checked['known_total_tokens'],result['result']['known_total_tokens'])

    def test_gate_input_prefix_clock_decision_and_dispatch_tampering_rejected(self):
        changes=[
            lambda x:x[1].__setitem__('past_calls_sha256','0'*64),
            lambda x:x[1].__setitem__('past_controls_sha256','0'*64),
            lambda x:x[1].__setitem__('prior_delta',999999),
            lambda x:x[1].__setitem__('predicted_actor_horizon',1),
            lambda x:x[1].__setitem__('remaining_calls',999),
            lambda x:x[1].__setitem__('remaining_wall_seconds',999),
            lambda x:x[1].__setitem__('model_attempted',True),
            lambda x:x[1].__setitem__('terminal_usage_recorded',True),
            lambda x:x[1].__setitem__('summary_known_tokens',1),
            lambda x:x.append(copy.deepcopy(x[1])),
            lambda x:x.pop(),
        ]
        for i,mutate in enumerate(changes):
            with self.subTest(case=i),tempfile.TemporaryDirectory() as folder:
                result=fixture(mode='empirical_payback',actions=('echo',)*8+('finish',),max_calls=10,folder=folder)
                audit_fixture(folder,result)
                p=Path(folder)/'records/context_pilot'/result['result']['run_id']/'empirical_payback_events.json'
                value=read(p);mutate(value);write(p,value)
                with self.assertRaises(ValueError):replay(folder,result)

    def test_ordinary_shadow_rejection_is_not_actual_intervention(self):
        with tempfile.TemporaryDirectory() as folder:
            result=fixture(actions=('echo',)*8+('finish',),max_calls=10,folder=folder)
            checked=audit_fixture(folder,result)
            self.assertGreater(checked['payback_shadow_rejections'],0)
            self.assertEqual(checked['payback_rejections'],0)

    def test_actual_focus_request_and_accounting_summary_tampering_rejected(self):
        for target in ('focus_request', 'summary'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                result=fixture(mode='empirical_payback',actions=('echo',)*8+('finish',),max_calls=10,folder=folder)
                audit_fixture(folder,result)
                trial=Path(folder)/'records/context_pilot'/result['result']['run_id']
                if target=='focus_request':
                    focus=next(c['id'] for c in read(trial/'usage.json') if c['role']=='focus')
                    path=trial/focus/'request.json';value=read(path);value['messages'][-1]['content']='synthetic tampering'
                else:
                    path=trial/'summary.json';value=read(path);value['payback_control']['skipped_unstarted_summaries']=0
                write(path,value)
                with self.assertRaises(ValueError):replay(folder,result)


def closed_fixture(base, *, missing=False, unknown=False, corrupt=False, lost_completed=False):
    storage=base/'storage';storage.mkdir();root=base/'repo';root.mkdir()
    for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER,'scripts/evaluate_context_trial.py'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
    original,plan,item=configuration();original['api_budget_by_task'][item['task_id']]=80
    plan.update(experiment='P133',batch_id='P133_batch_v01',max_calls=10,max_total_tokens=450000,
                known_tasks=[{k:item[k] for k in ('task_id','source_run')}],payback_modes=list(MODES),model_seeds=list(SEEDS))
    mapping={name:sha(root/name) for name in (report.BUILDER,report.AUDITOR,report.INSPECTOR,report.HELPER)}
    plan['source_sha256']=mapping;write(root/report.PLAN,plan)
    pre_rows=[];completed=[];batch_rows=[]
    for rep in (1,2):
        cfg=cohort.config_for(original,plan,item['task_id'],MODES[0],rep)
        initial,_=initial_conversation(original,item['public_task']).for_model(cfg['observation_page_characters'])
        pre_rows.append(dict(replication=rep,model_seed=SEEDS[rep-1],task_id=item['task_id'],
            conditions={m:dict(base_messages_sha256=digest(initial)) for m in MODES}))
    for rep,number,mode in run_order():
        rid=cell_id(rep,number,mode)
        if missing and rep==2:continue
        opts=dict(actions=('echo',)*8+('finish',),max_calls=10)
        if unknown and mode=='empirical_payback' and rep==1:opts=dict(actions=('echo',)*9,summary_mode='unknown',max_calls=10)
        result=fixture(mode=mode,replication=rep,folder=storage,**opts)
        audit_fixture(storage,result)
        trial=storage/'records/context_pilot'/rid
        # Bind the same synthetic plan to each real-worker trial; config is unchanged.
        write(trial/'comparison_plan.json',plan)
        dbs=storage/'.runtime/appworld/r18_probe_01/experiments/outputs'/rid/'tasks'/item['task_id']/'dbs'
        write(dbs/'synthetic.json',{'synthetic':True})
        write(trial/'evaluation.json',dict(execution_summary_sha256=sha(trial/'summary.json'),
            evaluation_returned_to_model=False,official_success=not unknown,
            evaluation_script_sha256=sha(root/'scripts/evaluate_context_trial.py'),
            frozen_database_hashes={'synthetic.json':sha(dbs/'synthetic.json')}))
        completed.append(rid);batch_rows.append(dict(run_id=rid,evaluation_started_at='synthetic',evaluation_wall_seconds=0.1))
        if corrupt and rep==2 and mode=='empirical_payback':
            value=read(trial/'empirical_payback_events.json');value[0]['remaining_calls']=999
            write(trial/'empirical_payback_events.json',value)
        if lost_completed and rep==2 and mode=='empirical_payback':
            shutil.rmtree(trial)  # Handwritten temporary fixture only.
    pre=dict(rows=pre_rows);write(root/report.PREFLIGHT,pre)
    activation=dict(source_hashes=mapping,preflight_sha256=sha(root/report.PREFLIGHT));write(root/report.ACTIVATION,activation)
    folder=storage/'records/context_pilot/P133_pipeline_v01';record=storage/'records/p2_servers/synthetic'
    server=dict(status='stopped',stop_reason='synthetic',supervisor_pid=10000001,pid=10000002,
        record_directory=str(record.relative_to(storage)),started_at='synthetic',wall_seconds=100,
        load_wall_seconds=1,sampled_peak_rss_bytes=100,peak_system_swap_bytes=0,exit_code=0,
        model_revision='synthetic',runtime='synthetic',ctx_size=64000,cache_type_k='f16',cache_type_v='f16',memory_note='synthetic')
    write(record/'summary.json',server);(record/'memory.jsonl').write_text(json.dumps({'rss_bytes':100,'swap_used_bytes':0})+'\n')
    write(folder/'server_final.json',server)
    write(folder/'status.json',dict(status='stopped' if missing else 'complete',server_stopped=True,
        server_supervisor_pid=server['supervisor_pid'],wall_seconds=100,stages=[dict(mode='batch',wall_seconds=90)]))
    write(storage/'records/context_pilot/P133_batch_v01/status.json',dict(phase='P133',status='stopped' if missing else 'complete',
        completed=completed,rows=batch_rows,active=None))
    absent=SimpleNamespace(returncode=1,stdout='')
    with patch('run_whole_task_checkpoint_payback.sources',return_value=(plan,original,[],[item])), \
         patch('run_whole_task_checkpoint_payback.frozen_hashes',return_value=mapping), \
         patch.object(cohort.subprocess,'run',return_value=absent):
        audited=cohort.run(storage,root)
        server_report=session.inspect(storage,root)
    write(root/report.SESSION,server_report)
    with patch.object(report,'ROOT',root):published=report.build(root)
    return audited,published,root,storage


class CohortAndReportTests(unittest.TestCase):
    def test_four_real_worker_trials_through_closed_audit_session_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,root,_=closed_fixture(Path(td))
            self.assertEqual(audit['audit_errors'],[])
            self.assertEqual(len(pub['conditions']),4)
            self.assertEqual(pub['all_conditions']['evaluated_conditions'],4)
            self.assertIsNotNone(pub['all_conditions']['exact_total_tokens'])
            self.assertEqual(sum(r['payback_rejections'] for r in pub['conditions']),2)
            self.assertTrue(all(r['payback_accounting_complete'] for r in pub['conditions']))
            with patch.object(report,'ROOT',root),self.assertRaises(FileExistsError):report.build(root)

    def test_unknown_dispatch_preserves_known_cost_and_nested_null(self):
        with tempfile.TemporaryDirectory() as td:
            audit,pub,_,_=closed_fixture(Path(td),unknown=True)
            self.assertEqual(audit['audit_errors'],[])
            self.assertFalse(pub['audited_criteria']['development_gate_met'])
            self.assertEqual(pub['all_conditions']['recorded_unknown_usage_calls'],1)
            self.assertGreater(pub['all_conditions']['known_token_subtotal'],0)
            self.assertIsNone(pub['all_conditions']['exact_total_tokens'])
            for k in ('input_tokens','output_tokens','cached_input_tokens'):
                self.assertIsNone(pub['all_conditions']['measures'][k]['exact_all_condition_total'])

    def test_missing_slots_are_kept_and_cannot_become_zero(self):
        with tempfile.TemporaryDirectory() as td:
            _,pub,_,_=closed_fixture(Path(td),missing=True)
            self.assertEqual(len(pub['conditions']),4)
            missing=[r for r in pub['conditions'] if r['record_status']=='not_run']
            self.assertEqual(len(missing),2)
            self.assertTrue(all(r['known_total_tokens'] is None and r['payback_rejections'] is None for r in missing))
            self.assertIsNone(pub['all_conditions']['exact_total_tokens'])
            self.assertEqual(pub['all_conditions']['unknown_usage_count_missing_conditions'],2)

    def test_missing_time_and_attempts_remain_unknown(self):
        self.assertIsNone(session.cell_time_totals([{'record_status':'incomplete_worker'}])['cell_full_wall_seconds'])
        self.assertEqual(session.cell_time_totals([{'record_status':'not_run'}])['cell_full_wall_seconds'],0)
        self.assertIsNone(session.attempt_time_totals([{'evaluation_started_at':'synthetic'}],'evaluation')['exact_total'])

    def test_audit_error_keeps_four_slots_and_missing_cost(self):
        with tempfile.TemporaryDirectory() as td:
            audited,pub,_,_=closed_fixture(Path(td),corrupt=True)
            self.assertEqual(len(audited['audit_errors']),1)
            self.assertEqual(len(pub['conditions']),4)
            bad=[r for r in pub['conditions'] if r['record_status']=='audit_error']
            self.assertEqual(len(bad),1)
            self.assertIsNone(bad[0]['known_total_tokens'])
            self.assertIsNone(bad[0]['payback_rejections'])
            self.assertFalse(pub['audited_criteria']['development_gate_met'])
            self.assertIsNone(pub['server_measures']['cell_full_wall_seconds'])

    def test_completed_marker_without_trial_is_started_unknown_not_unrun_zero(self):
        with tempfile.TemporaryDirectory() as td:
            _,pub,_,_=closed_fixture(Path(td),lost_completed=True)
            lost=[r for r in pub['conditions'] if r['record_status']=='incomplete_worker']
            self.assertEqual(len(lost),1)
            self.assertIsNone(lost[0]['known_total_tokens'])
            self.assertIsNone(pub['server_measures']['cell_full_wall_seconds'])

    def test_complete_batch_rejects_missing_or_duplicated_slots(self):
        ids=[cell_id(*args) for args in run_order()]
        for completed in (ids[:-1],ids+[ids[0]]):
            with self.assertRaises(ValueError):cohort.validate_closed_batch(dict(phase='P133',status='complete',completed=completed,rows=[],active=None))


if __name__=='__main__':unittest.main()

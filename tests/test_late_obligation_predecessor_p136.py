"""P136 closed-predecessor safety using entirely handwritten files and fake ps/git."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_whole_task_late_obligations_p136 as driver
from whole_task_observed_obligations_p135 import cell_id,run_order


class PredecessorTests(unittest.TestCase):
    def fixture(self, *, audit_mutate=None, marker_mutate=None):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        storage=Path(t.name).resolve()/'storage';private=Path(t.name).resolve()/'private'
        storage.mkdir();private.mkdir()
        def write(base,rel,value):
            p=base/rel;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(value,sort_keys=True)+'\n');return driver.sha(p)
        run=storage/'.runtime/worktrees/p135-run';prep=storage/'.runtime/worktrees/p135-prep'
        source={'scripts/a.py':{'synthetic':1},'tests/test_a.py':{'synthetic':2}}
        for base in (run,prep):
            mapping={rel:write(base,rel,val) for rel,val in source.items()}
            plan_sha=write(base,'configs/P135_whole_task_observed_obligations_v01.json',dict(source_sha256=mapping))
        folder='records/context_pilot/P135_pipeline_v01/'
        state=dict(phase='P135_pipeline',status='complete',git_commit=driver.P135_HEAD,
                   server_stopped=True,server_supervisor_pid=102,stage_pid=103)
        final=dict(status='stopped',supervisor_pid=102,pid=104)
        status_sha=write(storage,folder+'status.json',state);final_sha=write(storage,folder+'server_final.json',final)
        ids=[cell_id(*x) for x in run_order()]
        write(storage,'records/context_pilot/P135_batch_v01/status.json',dict(status='complete',planned=ids,completed=ids))
        rows=[dict(run_id=cell_id(rep,n,m),replication=rep,model_seed=57 if rep==1 else 157,
                   obligation_mode=m,record_status='evaluated',success=False,unknown_usage_calls=1)
              for rep,n,m in run_order()]
        audit=dict(phase='P135',rows=rows,audit_errors=[],owned_processes_absent=True,
                   pipeline_status_sha256=status_sha,server_final_sha256=final_sha)
        if audit_mutate:audit_mutate(audit)
        copies={}
        for base in (run,prep):
            copies['reports/P135_comparison.json']=write(base,'reports/P135_comparison.json',audit)
            session=dict(phase='P135',status='stopped',owned_processes_absent=True,
                         audit_source_sha256=copies['reports/P135_comparison.json'])
            copies['reports/P135_server_session.json']=write(base,'reports/P135_server_session.json',session)
            for rel in ('reports/P135_initial_checks.json','reports/P135_activation_v01.json',
                'materials/20261027_p135_results/README.md','materials/20261027_p135_results/conditions.csv',
                'materials/20261027_p135_results/summary.json','materials/20261027_p135_results/build_manifest.json'):
                copies[rel]=write(base,rel,{'handwritten':rel})
        collector=dict(status='complete',planned_conditions=6,evaluated_conditions=6,audit_passed=True,
                       audit_errors=0,copied_source_sha256=copies)
        collector_sha=write(storage,'.runtime/P135_report_collector_once_end.json',collector)
        review=dict(status='pass',phase='P135',fixed_head=driver.P135_HEAD,plan_sha256=plan_sha,
                    collector_complete_seen_before_trial_read=True,collector_end_sha256=collector_sha)
        private_hashes={name:write(private,name,review if name.endswith('review_20261027.json') else {'synthetic':name})
                        for name in driver.P135_PRIVATE_SHA256}
        review_sha=private_hashes['AI_P135_closed_independent_review_20261027.json']
        markers={
          'P135_report_collector_once_end.json':collector,
          'P135_closure_once_end.json':dict(pipeline_exit=0,stages=[dict(stage=s,exit_code=0)for s in ('audit','session','report')],
                audit_sha256=copies['reports/P135_comparison.json'],session_sha256=copies['reports/P135_server_session.json'],
                report_manifest_sha256=copies['materials/20261027_p135_results/build_manifest.json']),
          'P135_closed_review_wait_once_end.json':dict(status='complete',review_started=True,review_exit_code=0,
                source_head=driver.P135_HEAD,collector_end_sha256=collector_sha,reviewer_output_sha256=review_sha),
          'P135_figure_wait_once_end.json':dict(status='complete',renderer_started=True,renderer_exit_code=0,
                source_head=driver.P135_HEAD,collector_end_sha256=collector_sha,independent_review_sha256=review_sha,
                figure_manifest_sha256=private_hashes['AI_P135_actual_figures_20261027_v01/output_manifest.json']),
          'P135_pipeline_once_start.json':dict(source_head=driver.P135_HEAD,plan_sha256=plan_sha,wrapper_pid=101,
                reserved_snapshot_sha256='52cfe1ecc0ca4aa004ed3965c10041d0346144b0d382fab2339399a895aaf0fb',
                ledger_names_snapshot=['synthetic'+str(i)for i in range(190)])}
        if marker_mutate:marker_mutate(markers)
        marker_hashes={name:write(storage,'.runtime/'+name,value)for name,value in markers.items()}
        for p in (patch.object(driver,'PRIVATE_EVIDENCE_ROOT',private),
                  patch.object(driver,'P135_MARKER_SHA256',marker_hashes),
                  patch.object(driver,'P135_PRIVATE_SHA256',private_hashes),
                  patch.object(driver,'P135_SOURCE_COUNT',2),patch.object(driver,'P135_PLAN_SHA256',plan_sha),
                  patch.object(driver.subprocess,'check_output',return_value=driver.P135_HEAD)):
            p.start();self.addCleanup(p.stop)
        return storage,private

    def invoke(self,storage):
        with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
            return driver.launch_predecessor_closed(storage)

    def test_all_failed_unknown_previous_cells_are_allowed_not_selected_away(self):
        storage,_=self.fixture();result=self.invoke(storage)
        self.assertIs(result['all_six_closed'],True)
        self.assertIs(result['outcomes_used_to_filter_conditions'],False)
        self.assertTrue(result['storage_sha256']);self.assertTrue(result['private_evidence_sha256'])

    def test_collector_incomplete_rejected_before_any_other_read(self):
        storage,_=self.fixture(marker_mutate=lambda m:m['P135_report_collector_once_end.json'].update(status='waiting'))
        original=driver.read
        with patch.object(driver,'read',wraps=original) as reads,patch.object(driver.subprocess,'run')as ps:
            with self.assertRaisesRegex(ValueError,'all_six_closed'):driver.launch_predecessor_closed(storage)
            reads.assert_called_once_with(storage/'.runtime/P135_report_collector_once_end.json');ps.assert_not_called()

    def test_missing_evaluated_slot_wrong_seed_or_boolean_replication_are_rejected(self):
        mutations=[lambda a:a['rows'].pop(),lambda a:a['rows'][0].update(record_status='not_run'),
                   lambda a:a['rows'][0].update(model_seed=999),lambda a:a['rows'][0].update(replication=True),
                   lambda a:a.update(audit_errors=['synthetic'])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                storage,_=self.fixture(audit_mutate=mutate)
                with self.assertRaises(ValueError):self.invoke(storage)

    def test_typed_stage_review_and_figure_terminal_gates(self):
        mutations=[lambda m:m['P135_closure_once_end.json']['stages'][2].update(exit_code=1),
            lambda m:m['P135_closure_once_end.json']['stages'][0].update(exit_code=False),
            lambda m:m['P135_closed_review_wait_once_end.json'].update(review_started=False),
            lambda m:m['P135_closed_review_wait_once_end.json'].update(review_exit_code=False),
            lambda m:m['P135_figure_wait_once_end.json'].update(renderer_exit_code=1),
            lambda m:m['P135_report_collector_once_end.json'].update(evaluated_conditions=True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                storage,_=self.fixture(marker_mutate=mutate)
                with self.assertRaises(ValueError):self.invoke(storage)

    def test_source_report_private_output_or_marker_tamper_rejected(self):
        for rel in ('.runtime/worktrees/p135-run/scripts/a.py',
                    '.runtime/worktrees/p135-prep/reports/P135_comparison.json',
                    '.runtime/P135_figure_wait_once_end.json'):
            storage,_=self.fixture();(storage/rel).write_text('{}')
            with self.subTest(path=rel),self.assertRaises(ValueError):self.invoke(storage)
        storage,private=self.fixture();(private/'AI_P135_closed_independent_review_20261027.json').write_text('{}')
        with self.assertRaises(ValueError):self.invoke(storage)

    def test_owned_process_and_explicit_stop_cannot_be_overridden_by_closed_metadata(self):
        storage,_=self.fixture()
        with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='live')):
            with self.assertRaisesRegex(ValueError,'process_present'):driver.launch_predecessor_closed(storage)
        for phase in ('P135','P136'):
            p=storage/f'.runtime/{phase}.stop';p.touch()
            with patch.object(driver,'read')as reads:
                with self.assertRaises(InterruptedError):driver.launch_predecessor_closed(storage)
                reads.assert_not_called()
            p.unlink()

    def test_changed_frozen_head_rejected(self):
        storage,_=self.fixture()
        with patch.object(driver.subprocess,'check_output',return_value='0'*40):
            with self.assertRaisesRegex(ValueError,'head_changed'):self.invoke(storage)


if __name__=='__main__':unittest.main()

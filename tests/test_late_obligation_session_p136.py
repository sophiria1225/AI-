"""P136 session ledger: synthetic records and process probes only."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_whole_task_late_obligations_session_p136 as session


class P136SessionTests(unittest.TestCase):
    def test_unstarted_versus_missing_measurement_and_timing_overlap(self):
        r=session.cell_time_totals([dict(record_status='not_run'),dict(record_status='evaluated',full_wall_seconds=0.),dict(record_status='incomplete_worker')])
        self.assertEqual(r['known_cell_full_wall_seconds'],0.);self.assertEqual(r['unknown_cell_full_wall_count'],1);self.assertIsNone(r['cell_full_wall_seconds'])
        self.assertEqual(session.attempt_time_totals([{'evaluation_started_at':'synthetic'},{'evaluation_wall_seconds':0.},{}],'evaluation'),dict(known_subtotal=0.,unknown_attempts=1,attempts=2,exact_total=None))
    def test_invalid_timing_is_unknown(self):
        for value in (-1,True,float('nan')):
            self.assertIsNone(session.cell_time_totals([dict(record_status='evaluated',full_wall_seconds=value)])['cell_full_wall_seconds'])
    def test_session_checks_all_two_exact_identities_before_process_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'records/context_pilot/P136_pipeline_v01';folder.mkdir(parents=True)
            for name,value in [('status.json',dict(status='complete',server_stopped=True,server_supervisor_pid=1)),('server_final.json',dict(status='stopped',supervisor_pid=1))]:
                (folder/name).write_text(json.dumps(value))
            report=dict(phase='P136',audit_errors=[],rows=[dict(run_id=session.cell_id(rep,n,mode),replication=rep,model_seed=session.SEEDS[rep-1],obligation_mode=mode,checkpoint_policy='rolling_separate') for rep,n,mode in session.run_order()],owned_processes_absent=True,pipeline_status_sha256=session.sha(folder/'status.json'),server_final_sha256=session.sha(folder/'server_final.json'))
            report['rows'][0]['obligation_mode']='invalid'
            target=root/'reports';target.mkdir();(target/'P136_comparison.json').write_text(json.dumps(report))
            with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run') as process:
                with self.assertRaisesRegex(ValueError,'all_six_fixed'):session.inspect(root,root)
                process.assert_not_called()
    def test_closed_session_keeps_missing_started_costs_and_all_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'records/context_pilot/P136_pipeline_v01'
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
                model_seed=session.SEEDS[rep-1],obligation_mode=mode,checkpoint_policy='rolling_separate',
                record_status='evaluated',full_wall_seconds=10)
                for rep,n,mode in session.run_order()]
            rows[-1].pop('full_wall_seconds');rows[-1]['record_status']='incomplete_worker'
            write(root/'reports/P136_comparison.json',dict(phase='P136',rows=rows,audit_errors=[{'type':'synthetic'}],
                owned_processes_absent=True,pipeline_status_sha256=session.sha(folder/'status.json'),
                server_final_sha256=session.sha(folder/'server_final.json')))
            write(root/'records/context_pilot/P136_batch_v01/status.json',dict(
                rows=[dict(evaluation_wall_seconds=2),dict(evaluation_started_at='synthetic')],
                completed=['synthetic']))
            with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run',
                    return_value=SimpleNamespace(returncode=1,stdout='')) as process:
                result=session.inspect(root,root)
            self.assertEqual(process.call_count,2)
            self.assertEqual(result['known_cell_full_wall_seconds'],50)
            self.assertEqual(result['unknown_cell_full_wall_count'],1)
            self.assertIsNone(result['cell_full_wall_seconds'])
            self.assertIsNone(result['batch_other_wall_seconds'])
            self.assertEqual(result['known_evaluation_wall_seconds'],2)
            self.assertEqual(result['unknown_evaluation_wall_count'],1)
            self.assertIsNone(result['evaluation_wall_seconds'])
            self.assertEqual(result['cell_audit_error_count'],1)


    def _complete_fixture(self, root, memory):
        folder=root/'records/context_pilot/P136_pipeline_v01';record=root/'records/p2_servers/synthetic'
        def write(path,value):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n')
        state=dict(status='complete',server_stopped=True,server_supervisor_pid=2,wall_seconds=10,
                   stages=[dict(mode='batch',wall_seconds=8)])
        server=dict(status='stopped',stop_reason='synthetic',pid=1,supervisor_pid=2,record_directory=str(record),
            started_at='synthetic',wall_seconds=10,load_wall_seconds=1,sampled_peak_rss_bytes=0,peak_system_swap_bytes=0,
            exit_code=0,model_revision='synthetic',runtime='synthetic',ctx_size=65536,
            cache_type_k='synthetic',cache_type_v='synthetic',memory_note='synthetic')
        write(folder/'status.json',state);write(folder/'server_final.json',server);write(record/'summary.json',server)
        (record/'memory.jsonl').write_text(''.join(json.dumps(m)+'\n' for m in memory))
        rows=[dict(run_id=session.cell_id(rep,n,mode),replication=rep,model_seed=session.SEEDS[rep-1],
            obligation_mode=mode,checkpoint_policy='rolling_separate',record_status='not_run') for rep,n,mode in session.run_order()]
        report=dict(phase='P136',rows=rows,audit_errors=[],owned_processes_absent=True,
            pipeline_status_sha256=session.sha(folder/'status.json'),server_final_sha256=session.sha(folder/'server_final.json'))
        write(root/'reports/P136_comparison.json',report)
        write(root/'records/context_pilot/P136_batch_v01/status.json',dict(rows=[],completed=[]))
        return record

    def test_empty_or_missing_memory_is_distinct_from_observed_numeric_zero(self):
        for memory in ([],[dict(rss_bytes=None,swap_used_bytes=None)],[dict(rss_bytes=0,swap_used_bytes=0.0)]):
            with self.subTest(memory=memory),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self._complete_fixture(root,memory)
                with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run',
                        return_value=SimpleNamespace(returncode=1,stdout='')):
                    out=session.inspect(root,root)
                self.assertEqual(out['memory_sample_count'],len(memory))
                self.assertEqual(out['cell_full_wall_seconds'],0.)
                self.assertEqual(out['missing_rss_samples'],sum(m['rss_bytes'] is None for m in memory))
                expected=0 if memory and memory[0]['rss_bytes'] is not None else None
                self.assertEqual(out['observed_rss_peak_or_null'],expected)
                self.assertEqual(out['baseline_system_swap_bytes'],memory[0]['swap_used_bytes'] if memory else None)

    def test_live_process_or_invalid_memory_is_never_closed_as_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);record=self._complete_fixture(root,[dict(rss_bytes=0,swap_used_bytes=0.)])
            with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run',
                    return_value=SimpleNamespace(returncode=0,stdout='synthetic live process')):
                with self.assertRaisesRegex(ValueError,'process still exists'):session.inspect(root,root)
            (record/'memory.jsonl').write_text(json.dumps({'rss_bytes':True,'swap_used_bytes':0.})+'\n')
            with patch.object(session,'ROOT',root),patch.object(session.subprocess,'run',
                    return_value=SimpleNamespace(returncode=1,stdout='')):
                with self.assertRaisesRegex(ValueError,'invalid_memory_sample'):session.inspect(root,root)


if __name__=='__main__':unittest.main()

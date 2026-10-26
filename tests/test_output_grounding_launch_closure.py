"""An independent next cohort cannot attach to an active or unrelated P128."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_whole_task_output_grounding as driver
from whole_task_receipt_disclosure import cell_id,run_order


class LaunchClosureTests(unittest.TestCase):
    def test_unclosed_predecessor_rejects_before_server_contact_or_attempt_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';storage=Path(tmp)/'storage';root.mkdir();storage.mkdir()
            with patch.object(driver,'sources',return_value=({}, {}, [], [])), \
                 patch.object(driver,'launch_predecessor_closed',side_effect=ValueError('P128_active')), \
                 patch.object(driver,'live_identity') as live, \
                 patch.object(driver,'frozen_sources') as frozen, \
                 patch.object(driver,'count_input') as counted:
                with self.assertRaisesRegex(ValueError,'P128_active'):driver.preflight(storage,root)
                live.assert_not_called();frozen.assert_not_called();counted.assert_not_called()
                self.assertFalse((storage/'records/context_pilot/P129_preflight_v01').exists())

    def test_closed_failure_or_unknowns_do_not_select_a_different_next_condition(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp)
            values={
                'records/context_pilot/P128_pipeline_v01/status.json':dict(phase='P128_pipeline',status='stopped',server_stopped=True,server_supervisor_pid=123,git_commit='a'*40),
                'records/context_pilot/P128_pipeline_v01/server_final.json':dict(status='stopped',supervisor_pid=123,pid=124),
                'records/context_pilot/P128_batch_v01/status.json':dict(phase='P128',status='stopped',planned=[cell_id(*r) for r in run_order()]),
                '.runtime/P128_closure_once_end.json':dict(stages=[dict(stage=k,exit_code=1 if k=='audit' else 0) for k in ('audit','session','report')],audit_sha256='b'*64,session_sha256='c'*64),
                '.runtime/P128_report_collector_once_end.json':dict(status='complete',planned_conditions=16,development_gate_met=False,audit_errors=1,exact_total_tokens=None,
                    copied_source_sha256={'reports/P128_comparison.json':'b'*64,'reports/P128_server_session.json':'c'*64}),
                '.runtime/P128_pipeline_once_start.json':dict(source_head='a'*40),
                '.runtime/P128_report_collector_once_start.json':dict(source_head='a'*40)}
            def write(data):
                for name,value in data.items():
                    path=storage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
            write(values)
            values['.runtime/P128_report_collector_once_start.json']['closure_sha256']=driver.sha(storage/'.runtime/P128_closure_once_end.json')
            write(values)
            with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                result=driver.launch_predecessor_closed(storage)
                self.assertEqual(set(result),set(values))
                for name,change in (
                    ('records/context_pilot/P128_pipeline_v01/status.json',dict(status='batch')),
                    ('records/context_pilot/P128_pipeline_v01/status.json',dict(server_stopped=False)),
                    ('records/context_pilot/P128_pipeline_v01/status.json',dict(phase='P127_pipeline')),
                    ('records/context_pilot/P128_pipeline_v01/server_final.json',dict(supervisor_pid=999)),
                    ('records/context_pilot/P128_pipeline_v01/server_final.json',dict(pid='invalid')),
                    ('records/context_pilot/P128_pipeline_v01/server_final.json',dict(pid=True)),
                    ('records/context_pilot/P128_batch_v01/status.json',dict(planned=['wrong']*16)),
                    ('.runtime/P128_report_collector_once_end.json',dict(planned_conditions=16.0)),
                    ('.runtime/P128_report_collector_once_start.json',dict(source_head='d'*40)),
                    ('.runtime/P128_report_collector_once_start.json',dict(closure_sha256='d'*64)),
                    ('.runtime/P128_report_collector_once_end.json',dict(copied_source_sha256={})),
                    ('.runtime/P128_report_collector_once_end.json',dict(status='running'))):
                    changed=deepcopy(values);changed[name].update(change);write(changed)
                    with self.subTest(change=change),self.assertRaises(ValueError):driver.launch_predecessor_closed(storage)
                write(values)
            with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='owned model server')):
                with self.assertRaisesRegex(ValueError,'process_present'):driver.launch_predecessor_closed(storage)


if __name__=='__main__':unittest.main()

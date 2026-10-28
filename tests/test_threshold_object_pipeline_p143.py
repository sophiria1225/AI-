"""P143 finite launch/owned lease and pure six-shape checks; no live services."""
from copy import deepcopy
import datetime as dt
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_threshold_object_pipeline_p143 as pipeline
import threshold_object_server_identity_p143 as identity
from checkpoint_threshold_object_preflight_p143 import synthetic_transport_cases
from public_display import CODE_TOOLS


def finite_plan():
    return dict(server_max_lifetime_seconds=12000, batch_timeout_seconds=11400,
        latest_launch_jst='2026-10-28T10:55:00+09:00',
        deadline_jst='2026-10-28T14:15:00+09:00')


class PipelineTests(unittest.TestCase):
    def test_eight_full_cells_and_all_startup_stages_fit_finite_lease(self):
        pipeline.validate_timing_limits(finite_plan())
        for changes in ({'batch_timeout_seconds':11279}, {'batch_timeout_seconds':11551},
                        {'batch_timeout_seconds':float('inf')}, {'batch_timeout_seconds':True},
                        {'server_max_lifetime_seconds':12001}, {'server_max_lifetime_seconds':9000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                pipeline.validate_timing_limits(finite_plan() | changes)

    def test_deadlines_cannot_be_extended_or_naive(self):
        for changes in ({'latest_launch_jst':'2026-10-28T10:56:00+09:00'},
                        {'deadline_jst':'2026-10-28T15:00:00+09:00'},
                        {'deadline_jst':'2026-10-28T14:15:00'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                pipeline.validate_timing_limits(finite_plan() | changes)

    def test_last_launch_boundary_rechecks_stop_authority_and_time(self):
        plan = finite_plan(); resume = {'synthetic_authority':True}
        now = dt.datetime.fromisoformat(plan['latest_launch_jst']).timestamp()
        with tempfile.TemporaryDirectory() as temporary:
            storage = Path(temporary); (storage/'.runtime').mkdir()
            with patch.object(pipeline, 'check_resume', return_value=resume), patch.object(pipeline.time, 'time', return_value=now):
                pipeline.launch_boundary(storage, plan, resume)
                with patch.object(pipeline.time, 'time', return_value=now+1), self.assertRaises(ValueError):
                    pipeline.launch_boundary(storage, plan, resume)
                with patch.object(pipeline, 'check_resume', return_value={'changed':True}), self.assertRaises(ValueError):
                    pipeline.launch_boundary(storage, plan, resume)
                (storage/'.runtime/P143.stop').write_text('stop')
                with self.assertRaises(InterruptedError):
                    pipeline.launch_boundary(storage, plan, resume)

    def test_owned_lease_rejects_wrong_namespace_options_and_parent_claim(self):
        now = dt.datetime(2026,10,28,0,0,tzinfo=dt.timezone.utc)
        runtime = dict(supervisor_pid=1234,pid=1235,
            record_directory='records/p2_servers/SYNTHETIC',started_at=now.isoformat())
        owner = dict(phase='P143_pipeline',status='preflight',server_owned=True,
            server_supervisor_pid=1234,server_record_directory=runtime['record_directory'])
        source = dict(model_selection='synthetic-selection',model={'num_ctx':65536})
        storage = Path('/synthetic-storage')
        args = ['synthetic-python', str(identity.ROOT/identity.SUPERVISOR),
            '--storage-root',str(storage),'--selection','synthetic-selection',
            '--ctx-size','65536','--cache-type-k','q8_0','--cache-type-v','q8_0',
            '--max-seconds','12000']
        remaining, _ = identity.owned_lease(runtime, shlex.join(args), now,
            storage=storage,source_plan=source,owner=owner)
        self.assertEqual(remaining,12000)
        for changed in (owner | {'phase':'P142_pipeline'}, owner | {'server_supervisor_pid':999},
                        owner | {'server_owned':False}):
            with self.assertRaises(ValueError):
                identity.owned_lease(runtime,shlex.join(args),now,storage=storage,source_plan=source,owner=changed)
        for tail in ('9000','12001'):
            with self.assertRaises(ValueError):
                identity.owned_lease(runtime,shlex.join(args[:-1]+[tail]),now,
                    storage=storage,source_plan=source,owner=owner)

    def test_six_pure_shapes_are_four_focus_two_actor_with_both_first_prompts(self):
        with (patch('subprocess.Popen',side_effect=AssertionError('NO_PROCESS')),
              patch('urllib.request.urlopen',side_effect=AssertionError('NO_NETWORK'))):
            cases=synthetic_transport_cases()
        self.assertEqual(len(cases),6)
        self.assertEqual(len({c['name'] for c in cases}),6)
        self.assertEqual(sum(c['role']=='focus' for c in cases),4)
        self.assertEqual(sum(c['role']=='agent' for c in cases),2)
        self.assertTrue(all(c['synthetic_only'] for c in cases))
        self.assertEqual({c['mode'] for c in cases},{'threshold_recursive','threshold_delta_object'})
        self.assertEqual(cases[0]['messages'],cases[1]['messages'])
        self.assertNotEqual(cases[2]['messages'][0],cases[3]['messages'][0])
        self.assertEqual(cases[2]['messages'][1],cases[3]['messages'][1])
        self.assertNotEqual(cases[4]['messages'],cases[5]['messages'])
        self.assertTrue(all(c['tools']==([] if c['role']=='focus' else CODE_TOOLS) for c in cases))
        before=deepcopy(cases)
        cases[0]['messages'][0]['content']='changed'
        self.assertEqual(synthetic_transport_cases(),before)


if __name__ == '__main__':
    unittest.main()

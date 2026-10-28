"""P144R1 finite launch and owned process closure; external execution is mocked."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_state_update_resume_p144r1 as driver
import state_update_resume_server_p144r1 as identity


def fixed_spec():
    return dict(phase='P144R1', inherited_plan='configs/P144_state_update_v01.json',
        remaining_run_ids=list(driver.remaining_ids()),
        canonical_remaining_run_ids=[driver.original_cell_id(n, m) for n, m in driver.REMAINING],
        max_new_cells=10, max_new_model_calls=800, max_new_reserved_tokens=4500000,
        max_new_environment_api_requests=880, max_new_evaluator_calls=10,
        server_max_lifetime_seconds=21000, batch_timeout_seconds=20220,
        latest_launch_jst='2026-10-28T17:20:00+09:00',
        deadline_jst='2026-10-28T23:15:00+09:00',
        reporting_deadline_jst='2026-10-28T23:59:00+09:00',
        automatic_retries=0, regenerate_completed_cells=False,
        choose_conditions_from_outcomes=False, reserved_scenarios_read=0)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class ResumePipelineTests(unittest.TestCase):
    def test_signal_is_deferred_until_spawn_handle_is_retained_and_handler_restored(self):
        previous = signal.getsignal(signal.SIGTERM)
        steps = []
        def old_handler(*_):
            raise AssertionError('original handler must not run inside spawn context')
        signal.signal(signal.SIGTERM, old_handler)
        try:
            with self.assertRaises(InterruptedError):
                with driver.retain_spawn_handle():
                    os.kill(os.getpid(), signal.SIGTERM)
                    steps.append('owned handle retained after signal')
            self.assertEqual(steps, ['owned handle retained after signal'])
            self.assertIs(signal.getsignal(signal.SIGTERM), old_handler)
        finally:
            signal.signal(signal.SIGTERM, previous)

    def test_child_does_not_inherit_a_blocked_sigterm_and_terminates_normally(self):
        child = None
        try:
            with driver.retain_spawn_handle():
                child = subprocess.Popen([sys.executable, '-c',
                    'import signal; print(signal.SIGTERM not in signal.pthread_sigmask(signal.SIG_BLOCK, set()), flush=True); signal.pause()'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertTrue(select.select([child.stdout], [], [], 5)[0])
            self.assertEqual(child.stdout.readline().strip(), 'True')
            child.terminate()
            self.assertEqual(child.wait(timeout=5), -signal.SIGTERM)
        finally:
            if child is not None:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                child.stdout.close()
                child.stderr.close()

    def test_cancellation_inside_popen_still_retains_and_closes_returned_child(self):
        class Child:
            pid = 45678
            returncode = None
            def poll(self): return self.returncode
            def terminate(self): self.returncode = -15
            def wait(self, timeout): return self.returncode
        child = Child()
        def spawn(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
            return child
        with tempfile.TemporaryDirectory() as temp, patch.object(driver.subprocess, 'Popen', side_effect=spawn):
            record = {}
            with self.assertRaises(InterruptedError):
                driver.bounded_process(['synthetic'], Path(temp) / 'once.log', record,
                    lambda:None, 10, absolute_end=driver.time.time()+30)
        self.assertEqual(record['pid'], child.pid)
        self.assertEqual(record['status'], 'exited')
        self.assertEqual(child.poll(), -15)

    def test_exact_ten_slots_limits_deadlines_and_no_retry_are_fixed(self):
        spec = fixed_spec()
        driver.validate_spec(spec)
        self.assertLessEqual(300 + 180 + 30 + spec['batch_timeout_seconds'], identity.LEASE_SECONDS)
        self.assertGreaterEqual(spec['batch_timeout_seconds'], 10 * driver.CELL_SECONDS)
        changes = ({'remaining_run_ids':spec['remaining_run_ids'][::-1]},
            {'remaining_run_ids':spec['remaining_run_ids'][:-1]},
            {'canonical_remaining_run_ids':spec['canonical_remaining_run_ids'] + ['repeat']},
            {'max_new_cells':True}, {'max_new_cells':11}, {'max_new_model_calls':801},
            {'max_new_reserved_tokens':4500001}, {'max_new_environment_api_requests':881},
            {'max_new_evaluator_calls':11}, {'automatic_retries':1},
            {'regenerate_completed_cells':True}, {'choose_conditions_from_outcomes':True},
            {'reserved_scenarios_read':1}, {'server_max_lifetime_seconds':21001},
            {'batch_timeout_seconds':20100}, {'deadline_jst':'2026-10-29T00:00:00+09:00'},
            {'latest_launch_jst':'2026-10-28T17:21:00+09:00'})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                driver.validate_spec(spec | change)

    def test_launch_checks_current_stop_latest_time_and_full_lease(self):
        spec = fixed_spec()
        latest = driver.datetime.fromisoformat(spec['latest_launch_jst']).timestamp()
        with tempfile.TemporaryDirectory() as temp:
            storage = Path(temp)
            (storage / '.runtime').mkdir()
            # Historical stop remains in place and does not revoke the new authority.
            (storage / '.runtime/P144.stop').write_text('historical stop')
            with patch.object(driver.time, 'time', return_value=latest):
                driver.launch_boundary(storage, spec)
            with patch.object(driver.time, 'time', return_value=latest + .001):
                with self.assertRaises(ValueError):
                    driver.launch_boundary(storage, spec)
            (storage / driver.STOP).write_text('new explicit stop')
            with patch.object(driver.time, 'time', return_value=latest), self.assertRaises(InterruptedError):
                driver.launch_boundary(storage, spec)
            self.assertEqual((storage / '.runtime/P144.stop').read_text(), 'historical stop')
        end = driver.datetime.fromisoformat(spec['deadline_jst']).timestamp()
        with tempfile.TemporaryDirectory() as temp, patch.object(driver, 'validate_spec'), \
                patch.object(driver.time, 'time', side_effect=[latest, end - identity.LEASE_SECONDS + 1]):
            with self.assertRaises(ValueError):
                driver.launch_boundary(Path(temp), spec)

    def test_bounded_process_failure_timeout_and_owned_group_cleanup(self):
        for kind in ('nonzero', 'timeout', 'timeout_then_kill', 'interrupt', 'spawn_failure'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'once.log'
                record, snapshots, killed = {}, [], []
                class Child:
                    pid = 34567
                    returncode = None
                    waits = 0
                    terminations = 0
                    def poll(self):
                        return self.returncode
                    def terminate(self):
                        self.terminations += 1
                    def wait(self, timeout):
                        self.waits += 1
                        if kind == 'nonzero':
                            self.returncode = 9
                            return 9
                        if self.waits == 1:
                            if kind == 'interrupt':
                                raise InterruptedError('synthetic interrupt')
                            raise subprocess.TimeoutExpired('synthetic child', timeout)
                        if kind == 'timeout_then_kill' and self.waits == 2:
                            raise subprocess.TimeoutExpired('synthetic cleanup', timeout)
                        self.returncode = -15
                        return self.returncode
                child = Child()
                def killpg(pid, signum):
                    killed.append((pid, signum))
                popen = {'side_effect':OSError('synthetic spawn failure')} if kind == 'spawn_failure' else {'return_value':child}
                with patch.object(driver.subprocess, 'Popen', **popen) as launch, \
                        patch.object(driver.os, 'killpg', side_effect=killpg), \
                        patch.object(driver.time, 'time', return_value=100):
                    with self.assertRaises((RuntimeError, subprocess.TimeoutExpired, InterruptedError, OSError)):
                        driver.bounded_process(['synthetic'], path, record,
                            lambda:snapshots.append(dict(record)), 20, absolute_end=200)
                self.assertEqual(launch.call_count, 1)
                self.assertTrue(snapshots)
                self.assertEqual(record['status'], 'not_started' if kind == 'spawn_failure' else 'exited')
                if kind != 'spawn_failure':
                    self.assertIsNotNone(child.poll())
                self.assertEqual(killed, [(child.pid, signal.SIGKILL)] if kind == 'timeout_then_kill' else [])
                self.assertEqual(record['timed_out'], kind in ('timeout', 'timeout_then_kill'))

    def test_pipeline_closes_owned_server_before_reporting_after_stage_failure(self):
        for failed in (False, True):
            with self.subTest(stage_failed=failed), tempfile.TemporaryDirectory() as temp:
                root, storage = Path(temp) / 'repo', Path(temp) / 'storage'
                root.mkdir()
                (storage / 'records/context_pilot').mkdir(parents=True)
                spec = fixed_spec()
                write(root / driver.SPEC, spec)
                runtime_path = storage / '.runtime/model_server.json'
                runtime = dict(supervisor_pid=12345, pid=12346, status='ready',
                    record_directory='records/p2_servers/SYNTHETIC_ONLY')
                write(runtime_path, runtime)
                class Process:
                    def __init__(self, pid, server=False):
                        self.pid, self.returncode, self.server = pid, None, server
                    def poll(self):
                        return self.returncode
                    def terminate(self):
                        self.returncode = 0
                        if self.server:
                            write(runtime_path, runtime | {'status':'stopped'})
                    def wait(self, timeout):
                        return self.returncode
                caffeinate, server = Process(12344), Process(12345, True)
                calls = []
                def bounded(command, log, record, save, timeout, **kwargs):
                    reporting = 'audit_state_update_resume_p144r1.py' in command[1]
                    calls.append('report' if reporting else command[-1])
                    if reporting:
                        self.assertIsNotNone(server.poll())
                        self.assertIsNotNone(caffeinate.poll())
                    elif failed:
                        raise RuntimeError('synthetic stage failure')
                    record.update(returncode=0, status='exited')
                    save()
                with patch.object(driver, 'sources', return_value=(None, {'model_selection':'synthetic', 'model':{'num_ctx':65536}}, None, None)), \
                        patch.object(driver, 'checked_ci', return_value={'synthetic':True}), \
                        patch.object(driver, 'launch_boundary'), \
                        patch.object(driver, 'frozen_hashes', return_value={}), \
                        patch.object(driver, 'sha', return_value='synthetic hash'), \
                        patch.object(driver.subprocess, 'check_output', side_effect=['synthetic head\n', '']), \
                        patch.object(driver.subprocess, 'Popen', side_effect=[caffeinate, server]), \
                        patch.object(driver, 'bounded_process', side_effect=bounded), \
                        patch.object(driver.time, 'time', return_value=driver.datetime.fromisoformat(spec['latest_launch_jst']).timestamp()):
                    result = driver.pipeline(storage, root, 'synthetic head')
                self.assertEqual(result, 1 if failed else 0)
                self.assertEqual(calls, ['--preflight', 'report'] if failed else
                    ['--preflight', '--activation', '--batch', 'report'])
                state = json.loads((storage / driver.PIPELINE / 'status.json').read_text())
                self.assertTrue(state['server_stopped'])
                self.assertFalse(state['prior_session_continuous'])
                self.assertEqual(state['status'], 'stopped' if failed else 'complete')


if __name__ == '__main__':
    unittest.main()

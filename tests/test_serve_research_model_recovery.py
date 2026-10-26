"""Synthetic port-only tests; no model, HTTP, tokenizer, or backend startup."""
import errno
import io
import json
import os
import socket
import shutil
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import serve_research_model_recovery as recovery


class RecoveryPortTest(unittest.TestCase):
    def setUp(self):
        self.which_patch=patch.object(recovery.shutil,'which',return_value=shutil.which('lsof') or '/synthetic/lsof')
        self.which_patch.start();self.addCleanup(self.which_patch.stop)

    def test_storage_root_argument_reaches_verified_model_before_launch(self):
        class StopBeforeModel(Exception): pass
        with tempfile.TemporaryDirectory() as directory, patch.object(sys,'argv',['recovery','--storage-root',directory]), patch.object(recovery,'verified_model',side_effect=StopBeforeModel) as verify, patch.object(recovery.subprocess,'Popen') as popen:
            with self.assertRaises(StopBeforeModel): recovery.main()
            verify.assert_called_once_with(recovery.LEGACY_SELECTION,root=Path(directory).resolve())
            popen.assert_not_called()

    def test_supervisor_records_and_backend_paths_remain_in_storage_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);storage=base/'storage';implementation=base/'implementation'
            (storage/'records/models').mkdir(parents=True);(storage/'.runtime').mkdir()
            (implementation/'scripts').mkdir(parents=True)
            (implementation/'scripts/model_provenance.py').write_text('# synthetic source\n')
            (storage/'records/models/p2_runtime_install.json').write_text(json.dumps({'runtime':'synthetic','server_path':'bin/backend'}))
            selection={'runtime':'synthetic','model_alias':'fake','revision':'fixed','quantization':'fake'}
            child=Mock(pid=321,returncode=0);child.poll.return_value=0
            with patch.object(sys,'argv',['recovery','--storage-root',str(storage)]), patch.object(recovery,'ROOT',implementation), patch.object(recovery,'verified_model',return_value=(selection,{},storage/'model')), patch.object(recovery,'probe_reusable_loopback_port',return_value={'synthetic':True}), patch.object(recovery.urllib.request,'urlopen',return_value=io.BytesIO(b'{"models":[]}')), patch.object(recovery.signal,'signal'), patch.object(recovery.subprocess,'Popen',return_value=child) as popen, patch.object(recovery,'memory_sample',return_value={'swap_used_bytes':0}), patch('builtins.print'):
                self.assertFalse(recovery.main())
            state=json.loads((storage/'.runtime/model_server.json').read_text())
            out=storage/state['record_directory']
            self.assertTrue((out/'summary.json').is_file())
            self.assertTrue((out/'serve_research_model_recovery.py').is_file())
            self.assertFalse((implementation/'.runtime/model_server.json').exists())
            self.assertEqual(popen.call_args.args[0][0],str(storage/'bin/backend'))
            child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_missing_inspector_fails_closed(self):
        with patch.object(recovery.shutil,'which',return_value=None),patch.object(recovery.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):recovery.listener_pids(8011)
            run.assert_not_called()

    def test_inspection_absent_is_empty(self):
        with patch.object(recovery.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')) as run:
            self.assertEqual(recovery.listener_pids(8011), set())
            argv = run.call_args.args[0]
            self.assertIn('-sTCP:LISTEN', argv)
            self.assertEqual(Path(argv[0]).name, 'lsof')

    def test_listener_inspection_strict_and_deduplicated(self):
        with patch.object(recovery.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '12\n12\n45\n', '')):
            self.assertEqual(recovery.listener_pids(8011), {12, 45})
        for code, stdout, stderr in [(0, '', ''), (1, '12\n', ''), (2, '', ''), (1, '', 'denied'), (0, 'true\n', ''), (0, '0\n', ''), (0, '12\n', 'warning')]:
            with self.subTest(code=code, stdout=stdout, stderr=stderr), patch.object(recovery.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, stdout, stderr)):
                with self.assertRaises(RuntimeError): recovery.listener_pids(8011)

    def test_invalid_port_does_not_run_process(self):
        with patch.object(recovery.subprocess, 'run') as run:
            for p in [True, False, 0, 65536, '8011', 8011.0]:
                with self.subTest(port=p), self.assertRaises(ValueError): recovery.listener_pids(p)
            run.assert_not_called()

    def test_existing_listener_refuses_before_socket(self):
        with patch.object(recovery, 'listener_pids', return_value={123}), patch.object(recovery.socket, 'socket') as create:
            with self.assertRaises(RuntimeError): recovery.probe_reusable_loopback_port(8011)
            create.assert_not_called()

    def test_only_reuseaddr_set_no_reuseport(self):
        sock=Mock();ctx=Mock();ctx.__enter__=Mock(return_value=sock);ctx.__exit__=Mock(return_value=False)
        with patch.object(recovery, 'listener_pids', return_value=set()), patch.object(recovery.socket, 'socket', return_value=ctx):
            result=recovery.probe_reusable_loopback_port(8011)
        sock.setsockopt.assert_called_once_with(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind.assert_called_once_with(('127.0.0.1',8011))
        self.assertFalse(result['reuse_port']);self.assertFalse(result['probe_is_port_reservation'])

    def test_backend_race_bind_failure_preserved(self):
        sock=Mock();sock.bind.side_effect=OSError(errno.EADDRINUSE,'in use');ctx=Mock();ctx.__enter__=Mock(return_value=sock);ctx.__exit__=Mock(return_value=False)
        with patch.object(recovery,'listener_pids',return_value=set()),patch.object(recovery.socket,'socket',return_value=ctx):
            with self.assertRaises(OSError): recovery.probe_reusable_loopback_port(8011)

    def test_ready_requires_only_owned_pid(self):
        for pids,expected in [(set(),False),({12},True),({13},False),({12,13},False)]:
            with self.subTest(pids=pids),patch.object(recovery,'listener_pids',return_value=pids):
                self.assertEqual(recovery.owned_listener_ready(8011,12),expected)
        for pid in [True,0,-1,'12']:
            with self.subTest(pid=pid),self.assertRaises(ValueError): recovery.owned_listener_ready(8011,pid)

    @unittest.skipUnless(shutil.which('lsof'), 'listener inspector not installed')
    def test_real_active_listener_is_unchanged_and_not_stolen(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
            self.assertEqual(recovery.listener_pids(port),{os.getpid()})
            with self.assertRaises(RuntimeError): recovery.probe_reusable_loopback_port(port)
            self.assertEqual(recovery.listener_pids(port),{os.getpid()})
            self.assertTrue(recovery.owned_listener_ready(port,os.getpid()))

    @unittest.skipUnless(shutil.which('lsof'), 'listener inspector not installed')
    def test_real_time_wait_reuse_without_listener(self):
        # The accepted server endpoint actively closes first, leaving TIME_WAIT.
        listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
        client=socket.socket();client.settimeout(2);client.connect(('127.0.0.1',port));accepted,_=listener.accept()
        accepted.close();self.assertEqual(client.recv(1),b'');client.close();listener.close()
        with socket.socket() as strict:
            with self.assertRaises(OSError) as raised:strict.bind(('127.0.0.1',port))
            self.assertEqual(raised.exception.errno,errno.EADDRINUSE)
        self.assertEqual(recovery.listener_pids(port),set())
        self.assertTrue(recovery.probe_reusable_loopback_port(port)['reuse_address'])
        self.assertEqual(recovery.listener_pids(port),set())


if __name__=='__main__':unittest.main()

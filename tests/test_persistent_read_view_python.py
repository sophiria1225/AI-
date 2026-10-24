"""Trusted handwritten subprocess fixture; no Docker, model or task API."""
import json
from pathlib import Path
import select
import selectors
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from container_api_python import ApiChannel
from persistent_api_python import BOOTSTRAP as ORIGINAL_BOOTSTRAP
from persistent_read_view_python import (client_source, derived_bootstrap, ViewControlChannel,
                                         PersistentReadViewPython, ReadViewProgram)
from shared_api_reservations import BudgetedApiChannel
from test_deferred_view_protocol import setup
from probe_deferred_view_container import probe


class TrustedSubprocessSession(PersistentReadViewPython):
    """Exercise the real persistent run loop using only handwritten local code."""
    def __init__(self, folder, storage_root=None):
        Path(folder).mkdir(parents=True,exist_ok=True)
        self.storage_root = Path(storage_root if storage_root is not None else folder)
        self.folder = Path(folder)/'session';self.folder.mkdir()
        self.selection = {'image':'trusted-local-test-no-container',
                          'expected_python':sys.version.split()[0]}
        self.name = 'trusted-local-test';self.process = None;self.selector = None
        self.stderr = None;self.closed = False;self.usable = True
        self.controls = {'trusted_local_fixture':True};self.programs = []
        self.state = {'container_removed':False,'programs':self.programs}
        self._save()

    def _start(self):
        self.stderr = (self.folder/'stderr.txt').open('wb')
        self.process = subprocess.Popen([sys.executable,'-I','-S','-u','-c',derived_bootstrap()],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout,selectors.EVENT_READ)
        self.created_monotonic = time.monotonic()

    def close(self):
        if self.closed:return self.state
        if self.process is not None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            self.process.stdout.close();self.selector.close();self.stderr.close()
        self.closed = True
        self.state['trusted_local_process_stopped'] = self.process is None or self.process.poll() is not None
        self._save()
        return self.state


class PersistentReadViewBootstrapTests(unittest.TestCase):
    def run_fixture(self, programs, *, defer=True):
        b, raw, host, client, wire, rows = setup(defer=defer)
        process = subprocess.Popen([sys.executable,'-I','-S','-u','-c',derived_bootstrap()],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        results = []; controls = []
        try:
            for index, source in enumerate([client_source()]+programs,1):
                if index > 1:
                    host.attach(BudgetedApiChannel(ApiChannel(host.channel.catalog,host.channel.bridge,
                        b.limit-b.spent),b))
                control = ViewControlChannel(host,rows.append);controls.append(control)
                payload = dict(code=source,observations={},program_index=index,api_schemas={})
                process.stdin.write(json.dumps(payload).encode()+b'\n');process.stdin.flush()
                while True:
                    if not select.select([process.stdout],[],[],5)[0]:
                        self.fail('trusted fixture worker timed out')
                    line = process.stdout.readline()
                    if not line: self.fail('trusted fixture worker exited before done')
                    packet = json.loads(line)
                    self.assertEqual(packet['program_index'],index)
                    if packet['kind']=='done':
                        results.append(packet);break
                    reply = control.exchange({k:v for k,v in packet.items() if k!='program_index'})
                    process.stdin.write(json.dumps(reply).encode()+b'\n');process.stdin.flush()
            return b, raw, host, results[1:], controls[1:], rows
        finally:
            process.stdin.close()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5)
            stderr=process.stderr.read().decode();process.stdout.close();process.stderr.close()
            self.assertEqual(process.returncode,0,stderr)

    def test_alias_survives_program_boundary_and_both_policies_export_same_value(self):
        outcomes=[]
        for defer in (False,True):
            b, raw, host, results, controls, rows = self.run_fixture([
                "saved={'track':read_view('fixture','echo',value={'title':'alpha','rating':1})}\nprint(saved['track']['title'])",
                "print(saved['track']['rating'])\nprint(call_api('fixture','echo',value=9))",
            ],defer=defer)
            self.assertTrue(all(r['error'] is None for r in results))
            outcomes.append([r['stdout'] for r in results])
            self.assertEqual(b.spent,2);self.assertEqual(b.pending,0)
            self.assertEqual(sum(r['api_request_sent'] for r in rows),2)
        self.assertEqual(outcomes[0],outcomes[1])

    def test_finally_flushes_dead_views_even_after_generated_python_exception(self):
        b, raw, host, results, controls, rows = self.run_fixture([
            "v=read_view('fixture','echo',value={'title':'alpha','rating':1})\nprint(v['title'])\ndel v\nraise ValueError('handwritten fixture')",
            "print(call_api('fixture','echo',value=8))",
        ])
        self.assertEqual(results[0]['error'],'ValueError: handwritten fixture')
        self.assertEqual(results[1]['stdout'],'8\n')
        self.assertEqual(controls[0].control_requests,2)  # read, release flush before done
        self.assertEqual(raw.world.effects,[('echo',8)])
        self.assertEqual(host.records,{});self.assertEqual(b.spent,1);self.assertEqual(b.pending,0)

    def test_control_channel_rejects_raw_api_bypass_without_dispatch(self):
        b, raw, host, client, wire, rows = setup()
        ch=ViewControlChannel(host)
        with self.assertRaises(ValueError):
            ch.exchange(dict(kind='api',id=1,app='fixture',api='echo',arguments={'value':9}))
        self.assertEqual(raw.commands,[]);self.assertEqual(b.spent,0)

    def test_original_runtime_is_unchanged_and_client_source_fits_existing_limit(self):
        self.assertNotIn('_harness_read_views_v1',ORIGINAL_BOOTSTRAP)
        self.assertLess(len(client_source()),20000)
        compile(client_source(),'<trusted fixture client>','exec')

    def test_real_program_adapter_preserves_code_counts_setup_and_records_actual_apis(self):
        for defer in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                b, raw, host, client, wire, rows = setup(defer=defer)
                session = TrustedSubprocessSession(tmp)
                adapter = ReadViewProgram(session,b,authority=host.authority,defer=defer)
                try:
                    sources = ["saved=read_view('fixture','echo',value={'title':'alpha','rating':1})\nprint(saved['title'])",
                               "print(saved['rating'])\nprint(call_api('fixture','echo',value=9))"]
                    for index, source in enumerate(sources):
                        base = ApiChannel(host.channel.catalog,host.channel.bridge,b.limit-b.spent)
                        folder = Path(tmp)/f'program_{index}'
                        result = adapter(source,{},base,storage_root=tmp,record_dir=folder,
                                         timeout=5,on_record=rows.append)
                        self.assertEqual(result['status'],'ok')
                        saved = json.loads((folder/'input_private.json').read_text())
                        self.assertEqual(saved['code'],source)
                        record = json.loads((folder/'view_program_private.json').read_text())
                        self.assertGreater(record['control_requests'],0)
                        self.assertEqual(record['setup'] is not None,index==0)
                    self.assertEqual(len(session.programs),3)  # counted setup plus both user programs
                    self.assertEqual(b.spent,2)
                    self.assertEqual(sum(r['api_request_sent'] for r in rows),2)
                    self.assertTrue(all(r['action']['name']=='fixture__echo' for r in rows))
                finally:session.close()
                self.assertTrue(session.state['trusted_local_process_stopped'])

    def test_known_contract_failure_stops_session_without_relabelling_it_unknown_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, raw, host, client, wire, rows = setup()
            session = TrustedSubprocessSession(tmp)
            adapter = ReadViewProgram(session,b,authority=host.authority)
            try:
                base = ApiChannel(host.channel.catalog,host.channel.bridge,b.limit-b.spent)
                # The authority initially copies title from this argument. The
                # handwritten fixture then returns a contradictory response.
                original = raw.request
                def inconsistent(command):
                    command = json.loads(json.dumps(command))
                    command['call']['args']['value']['title']='changed'
                    return original(command)
                raw.request = inconsistent
                result = adapter("v=read_view('fixture','echo',value={'title':'alpha','rating':1})\nprint(v['rating'])",
                    {},base,storage_root=tmp,record_dir=Path(tmp)/'failed',timeout=5,on_record=rows.append)
                self.assertEqual(result['status'],'harness_error')
                self.assertFalse(result['unknown_effects']);self.assertFalse(result['session_usable'])
                self.assertTrue(session.closed);self.assertEqual(result['api_requests'],1)
                self.assertEqual(b.spent,1);self.assertTrue(b.stopped)
            finally:session.close()

    def test_fixed_smoke_programs_and_catalog_through_local_subprocess_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'reports').mkdir()
            (root/'reports/deferred_view_runtime_preparation_20261024.json').write_text(
                json.dumps({'source_sha256':{}}))
            with patch('probe_deferred_view_container.PersistentReadViewPython',
                       side_effect=lambda storage,folder:TrustedSubprocessSession(folder,storage)):
                result=probe(root,root/'output',root)
            self.assertEqual(result['status'],'complete')
            self.assertEqual([c['fixture_requests'] for c in result['conditions']],[4,3])
            self.assertTrue(result['observations_equal'])
            self.assertTrue(all(c['cleanup']['trusted_local_process_stopped'] for c in result['conditions']))


if __name__=='__main__':unittest.main()

"""Handwritten discovery fixtures; no model, AppWorld state, or network calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from agent_read_view_runtime import AgentReadViewPython
from container_api_python import ApiChannel
from field_read_contract import CONTRACT_ID
from ordinary_complete_read_cache import OrdinaryCachedReadProgram
from public_api_result_transport import PublicResultTransport
from public_name_catalog import PublicNameCatalog
from shared_api_reservations import RequestBudget
from test_persistent_read_view_python import TrustedSubprocessSession
from test_public_api_result_transport import FixtureTransport
from test_public_name_catalog import tool


class ForwardingFixtureSession(AgentReadViewPython, TrustedSubprocessSession):
    pass


class DiscoveryWorld:
    def __init__(self, fail=False):
        self.fail = fail; self.complete = False; self.effects = []
        self.task = SimpleNamespace(api_docs={
            'api_docs':{'show_api_doc':{'parameters':[{'name':'app_name'},{'name':'api_name'}]}},
            'fixture':{'echo':{'parameters':[{'name':'value'}]}, 'finish':{'parameters':[]}}})

    def execute(self, source):
        def document(app_name, api_name):
            self.effects.append('document')
            if self.fail: raise ValueError('synthetic documentation error')
            return {'api_name':api_name, 'app_name':app_name}
        def echo(value):
            self.effects.append('echo'); return value
        def finish():
            self.effects.append('finish'); self.complete = True; return {'done':True}
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            exec(compile(source,'<trusted discovery fixture>','exec'), {'apis':SimpleNamespace(
                api_docs=SimpleNamespace(show_api_doc=document),
                fixture=SimpleNamespace(echo=echo, finish=finish))})
        return capture.getvalue()

    def task_completed(self): return self.complete


class AgentReadViewRuntimeTests(unittest.TestCase):
    def exercise(self, sources, *, forwarding=True, fail=False, defer=True):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cls=ForwardingFixtureSession if forwarding else TrustedSubprocessSession
            session=cls(root); raw=FixtureTransport(); raw.world=DiscoveryWorld(fail)
            transport=PublicResultTransport(raw); budget=RequestBudget(8)
            catalog=PublicNameCatalog([
                tool('api_docs__show_api_doc',{'app_name':{},'api_name':{}}),
                tool('fixture__echo',{'value':{}}),tool('fixture__finish')])
            adapter=OrdinaryCachedReadProgram(session,budget,execution_scope='schema-fixture',
                                              verified_contract=CONTRACT_ID,defer=defer)
            results=[]; reports=[]; rows=[]
            try:
                for index, source in enumerate(sources):
                    folder=root/f'program_{index}'
                    result=adapter(source,{},ApiChannel(catalog,transport,budget.limit-budget.spent),
                        storage_root=root,record_dir=folder,timeout=5,on_record=rows.append)
                    results.append(result)
                    if forwarding:
                        report=json.loads((folder/'schema_forwarding_private.json').read_text())
                        self.assertEqual(report['extra_API_requests'],0)
                        self.assertTrue(report['generated_source_unchanged'])
                        reports.append(report)
            finally:session.close()
            self.assertTrue(session.state['trusted_local_process_stopped'])
            return SimpleNamespace(results=results,reports=reports,rows=rows,budget=budget,
                effects=raw.world.effects,catalog=catalog,receipts=transport.receipts)

    def test_discovery_is_visible_immediately_not_only_in_the_next_program(self):
        sources=["print('fixture__echo' in api_schemas)\n"
                 "call_api('api_docs','show_api_doc',app_name='fixture',api_name='echo')\n"
                 "print('fixture__echo' in api_schemas)\n"
                 "print(call_api('fixture','echo',value=7))",
                 "print('fixture__echo' in api_schemas)"]
        old=self.exercise(sources,forwarding=False)
        self.assertEqual([r['stdout'] for r in old.results],['False\nFalse\n7\n','True\n'])
        for defer in (False,True):
            new=self.exercise(sources,defer=defer)
            self.assertEqual([r['stdout'] for r in new.results],['False\nTrue\n7\n','True\n'])
            self.assertTrue(all(r['status']=='ok' for r in new.results))
            self.assertEqual((new.budget.spent,new.effects),(2,['document','echo']))
            self.assertEqual([r['schema_deliveries'] for r in new.reports],[1,0])
            self.assertGreater(new.reports[0]['reply_wire_bytes'],0)

    def test_failed_documentation_does_not_expose_a_schema(self):
        r=self.exercise(["try:\n call_api('api_docs','show_api_doc',app_name='fixture',api_name='echo')\n"
                         "except RuntimeError: pass\nprint('fixture__echo' in api_schemas)"],fail=True)
        self.assertEqual(r.results[0]['stdout'],'False\n')
        self.assertEqual(r.results[0]['status'],'ok')
        self.assertEqual(r.reports[0]['schema_deliveries'],0)
        self.assertNotIn('fixture__echo',r.catalog.visible)
        self.assertEqual((r.budget.spent,r.receipts[0]['status']),(1,'raised'))

    def test_known_name_call_does_not_disclose_an_unrequested_schema(self):
        r=self.exercise(["print(call_api('fixture','echo',value=9))\n"
                         "print('fixture__echo' in api_schemas)"])
        self.assertEqual(r.results[0]['stdout'],'9\nFalse\n')
        self.assertEqual((r.budget.spent,r.reports[0]['schema_deliveries']),(1,0))

    def test_completion_remains_terminal_with_exact_dispatch_accounting(self):
        for defer in (False,True):
            r=self.exercise(["print(call_api('fixture','finish'))"],defer=defer)
            self.assertEqual(r.results[0]['status'],'ok')
            self.assertTrue(r.results[0]['declared_complete'])
            self.assertFalse(r.results[0]['unknown_effects'])
            self.assertTrue(r.budget.stopped)
            self.assertEqual((r.budget.spent,len(r.rows),len(r.receipts)),(1,1,1))

    def test_local_schema_changes_do_not_mutate_the_host_catalog(self):
        r=self.exercise(["call_api('api_docs','show_api_doc',app_name='fixture',api_name='echo')\n"
                         "api_schemas['fixture__echo']['parameters']['properties'].clear()"])
        self.assertEqual(r.results[0]['status'],'ok')
        self.assertIn('value',r.catalog.catalog['fixture__echo']['function']['parameters']['properties'])


if __name__=='__main__':unittest.main()

"""Synthetic recorded controls only; no model, AppWorld or network execution."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from replay_read_view_controls import replay_cell
from public_api_envelope import PROTOCOL
from public_name_catalog import PublicNameCatalog
from test_public_name_catalog import tool
from test_public_read_views_live_probe import Fixture, catalog
from test_whole_task_read_view_worker import fixture, PROGRAMS


TOOLS = list(catalog().catalog.values()) + [tool('supervisor__complete_task')]
FINISH = "call_api('supervisor','complete_task')"


class ControlReplayTests(unittest.TestCase):
    def exercise(self, policy, *, programs=PROGRAMS, public_tools=TOOLS, **options):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        with patch('test_whole_task_read_view_worker.PROGRAMS', programs):
            data=fixture(Path(tmp.name),policy,**options)
        # Creating a synthetic recording may execute handwritten fixture code.
        # The replay itself must never enter any interpreter/transport process.
        with patch('subprocess.Popen',side_effect=AssertionError('replay must not execute code')):
            report=replay_cell(data['folder'],public_tools)
        return data,report

    def test_exact_replies_budgets_and_dispatched_rows_under_both_policies(self):
        for policy in ('eager_cached','coalesced_cached'):
            data,r=self.exercise(policy)
            self.assertTrue(r['exact_factual_reply_replay'])
            self.assertEqual(r['replayed_API_receipts'],3)
            self.assertEqual(r['deferred_groups'],int(policy=='coalesced_cached'))
            self.assertEqual(r['disposition_counts'],{'explicit_materialization':1} if policy=='coalesced_cached' else {})

    def test_last_reference_release_cancels_without_a_later_full_fetch(self):
        _,r=self.exercise('coalesced_cached',programs=(PROGRAMS[0], 'del v\n'+FINISH))
        self.assertEqual(r['disposition_counts'],{'last_reference_release':1})
        self.assertEqual(r['replayed_API_receipts'],2)

    def test_retained_reference_is_materialized_at_a_conservative_barrier(self):
        _,r=self.exercise('coalesced_cached',programs=(PROGRAMS[0],FINISH))
        self.assertEqual(r['disposition_counts'],{'conservative_barrier':1})
        self.assertEqual(r['replayed_API_receipts'],3)

    def test_separate_complete_response_is_distinct_from_unused_release(self):
        source="call_api('spotify','show_song',song_id=10)\nprint(v['genre'])\ndel v\n"+FINISH
        _,r=self.exercise('coalesced_cached',programs=(PROGRAMS[0],source))
        self.assertEqual(r['disposition_counts'],{'separate_complete_response':1})
        self.assertEqual(r['replayed_API_receipts'],3)

    def test_two_aliases_share_one_reservation_and_only_last_release_cancels(self):
        source=PROGRAMS[0]+"\nw=read_view('spotify','show_song',song_id=10)\ndel v"
        _,r=self.exercise('coalesced_cached',programs=(source,'del w\n'+FINISH))
        self.assertEqual(r['deferred_groups'],1)
        self.assertEqual(r['lifetimes'][0]['largest_alias_count'],2)
        self.assertEqual(r['disposition_counts'],{'last_reference_release':1})

    def test_model_transport_loss_keeps_pending_separate_from_cancellation(self):
        _,r=self.exercise('coalesced_cached',unknown=True)
        self.assertEqual(r['pending_groups_at_stop'],1)
        self.assertEqual(r['disposition_counts'],{'pending_at_stop':1})
        self.assertEqual(r['replayed_API_receipts'],1)

    def test_explicit_stop_does_not_materialize_pending_values(self):
        _,r=self.exercise('coalesced_cached',stop=True)
        self.assertEqual(r['disposition_counts'],{'pending_at_stop':1})
        self.assertEqual(r['replayed_API_receipts'],1)

    def test_no_programs_remain_a_valid_zero_control_inventory(self):
        _,r=self.exercise('coalesced_cached',no_tool=True)
        self.assertEqual((r['control_requests'],r['deferred_groups'],r['replayed_API_receipts']),(0,0,0))

    def test_changed_reply_fingerprint_is_rejected(self):
        data,_=self.exercise('coalesced_cached')
        path=data['folder']/'programs/call_001_01/schema_forwarding_private.json'
        value=json.loads(path.read_text());value['exchanges'][0]['reply_wire_sha256']='0'*64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'replayed_control_reply_differs'):
            replay_cell(data['folder'],TOOLS)

    def test_saved_API_action_cannot_be_replaced_with_an_unrecorded_request(self):
        data,_=self.exercise('coalesced_cached')
        path=data['folder']/'bridge_02_private.json'
        value=json.loads(path.read_text());value['command']['call']['args']['page_index']=99
        path.write_text(json.dumps(value))
        # The host catches the mismatch as a failed control operation, whose
        # changed reply fingerprint is then rejected by the outer replay.
        with self.assertRaisesRegex(ValueError,'replayed_control_reply_differs'):
            replay_cell(data['folder'],TOOLS)

    def test_lost_API_reply_is_a_charged_attempt_not_an_unused_cancellation(self):
        class Lost(Fixture):
            def __init__(self):super().__init__(missing_fallback=True)
        with patch('test_whole_task_read_view_worker.Fixture',Lost):
            _,r=self.exercise('coalesced_cached')
        self.assertEqual(r['disposition_counts'],{'explicit_materialization':1})
        self.assertEqual(r['lifetimes'][0]['invocation_status'],'unknown')
        self.assertEqual(r['replayed_API_receipts'],2)

    def test_known_API_exception_preserves_barrier_fetch_and_no_retry(self):
        class Raised(Fixture):
            def __init__(self):super().__init__(mutation_error=True)
        code="try:\n call_api('spotify','like_song',song_id=10,access_token='synthetic-token')\nexcept RuntimeError: pass\n"+FINISH
        with patch('test_whole_task_read_view_worker.Fixture',Raised):
            _,r=self.exercise('coalesced_cached',programs=(PROGRAMS[0],code))
        self.assertEqual(r['disposition_counts'],{'conservative_barrier':1})
        self.assertEqual(r['replayed_API_receipts'],4)

    def test_same_program_public_schema_forwarding_is_reproduced(self):
        class Documented(Fixture):
            def request(self,command):
                if command['call']['app'] != 'api_docs':return super().request(command)
                self.calls.append(command['call'])
                env=dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',value={'documented':True})
                return {'ok':True,'result':dict(protocol=PROTOCOL,observation=json.dumps(env),declared_complete=False)}
        doc=tool('api_docs__show_api_doc',{'app_name':{},'api_name':{}})
        tools=TOOLS+[doc]
        code="call_api('api_docs','show_api_doc',app_name='spotify',api_name='show_song')\nprint('spotify__show_song' in api_schemas)"
        with patch('test_whole_task_read_view_worker.Fixture',Documented), \
             patch('test_whole_task_read_view_worker.catalog',side_effect=lambda:PublicNameCatalog(TOOLS[:-1]+[doc])):
            _,r=self.exercise('coalesced_cached',programs=(code,FINISH),public_tools=tools)
        self.assertEqual(r['replayed_API_receipts'],2)


if __name__=='__main__':unittest.main()

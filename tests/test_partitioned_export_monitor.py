"""Handwritten synthetic receipts; no saved programs, APIs or private worlds."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_public_output_grounding import Fixture as OriginalFixture, TASK
from public_output_grounding import PublicExportMonitor, PUBLIC_CONTRACT_ID
import partitioned_export_monitor as module
from partitioned_export_monitor import PartitionedExportMonitor, CONTRACT_ID, contract_identity


class Fixture(OriginalFixture):
    def __init__(self):
        super().__init__()
        self.monitor = PartitionedExportMonitor(deepcopy(TASK), execution_scope='synthetic_execution')

    def sources(self):
        self.login('spotify', 'synthetic-token')
        for kind in ('song', 'album'):
            self.send(f'spotify__show_{kind}_library', {'access_token':'synthetic-token','page_limit':20}, [])
        return self

    def partition(self, flag, *, ids=(1,), songs=None, index=0, limit=20, **kwargs):
        args = {'access_token':'synthetic-token','page_index':index,'page_limit':limit,'is_public':flag}
        rows = [{'playlist_id':i,'is_public':flag,'song_ids':list(songs if songs is not None else (100+i,))}for i in ids]
        return self.send('spotify__show_playlist_library', args, rows, **kwargs)

    def closed(self):
        evidence, _, _ = self.monitor.source_state()
        return all(evidence['source_complete'].values()) and not self.monitor.taints


class PartitionedExportTests(unittest.TestCase):
    def test_original_monitor_remains_unknown(self):
        f=Fixture().sources();f.monitor=PublicExportMonitor(deepcopy(TASK),execution_scope='original')
        f.login('spotify','synthetic-token');f.partition(False);f.partition(True,ids=(2,))
        self.assertIn('filtered_or_unsupported_source_page',f.monitor.taints)
    def test_two_complete_partitions_use_original_success_receipts(self):
        f=Fixture().sources();f.partition(False);f.partition(True,ids=(2,))
        self.assertTrue(f.closed());self.assertEqual(f.monitor.source_state()[1],{101,102})
        self.assertEqual(f.monitor.pages['playlist'],{})
    def test_one_partition_is_not_complete_scope(self):
        f=Fixture().sources();f.partition(False);self.assertFalse(f.closed())
    def test_terminal_and_every_page_are_required(self):
        for index in (None,2,1):
            f=Fixture().sources();f.partition(False,limit=1);f.partition(True,ids=())
            if index is not None:f.partition(False,ids=(),index=index,limit=1)
            self.assertEqual(f.closed(),index==1)
    def test_complete_empty_union_is_known(self):
        f=Fixture().sources();f.partition(False,ids=());f.partition(True,ids=())
        self.assertTrue(f.closed());self.assertEqual(f.monitor.source_state()[1],set())
    def test_cross_partition_duplicate_taints_even_if_complete_flags(self):
        f=Fixture().sources();f.partition(False);f.partition(True)
        self.assertFalse(f.closed());self.assertTrue(f.monitor.source_state()[0]['playlist_boolean_partitions_complete'])
    def test_wrong_returned_flag_and_integer_boolean_fail(self):
        for flag,value in ((False,True),(1,1)):
            f=Fixture().sources();f.send('spotify__show_playlist_library',
                {'access_token':'synthetic-token','is_public':flag,'page_limit':20},
                [{'playlist_id':1,'song_ids':[101],'is_public':value}])
            self.assertTrue(f.monitor.taints)
    def test_page_change_and_limit_disagreement_taint(self):
        f=Fixture().sources();f.partition(False);f.partition(False,ids=(3,));f.partition(True,ids=())
        self.assertFalse(f.closed());self.assertIn('changed_source_page',f.monitor.taints)
        g=Fixture().sources();g.partition(False);g.partition(False,ids=(3,),limit=19);g.partition(True,ids=())
        self.assertFalse(g.closed())
    def test_filtered_unfiltered_mix_is_explicitly_unsupported(self):
        f=Fixture().sources();f.partition(False);f.partition(True,ids=(2,))
        f.send('spotify__show_playlist_library',{'access_token':'synthetic-token','page_limit':20},[])
        self.assertFalse(f.closed());self.assertIn('mixed_partition_and_unfiltered_scope_unsupported',f.monitor.taints)
    def test_unbound_principal_cannot_close_partition(self):
        f=Fixture().sources();f.partition(False)
        f.send('spotify__show_playlist_library',{'access_token':'different-token','is_public':True},[])
        self.assertFalse(f.closed());self.assertIn('unverified_library_principal',f.monitor.taints)
    def test_raised_unsent_unknown_do_not_register_pages(self):
        for kwargs in ({'status':'raised'},{'sent':False},{'status':'unknown','unknown':True}):
            f=Fixture().sources();f.partition(False,**kwargs);f.partition(True,ids=())
            self.assertFalse(f.closed());self.assertEqual(f.monitor.playlist_partition_pages[False],{})
    def test_known_failed_read_preserves_other_valid_evidence(self):
        f=Fixture().sources();f.partition(False);f.partition(True,ids=())
        f.send('spotify__show_song',{'song_id':1},{},status='raised');self.assertTrue(f.closed())
    def test_source_mutation_and_delete_invalidate_current_scope(self):
        for api in ('spotify__add_song_to_library','spotify__delete_account'):
            f=Fixture().sources();f.partition(False);f.partition(True,ids=())
            f.send(api,{'access_token':'synthetic-token','song_id':1},{'message':'synthetic returned'})
            self.assertFalse(f.closed())
    def test_protocol_nonce_reuse_is_rejected(self):
        f=Fixture().sources();event,span=f.partition(False)
        event=deepcopy(event);span=deepcopy(span);event['span_id']='other';span['id']='other'
        with self.assertRaisesRegex(ValueError,'unique_typed_dispatch_nonce'):f.monitor.observe(event,span)
    def test_partition_contract_is_distinct_and_source_bound(self):
        identity=contract_identity();self.assertEqual(identity['contract_id'],CONTRACT_ID)
        self.assertNotEqual(CONTRACT_ID,PUBLIC_CONTRACT_ID)
        self.assertEqual(identity['monitor_source_sha256']['partitioned_export_monitor.py'],
                         hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
        with patch.object(module,'verify_public_export_sources',return_value=PUBLIC_CONTRACT_ID):
            self.assertEqual(module.verify_partitioned_export_sources('unused'),CONTRACT_ID)
            with patch.dict(module.PINNED_MONITOR_SHA256,{'public_output_grounding.py':'0'*64}):
                with self.assertRaisesRegex(ValueError,'dependency_changed'):module.verify_partitioned_export_sources('unused')

if __name__=='__main__':unittest.main()

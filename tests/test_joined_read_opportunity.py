"""P91 rejects future evidence and missing inner/outer correspondence."""
import copy
import json
import unittest

from test_public_read_opportunity import records
from test_joined_public_read_views import ALBUM, PLAYLIST, SONG
from public_read_opportunity import analyze as original_availability
from joined_read_opportunity import analyze


def packet(calls,source="v=call_api('spotify','show_song',song_id=1)\nprint(v)"):
    data=records(calls);events,spans,usage=data
    targets=[e for e in events if spans[e['span_id']]['action']['name']=='spotify__show_song']
    for e in list(targets):
        sid='parent_'+e['span_id']
        parent=dict(span_id=sid,call=e['call'],stage='model_tool',api_request_sent=False,effects_unknown=False)
        events.insert(events.index(e)+1,parent)
        spans[sid]=dict(action=dict(name='run_python',arguments=json.dumps(dict(code=source,span_ids=[]))),
            observation=dict(api_receipts=[dict(span_id=e['span_id'],api='spotify__show_song',api_request_sent=True)]))
    old=original_availability(*data,execution_scope='fixture')['targets']
    return data,old


def album():return ('spotify__show_album',{'album_id':9},copy.deepcopy(ALBUM),'returned')
def target(status='returned'):return ('spotify__show_song',{'song_id':1},copy.deepcopy(SONG),status)


class JoinedReadOpportunityTests(unittest.TestCase):
    def inspect(self,calls,**kwargs):
        data,old=packet(calls,**kwargs);return analyze(*data,old)

    def test_new_source_availability_is_measured_before_target_and_old_result_preserved(self):
        r=self.inspect([album(),target()]);t=r['targets'][0]
        self.assertEqual(t['original_authority_before'],'absent')
        self.assertEqual(t['joined_authority_before'],'partial')
        self.assertEqual(t['available_fields_before'],['song_id','title'])
        self.assertTrue(t['prior_fields_match_returned']);self.assertIsNone(r['measured_savings'])
        self.assertFalse(t['avoided_request_established'])

    def test_future_album_is_not_backdated(self):
        r=self.inspect([target(),album()]);self.assertEqual(r['targets'][0]['joined_authority_before'],'absent')

    def test_unknown_effect_retains_all_receipts_and_blocks_later_grants(self):
        r=self.inspect([album(),('spotify__like_song',{},None,'unknown'),album(),target()])
        self.assertEqual(r['counts']['sent_requests'],4)
        self.assertEqual(r['targets'][0]['joined_authority_before'],'unknown_state')

    def test_original_invalidation_rule_is_unchanged(self):
        r=self.inspect([album(),('api_docs__show_app_descriptions',{},[], 'returned'),target()])
        self.assertEqual(r['targets'][0]['joined_authority_before'],'absent')

    def test_syntax_is_reported_without_inferring_runtime_whole_value_demand(self):
        r=self.inspect([album(),target()],source="print(call_api('spotify','show_song',song_id=1))")
        p=r['target_programs'][0]
        self.assertEqual(p['target_syntax_sites'][0]['root_use'],'whole_value_argument')
        self.assertTrue(p['syntax_does_not_prove_field_demand'])
        self.assertFalse(p['persistent_namespace_inspected'])

    def test_missing_or_duplicate_outer_receipt_is_rejected(self):
        data,old=packet([album(),target()]);events,spans,usage=data
        parent=next(s for s in spans if s.startswith('parent_'))
        row=spans[parent]['observation']['api_receipts'][0]
        spans[parent]['observation']['api_receipts'].append(copy.deepcopy(row))
        with self.assertRaises(ValueError):analyze(*data,old)
        spans[parent]['observation']['api_receipts']=[]
        with self.assertRaises(ValueError):analyze(*data,old)

    def test_known_exception_cannot_confirm_available_fields(self):
        r=self.inspect([album(),target('raised')]);t=r['targets'][0]
        self.assertEqual(t['joined_authority_before'],'partial')
        self.assertFalse(t['prior_fields_match_returned'])
        self.assertEqual(r['counts']['receipt_raised'],1)

    def test_mislabeled_outer_api_receipt_is_rejected(self):
        data,old=packet([album(),target()]);events,spans,usage=data
        parent=next(s for s in spans if s.startswith('parent_'))
        spans[parent]['observation']['api_receipts'][0]['api']='spotify__show_album'
        with self.assertRaises(ValueError):analyze(*data,old)


if __name__=='__main__':unittest.main()

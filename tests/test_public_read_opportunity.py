"""Boundary checks for chronological, read-only availability classification."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from field_read_contract import FIELDS, SOURCE, TARGET
from public_read_opportunity import analyze

SONG = dict(song_id=1,title='synthetic',album_id=None,duration=200,
            artists=[{'id':2,'name':'fixture'}],genre='fixture',like_count=0)
LIBRARY = [{**{k:copy.deepcopy(SONG[k]) for k in FIELDS},'added_at':'fixture'}]


def records(calls):
    events=[];spans={};usage=[]
    for i,(name,args,value,status) in enumerate(calls,1):
        sid=f's{i}';call=f'call_{i:03d}';usage.append({'id':call})
        event=dict(span_id=sid,call=call,stage='python_api',api_request_sent=True,
            effects_unknown=status=='unknown',api_execution=dict(status=status,
                bridge_request_sent=True,automatic_retries=0))
        obs=({'observation':json.dumps(value)} if status=='returned'
             else {'api_error':'synthetic failure'})
        events.append(event);spans[sid]=dict(action=dict(name=name,arguments=json.dumps(args)),
                                           observation=obs)
    return events,spans,usage


def source(value=LIBRARY):return (SOURCE,{'access_token':'synthetic-token'},copy.deepcopy(value),'returned')
def target(value=SONG,status='returned'):return (TARGET,{'song_id':1},copy.deepcopy(value),status)


class PublicReadOpportunityTests(unittest.TestCase):
    def inspect(self,calls):
        return analyze(*records(calls),execution_scope='synthetic-closed-cell')

    def test_partial_then_complete_availability_includes_source_cost_and_exact_baseline(self):
        r=self.inspect([source(),target(),target()])
        self.assertEqual([t['authority_before'] for t in r['targets']],['partial','complete'])
        self.assertTrue(all(t['prior_value_matches_returned'] for t in r['targets']))
        self.assertEqual(r['counts']['sent_requests'],3)
        self.assertIsNone(r['measured_savings'])
        self.assertFalse(any(t['avoided_request_established'] for t in r['targets']))

    def test_future_library_does_not_create_authority_for_an_earlier_request(self):
        r=self.inspect([target(),source(),target()])
        self.assertEqual([t['authority_before'] for t in r['targets']],['absent','complete'])
        self.assertEqual(r['counts'].get('before_partial',0),0)

    def test_even_other_read_named_operations_conservatively_invalidate_the_cache(self):
        other=('api_docs__show_app_descriptions',{},[], 'returned')
        r=self.inspect([source(),other,target()])
        self.assertEqual(r['targets'][0]['authority_before'],'absent')
        self.assertEqual(r['counts']['conservative_invalidations'],1)

    def test_changed_target_value_is_a_contradiction_and_blocks_later_conflicting_reuse(self):
        changed={**SONG,'title':'different'}
        r=self.inspect([source(),target(changed),target(changed)])
        self.assertEqual(r['targets'][0]['authority_before'],'partial')
        self.assertFalse(r['targets'][0]['prior_value_matches_returned'])
        self.assertEqual(r['targets'][1]['authority_before'],'absent')
        self.assertEqual(r['counts']['prior_value_not_confirmed'],1)

    def test_unknown_effect_preserves_all_counts_and_never_reestablishes_authority(self):
        unknown=('spotify__like_song',{'song_id':1,'access_token':'synthetic'},None,'unknown')
        r=self.inspect([source(),unknown,source(),target()])
        self.assertEqual(r['counts']['sent_requests'],4)
        self.assertTrue(r['final_unknown_state'])
        self.assertEqual(r['targets'][0]['authority_before'],'unknown_state')
        self.assertEqual(r['counts']['receipt_unknown'],1)

    def test_known_exception_does_not_confirm_an_available_partial_value(self):
        r=self.inspect([source(),target(None,'raised')])
        t=r['targets'][0]
        self.assertEqual(t['authority_before'],'partial')
        self.assertFalse(t['response_supported'])
        self.assertFalse(t['prior_value_matches_returned'])
        self.assertEqual(r['counts']['receipt_raised'],1)

    def test_missing_typed_receipt_and_nonchronological_records_are_rejected(self):
        events,spans,usage=records([source(),target()])
        with self.assertRaises(ValueError):
            analyze(list(reversed(events)),spans,usage,execution_scope='fixture')
        del events[0]['api_execution']
        with self.assertRaises(ValueError):
            analyze(events,spans,usage,execution_scope='fixture')

    def test_partial_value_type_mismatch_is_not_accepted_as_numeric_equality(self):
        changed={**SONG,'duration':True}
        library=[{**LIBRARY[0],'duration':1}]
        r=self.inspect([source(library),target(changed)])
        self.assertFalse(r['targets'][0]['response_supported'])
        self.assertFalse(r['targets'][0]['prior_value_matches_returned'])

    def test_invalid_target_identity_is_retained_without_contract_authority(self):
        r=self.inspect([source(),(TARGET,{'song_id':True},SONG,'returned')])
        self.assertEqual(r['counts']['sent_requests'],2)
        self.assertEqual(r['targets'][0]['authority_before'],'absent')
        self.assertFalse(r['targets'][0]['response_supported'])


if __name__=='__main__':unittest.main()

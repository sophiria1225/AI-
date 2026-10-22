import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from structured_reuse_probe import RecordIndex
from analyze_structured_reuse import probe


class StructuredReuseProbeTests(unittest.TestCase):
    def test_cross_api_subset_is_not_full_response_equivalence(self):
        i=RecordIndex();i.add('a__list',{},[{'object_id':1,'name':'one'}])
        r=i.assess('a__show',{'object_id':1},{'object_id':1,'name':'one','detail':'new'})
        self.assertEqual(r['matching_nonidentity_fields_from_different_api'],1)
        self.assertEqual(r['missing_current_fields'],1)
        self.assertFalse(r['full_current_object_covered'])
        self.assertFalse(r['exact_previous_request'])

    def test_no_current_response_is_inserted_by_assessment(self):
        i=RecordIndex();args={'object_id':1};value={'object_id':1,'name':'one'}
        for _ in range(2):self.assertEqual(i.assess('a__show',args,value)['candidate_records'],0)

    def test_conflicts_are_not_resolved_using_current_reply(self):
        i=RecordIndex()
        for name in ('old','new'):i.add('a__list',{},[{'object_id':1,'name':name}])
        r=i.assess('a__show',{'object_id':1},{'object_id':1,'name':'new'})
        self.assertEqual(r['conflicting_prior_fields'],1)
        self.assertEqual(r['matching_current_fields'],1)
        self.assertFalse(r['full_current_object_covered'])

    def test_application_authentication_and_typed_ids_partition_candidates(self):
        i=RecordIndex();i.add('a__list',{'access_token':'private-one'},[{'object_id':1,'v':3}])
        for name,args,value in [('b__show',{'object_id':1,'access_token':'private-one'},{'object_id':1}),
            ('a__show',{'object_id':1,'access_token':'private-two'},{'object_id':1}),
            ('a__show',{'object_id':'1','access_token':'private-one'},{'object_id':'1'})]:
            r=i.assess(name,args,value);self.assertEqual(r['candidate_records'],0)
            self.assertNotIn('private',json.dumps(r))

    def test_foreign_key_conflict_is_kept_as_evidence_not_a_match(self):
        i=RecordIndex();i.add('a__songs',{},[{'song_id':1,'album_id':2,'title':'song'}])
        r=i.assess('a__album',{'album_id':2},{'album_id':2,'title':'album'})
        self.assertEqual(r['candidate_records'],1)
        self.assertEqual(r['different_current_fields'],1)
        self.assertFalse(r['full_current_object_covered'])

    def test_mutation_invalidation_and_changed_exact_reply(self):
        i=RecordIndex();args={'object_id':1};i.add('a__show',args,{'object_id':1,'v':3})
        r=i.assess('a__show',args,{'object_id':1,'v':4})
        self.assertTrue(r['exact_previous_request']);self.assertFalse(r['exact_reply_content_equal'])
        i.invalidate();r=i.assess('a__show',args,{'object_id':1,'v':4})
        self.assertFalse(r['exact_previous_request']);self.assertEqual(r['candidate_records'],0)

    def test_multiple_identity_keys_and_bounded_scans_are_disclosed(self):
        i=RecordIndex(max_nodes=1);i.add('a__list',{},[{'object_id':1}])
        self.assertEqual(i.bounded_scans,1)
        r=i.assess('a__show',{'object_id':1,'parent_id':2},{'object_id':1,'parent_id':2})
        self.assertFalse(r['eligible_identity_shape'])

    def test_saved_record_is_immutable_and_auth_mismatch_remains_separate(self):
        i=RecordIndex();value={'object_id':1,'items':[2,3]}
        i.add('a__list',{'access_token':'private-one'},value)
        value['items'].append(4)
        r=i.assess('a__show',{'object_id':1,'access_token':'private-one'},
                   {'object_id':1,'items':[2,3]})
        self.assertTrue(r['full_current_object_covered'])
        r=i.assess('a__show',{'object_id':1},{'object_id':1,'items':[2,3]})
        self.assertEqual(r['candidate_records'],0)
        self.assertEqual(r['other_auth_candidate_records'],1)

    def test_dispatched_write_invalidates_even_on_error_but_unsent_does_not(self):
        for sent in (False,True):
            i=RecordIndex();i.add('a__read',{'object_id':1},{'object_id':1,'value':2})
            spans={'w':{'action':{'name':'a__write','arguments':'{}'},'observation':{'api_error':'failed'}}}
            probe([{'span_id':'w','api_request_sent':sent}],spans,{'a__write':'POST'},i,measure=True)
            r=i.assess('a__read',{'object_id':1},{'object_id':1,'value':2})
            self.assertEqual(r['exact_previous_request'],not sent)

    def test_error_response_not_cached_and_order_precedes_current_insert(self):
        i=RecordIndex();events=[];spans={}
        for n,obs in enumerate(({'api_error':'error'},{'observation':'{"object_id":1,"value":2}'},
                                {'observation':{'object_id':1,'value':2}})):
            sid=str(n);events.append({'span_id':sid,'api_request_sent':True})
            spans[sid]={'action':{'name':'a__read','arguments':'{"object_id":1}'},'observation':obs}
        counts,rows=probe(events,spans,{'a__read':'GET'},i,measure=True)
        self.assertEqual(counts['get_error_responses'],1)
        self.assertEqual([r['exact_previous_request'] for r in rows],[False,True])


if __name__=='__main__':unittest.main()

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recorded_request_repetition import analyze

READ='spotify__show_song_library'


def records(calls):
    events=[];spans={};usage=[]
    for i,(name,args,value,status) in enumerate(calls,1):
        sid=f's{i}';cid=f'call_{i:03d}';usage.append({'id':cid})
        events.append(dict(span_id=sid,call=cid,stage='python_api',api_request_sent=True,
            effects_unknown=status=='unknown',api_execution=dict(status=status,bridge_request_sent=True,automatic_retries=0)))
        observation={'observation':json.dumps(value)} if status=='returned' else {'api_error':'fixture'}
        spans[sid]=dict(action=dict(name=name,arguments=json.dumps(args)),observation=observation)
    return events,spans,usage


def read(value=None,token='fixture',status='returned'):
    return READ,{'access_token':token},[1,2] if value is None else value,status


class RecordedRequestRepetitionTests(unittest.TestCase):
    def inspect(self,calls,**kwargs):return analyze(*records(calls),**kwargs)

    def test_prior_availability_does_not_use_the_future_reply(self):
        r=self.inspect([read(),read()]);a,b=r['requests']
        self.assertEqual(a['prior_status'],'absent')
        self.assertEqual(b['prior_status'],'prior_success')
        self.assertTrue(b['repeated_value_equal'])
        self.assertEqual(b['prior_success_request_ordinal'],1)
        self.assertIsNone(r['measured_API_savings'])
        self.assertFalse(b['online_cache_permission'])

    def test_same_api_name_with_different_arguments_is_not_a_repeat(self):
        r=self.inspect([read(token='first'),read(token='second')])
        self.assertIsNone(r['requests'][1]['previous_request_ordinal'])
        self.assertEqual(r['requests'][1]['prior_status'],'absent')

    def test_argument_key_order_is_ignored_but_list_order_and_types_are_not(self):
        calls=[(READ,a,[], 'returned') for a in [dict(x=1,y=[1,2]),dict(y=[1,2],x=1),dict(x=True,y=[1,2]),dict(x=1,y=[2,1]),dict(x=1.0,y=[1,2])]]
        rows=self.inspect(calls)['requests']
        self.assertEqual(rows[1]['previous_request_ordinal'],1)
        self.assertTrue(all(r['previous_request_ordinal'] is None for r in rows[2:]))

    def test_login_is_counted_and_invalidates_even_if_its_return_repeats(self):
        login=('spotify__login',{'username':'fixture'},'fixture-token','returned')
        r=self.inspect([read(),login,read(),login]);rows=r['requests']
        self.assertEqual(rows[2]['prior_status'],'absent')
        self.assertEqual(rows[2]['intervening_barriers'],1)
        self.assertTrue(rows[3]['repeated_value_equal'])
        self.assertEqual(rows[3]['prior_status'],'outside_read_scope')
        self.assertEqual(r['counts']['sent_requests'],4)

    def test_a_changed_reply_blocks_later_claims_until_a_barrier(self):
        barrier=('api_docs__show_api_doc',{},'fixture','returned')
        rows=self.inspect([read([1]),read([2]),read([2]),barrier,read([2]),read([2])])['requests']
        self.assertEqual(rows[1]['prior_status'],'prior_success')
        self.assertFalse(rows[1]['current_matches_prior_read_value'])
        self.assertEqual(rows[2]['prior_status'],'conflicting_or_failed_read')
        self.assertEqual(rows[4]['prior_status'],'absent')
        self.assertEqual(rows[5]['prior_status'],'prior_success')

    def test_known_exception_retains_historical_request_but_blocks_read_reuse(self):
        r=self.inspect([read(),read(status='raised'),read()]);rows=r['requests']
        self.assertEqual(rows[1]['prior_status'],'prior_success')
        self.assertIsNone(rows[1]['repeated_value_equal'])
        self.assertFalse(rows[1]['current_matches_prior_read_value'])
        self.assertEqual(rows[2]['prior_status'],'conflicting_or_failed_read')
        self.assertEqual(r['counts']['receipt_raised'],1)

    def test_unknown_result_does_not_use_future_success_to_reset_state(self):
        r=self.inspect([read(),read(status='unknown'),read(),read()])
        self.assertEqual(r['requests'][1]['prior_status'],'prior_success')
        self.assertEqual([x['prior_status'] for x in r['requests'][2:]],['unknown_state','unknown_state'])
        self.assertTrue(r['final_unknown_state'])

    def test_nonsent_unknown_event_is_retained_as_a_barrier(self):
        e,s,u=records([read(),read(),read()])
        e[1].update(api_request_sent=False,effects_unknown=True,stage='python_execute')
        r=analyze(e,s,u)
        self.assertEqual(r['counts']['sent_requests'],2)
        self.assertEqual(r['counts']['nonsent_unknown_effect_barriers'],1)
        self.assertEqual(r['requests'][-1]['prior_status'],'unknown_state')
        self.assertFalse(r['model_boundaries'][1]['all_sent_requests_historical_repeats'])

    def test_payload_format_equality_is_distinct_from_decoded_value_equality(self):
        e,s,u=records([read({'a':1,'b':2}),read({'b':2,'a':1})])
        r=analyze(e,s,u)['requests'][1]
        self.assertFalse(r['repeated_payload_equal'])
        self.assertTrue(r['repeated_value_equal'])

    def test_value_and_capacity_bounds_do_not_delete_observed_requests(self):
        r=self.inspect([read('too long'),read('too long')],max_value_bytes=3)
        self.assertEqual(r['counts']['sent_requests'],2)
        self.assertEqual(r['counts']['cache_bounds_rejected'],2)
        self.assertEqual(r['requests'][1]['prior_status'],'absent')
        r=self.inspect([read(token='a'),read(token='b'),read(token='b')],max_cache_entries=1)
        self.assertEqual(r['requests'][-1]['prior_status'],'absent')

    def test_same_generation_repetitions_are_not_independent_model_boundaries(self):
        e,s,u=records([read(),read()]);e[1]['call']=e[0]['call'];u=u[:1]
        r=analyze(e,s,u)
        self.assertEqual(r['counts']['repeated_requests'],1)
        self.assertEqual(r['counts'].get('repeated_across_model_boundaries',0),0)
        self.assertFalse(r['model_boundaries'][0]['all_sent_requests_historical_repeats'])
        self.assertFalse(r['model_boundaries'][0]['removable_generation_established'])

    def test_missing_records_reordered_events_and_automatic_retries_rejected(self):
        e,s,u=records([read(),read()])
        variants=[]
        x=copy.deepcopy(e);x[0]['api_execution']['automatic_retries']=1;variants.append((x,s,u))
        variants.append((list(reversed(e)),s,u));variants.append((e,{k:v for k,v in s.items() if k!='s1'},u))
        for args in variants:
            with self.subTest(args=args),self.assertRaises(ValueError):analyze(*args)


if __name__=='__main__':unittest.main()

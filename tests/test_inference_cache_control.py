import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from inference_cache_control import (SCHEDULE, cache_measurement, request_for,
                                     require_idle, validate_erasure)


class CacheControlTests(unittest.TestCase):
    def response(self,cached):
        return {'status':'ok','input_tokens':100,'output_tokens':10,'cached_input_tokens':cached,
                'timings':{'cache_n':cached,'prompt_n':100-cached,'predicted_n':10,
                           'prompt_ms':1000,'predicted_ms':2000}}

    def test_busy_missing_or_additional_slots_are_refused(self):
        require_idle([{'id':0,'is_processing':False}])
        for slots in ([],[{'id':0}],[{'id':0,'is_processing':True}],
                      [{'id':1,'is_processing':False}],[{'id':0,'is_processing':False}]*2):
            with self.assertRaises(ValueError):require_idle(slots)

    def test_erasure_must_be_acknowledged_for_exact_slot(self):
        self.assertEqual(validate_erasure({'id_slot':0,'n_erased':123}),123)
        for value in ({},{'id_slot':1,'n_erased':0},{'id_slot':0,'n_erased':True}):
            with self.assertRaises(ValueError):validate_erasure(value)

    def test_only_generation_cap_changes_in_request(self):
        original={'seed':50,'cache_prompt':True,'stream':False,'max_tokens':4096,'messages':[{'content':'fixture'}]}
        plan={'schedule':list(SCHEDULE),'max_calls':6,'max_output_tokens':256,'seed':50}
        updated=request_for(original,plan)
        self.assertEqual(updated,{**original,'max_tokens':256})
        updated['messages'][0]['content']='changed'
        self.assertEqual(original['messages'][0]['content'],'fixture')
        with self.assertRaises(ValueError):request_for(original,{**plan,'schedule':list(SCHEDULE)[::-1]})

    def test_configuration_does_not_substitute_for_measured_cache(self):
        self.assertTrue(cache_measurement('cold_1',self.response(0),100)['state_confirmed'])
        self.assertFalse(cache_measurement('cold_1',self.response(99),100)['state_confirmed'])
        self.assertTrue(cache_measurement('warm_1',self.response(99),100)['state_confirmed'])
        self.assertFalse(cache_measurement('warm_1',self.response(20),100)['state_confirmed'])

    def test_unknown_usage_and_inconsistent_timing_are_rejected(self):
        with self.assertRaises(ValueError):cache_measurement('cold_1',{'status':'error'},100)
        r=self.response(0);r['timings']['prompt_n']=99
        with self.assertRaises(ValueError):cache_measurement('cold_1',r,100)


if __name__=='__main__':unittest.main()

import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_projected_misses import classify, model_payload
from field_read_contract import CONTRACT_ID, SOURCE, TARGET
from projected_read_runtime import ProjectedReadRuntime


class ProjectedMissTests(unittest.TestCase):
    def setUp(self):
        self.runtime=ProjectedReadRuntime('contract',execution_scope='fixture',verified_contract=CONTRACT_ID)
        self.value={'song_id':17,'title':'fixture','artists':[]}

    def source(self):
        self.runtime.observed_sent(SOURCE,{'access_token':'fixture'},success=True,value=[self.value])

    def reason(self, fields=('title','artists'), ever=frozenset()):
        return classify(self.runtime,TARGET,{'song_id':17},fields,ever)

    def test_current_response_not_available_before_it_is_observed(self):
        self.assertEqual(self.reason(),'object_not_previously_observed')
        self.source()
        self.assertEqual(self.reason(),'hit_cross_api')

    def test_unknown_sent_operation_expires_prior_information(self):
        self.source()
        self.runtime.observed_sent('unknown__read',{},success=True,value={})
        self.assertEqual(self.reason(ever={17}),'previous_value_no_longer_available')

    def test_missing_field_is_not_a_successful_hit(self):
        self.source()
        self.assertEqual(self.reason(('duration',)),'required_fields_not_covered')

    def test_unsupported_field_is_distinguished(self):
        self.source()
        self.assertEqual(self.reason(('private_field',)),'fields_outside_contract')

    def test_conflicting_values_are_not_arbitrarily_selected(self):
        self.source()
        self.runtime.observed_sent(SOURCE,{'access_token':'fixture'},success=True,
                                   value=[{**self.value,'title':'different'}])
        self.assertEqual(self.reason(),'conflicting_versions')

    def test_exact_response_can_support_non_contract_fields(self):
        self.runtime.observed_sent(TARGET,{'song_id':17},success=True,
                                   value={**self.value,'additional':'present'})
        self.assertEqual(self.reason(('additional',)),'hit_exact')

    def test_unusable_identity_is_not_treated_as_a_new_object(self):
        self.assertEqual(classify(self.runtime,TARGET,{'song_id':'17'},['title'],set()),
                         'unsupported_target_or_arguments')

    def test_transport_ids_do_not_create_generation_differences(self):
        a={'role':'assistant','tool_calls':[{'id':'a','type':'function','function':{'name':'read','arguments':'{}'}}]}
        b={'role':'assistant','tool_calls':[{'id':'b','type':'function','function':{'name':'read','arguments':'{}'}}]}
        self.assertEqual(model_payload(a),model_payload(b))
        self.assertEqual(a['tool_calls'][0]['id'],'a')
        b['tool_calls'][0]['function']['arguments']='{"different":true}'
        self.assertNotEqual(model_payload(a),model_payload(b))


if __name__=='__main__':unittest.main()

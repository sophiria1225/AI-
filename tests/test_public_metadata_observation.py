import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from context_preservation import compact
from public_metadata_observation import literal_value,match_public_functions,describe_tool_observation,exposure_summary

FUNCTIONS={n:dict(name=n,description='public schema',parameters=dict(type='object',properties={}))
           for n in ('example__read','example__write')}


def fixture(stdout=None,**obs_changes):
    if stdout is None:stdout=json.dumps(FUNCTIONS)+'\n'
    obs=dict(status='ok',stdout=stdout,error=None,stdout_truncated=False,
             unknown_effects=False,declared_complete=False,api_receipts=[])
    obs.update(obs_changes)
    action=dict(name='run_python',arguments=json.dumps(dict(code='print(api_schemas)',span_ids=[])))
    spans={'s1':dict(id='s1',action=action,observation=obs)}
    message=dict(role='tool',tool_call_id='tool1',content=compact(dict(span_id='s1',observation=obs)))
    return message,spans,FUNCTIONS,{'s1':set(FUNCTIONS)}


class PublicMetadataObservationTests(unittest.TestCase):
    def test_full_mapping_json_and_python_literals_match_complete_schemas(self):
        for text in (json.dumps(FUNCTIONS),str(FUNCTIONS)):
            value,_=literal_value(text)
            self.assertEqual(match_public_functions(value,FUNCTIONS)['shape'],'mapping_of_functions')

    def test_single_schema_and_ordered_duplicate_list_recognized(self):
        value=FUNCTIONS['example__read']
        self.assertEqual(match_public_functions(value,FUNCTIONS)['shape'],'single_function')
        self.assertEqual(match_public_functions([value,value],FUNCTIONS)['names'],['example__read']*2)

    def test_mixed_task_values_or_partial_schema_are_not_complete_metadata(self):
        for value in ({**FUNCTIONS,'task_data':{'name':'private'}},
                      [FUNCTIONS['example__read'],{'value':1}],
                      {'example__read':{'name':'example__read'}}):
            self.assertIsNone(match_public_functions(value,FUNCTIONS))

    def test_even_changed_description_rejects_equality(self):
        value=copy.deepcopy(FUNCTIONS);value['example__read']['description']='different'
        self.assertIsNone(match_public_functions(value,FUNCTIONS))

    def test_nonliteral_code_prefix_and_duplicate_keys_never_executed(self):
        for text in ("__import__('os').system('false')",'prefix '+json.dumps(FUNCTIONS),'{"x":1,"x":2}'):
            with self.assertRaises((ValueError,SyntaxError)):
                literal_value(text)

    def test_exact_archived_wrapper_and_schema_name_use_are_not_provenance(self):
        raw=fixture();old=copy.deepcopy(raw);r=describe_tool_observation(*raw)
        self.assertEqual(raw,old)
        self.assertEqual(r['archive_correspondence'],'exact')
        self.assertTrue(r['whole_public_metadata_match'])
        self.assertTrue(r['syntax']['api_schemas_name_loaded'])
        self.assertFalse(r['syntax']['actual_dataflow_proven'])
        self.assertFalse(r['safe_to_omit'])
        self.assertFalse(r['provenance_of_printed_value_proven'])

    def test_error_truncation_unknown_effect_or_hidden_name_protects_observation(self):
        for kwargs in ({'status':'execution_error'},{'error':'error'},{'stdout_truncated':True},
                       {'unknown_effects':True},{'declared_complete':True}):
            r=describe_tool_observation(*fixture(**kwargs))
            self.assertTrue(r['whole_public_metadata_match'])
            self.assertFalse(r['normal_complete_metadata_match'])
        raw=fixture();raw[3]['s1']={'example__read'}
        r=describe_tool_observation(*raw)
        self.assertTrue(r['whole_public_metadata_match'])
        self.assertFalse(r['all_names_exposed_by_program_end'])

    def test_wrong_archive_payload_cannot_lend_metadata_identity(self):
        raw=fixture();raw[1]['s1']['observation']['stdout']='changed'
        r=describe_tool_observation(*raw)
        self.assertEqual(r['archive_correspondence'],'observation_mismatch')
        self.assertFalse(r['whole_public_metadata_match'])

    def test_paged_wrapper_is_retained_as_unrecognized(self):
        raw=fixture();raw[0]['content']=compact(dict(span_id='s1',first_page={'content':'partial'}))
        r=describe_tool_observation(*raw)
        self.assertEqual(r['archive_correspondence'],'unrecognized_or_paged')
        self.assertFalse(r['whole_public_metadata_match'])

    def test_exposure_summary_does_not_relabel_repetition_as_savings(self):
        r=describe_tool_observation(*fixture());r.update(exposures=3)
        s=exposure_summary([r])
        self.assertEqual(s['matched_whole_tool_exposure_characters'],3*r['tool_content_characters'])
        self.assertTrue(s['observed_exposure_is_not_removable_work'])
        self.assertTrue(s['character_counts_are_not_token_counts'])
        public=json.dumps(r)
        self.assertNotIn('public schema',public)


if __name__=='__main__':unittest.main()

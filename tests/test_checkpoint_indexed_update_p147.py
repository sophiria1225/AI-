"""Explicit-index representation checks; synthetic states only, no model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import checkpoint_indexed_update_p147 as indexed
from checkpoint_state_update_p144 import apply_update_patch,parse_update_patch
from test_checkpoint_update_schema_p145 import request


def old_state():
    return {'completed':['A','B','C'],'usable_state':['known'],'remaining':['pending'],'uncertainties':[]}


def keep_all(old):
    return {field:{'by_index':{str(i):{'action':'keep'} for i in range(len(old[field]))},'add':[]}
            for field in indexed.FIELDS}


def message(value):
    return {'role':'assistant','content':json.dumps(value,ensure_ascii=False,separators=(',',':'))}


class IndexedSchemaTests(unittest.TestCase):
    def test_schema_requires_every_old_key_once_and_only_supported_keywords(self):
        old={f:['state text']*n for f,n in zip(indexed.FIELDS,(0,1,3,32))}
        schema=indexed.schema_for(old)
        self.assertEqual(schema['required'],list(indexed.FIELDS));self.assertFalse(schema['additionalProperties'])
        for field,items in old.items():
            fs=schema['properties'][field]
            self.assertEqual(fs['required'],['by_index','add']);self.assertFalse(fs['additionalProperties'])
            by=fs['properties']['by_index']
            self.assertEqual(by['required'],[str(i) for i in range(len(items))])
            self.assertEqual(set(by['properties']),set(by['required']));self.assertFalse(by['additionalProperties'])
            for action in by['properties'].values():
                self.assertEqual(len(action['anyOf']),3)
                self.assertEqual([a['properties']['action']['const'] for a in action['anyOf']],['keep','delete','update'])
                self.assertEqual([a['required'] for a in action['anyOf']],[['action'],['action'],['action','text']])
                self.assertTrue(all(a['additionalProperties'] is False for a in action['anyOf']))
        serialized=json.dumps(schema)
        self.assertNotIn('state text',serialized)
        for unsupported in ('uniqueItems','if','then','else','patternProperties','dependentSchemas'):
            self.assertNotIn('"'+unsupported+'"',serialized)

    def test_payload_preserves_user_packet_sampling_seed_and_cap(self):
        old=old_state();saved=request(old);before=deepcopy((saved,old))
        result=indexed.payload_for(saved,old)
        self.assertEqual(result['messages'][1],saved['messages'][1])
        self.assertEqual(result['messages'][0],{'role':'system','content':indexed.INDEXED_UPDATE_PROMPT})
        self.assertEqual(result['reasoning_budget_tokens'],2048);self.assertEqual(result['max_tokens'],4096)
        self.assertEqual(result['response_format']['json_schema']['name'],indexed.SCHEMA_NAME)
        self.assertEqual({k:v for k,v in result.items() if k not in ('messages','reasoning_budget_tokens','response_format')},
                         {k:v for k,v in saved.items() if k not in ('messages','reasoning_budget_tokens')})
        self.assertEqual((saved,old),before)

    def test_wrong_original_prompt_or_mismatched_old_state_is_rejected(self):
        old=old_state();saved=request(old)
        bad=deepcopy(saved);bad['messages'][0]['content']='ordinary summary'
        for req,prior in [(bad,old),(saved,{f:[] for f in indexed.FIELDS})]:
            with self.assertRaises(ValueError):indexed.payload_for(req,prior)


class StrictConverterTests(unittest.TestCase):
    def test_all_four_actions_match_frozen_patch_without_mutating_inputs(self):
        old=old_state();value=keep_all(old)
        value['completed']['by_index']={'2':{'action':'delete'},'0':{'action':'keep'},
                                       '1':{'action':'update','text':'B revised'}}
        value['completed']['add']=['D','E'];before=deepcopy((old,value))
        expected={f:dict(keep=list(range(len(old[f]))),update=[],delete=[],add=[]) for f in indexed.FIELDS}
        expected['completed']=dict(keep=[0],update=[{'index':1,'text':'B revised'}],delete=[2],add=['D','E'])
        actual=indexed.to_legacy_patch(message(value),'stop',old)
        self.assertEqual(actual,expected)
        self.assertEqual(indexed.parse_and_apply(message(value),'stop',old),apply_update_patch(old,expected))
        self.assertEqual((old,value),before)

    def test_all_keep_and_empty_fields_preserve_exact_text(self):
        old=old_state();old['completed']=['  日本語\n"quoted" \\ unchanged  ']
        new,counts=indexed.parse_and_apply(message(keep_all(old)),'stop',old)
        self.assertEqual(new,old);self.assertEqual(counts['changed_old_items'],0)
        self.assertEqual(counts['added_items'],0)

    def test_numeric_index_order_is_independent_of_json_key_order(self):
        old={f:[] for f in indexed.FIELDS};old['completed']=[str(i) for i in range(12)]
        value=keep_all(old);value['completed']['by_index']={str(i):{'action':'update','text':'v'+str(i)} for i in reversed(range(12))}
        converted=indexed.to_legacy_patch(message(value),'stop',old)
        self.assertEqual([x['index'] for x in converted['completed']['update']],list(range(12)))
        result,_=indexed.parse_and_apply(message(value),'stop',old)
        self.assertEqual(result['completed'],['v'+str(i) for i in range(12)])

    def test_missing_extra_noncanonical_or_cross_field_indices_reject_entire_output(self):
        old=old_state();variants=[]
        value=keep_all(old);del value['completed']['by_index']['1'];variants.append(value)
        value=keep_all(old);value['completed']['by_index']['3']={'action':'keep'};variants.append(value)
        value=keep_all(old);value['completed']['by_index']['00']=value['completed']['by_index'].pop('0');variants.append(value)
        value=keep_all(old);value['uncertainties']['by_index']['0']={'action':'keep'};variants.append(value)
        value=keep_all(old);value['completed']['by_index']=[];variants.append(value)
        for value in variants:
            with self.subTest(value=value),self.assertRaises(ValueError):
                indexed.to_legacy_patch(message(value),'stop',old)

    def test_duplicate_json_index_action_and_outer_keys_reject_before_conversion(self):
        old=old_state();content=message(keep_all(old))['content']
        variants=[content.replace('"0":{"action":"keep"}',
            '"0":{"action":"keep"},"0":{"action":"delete"}',1),
            content.replace('"action":"keep"','"action":"keep","action":"delete"',1),
            content[:-1]+',"completed":{"by_index":{},"add":[]}}',
            content.replace('"0":{"action":"keep"}',
                '"0":{"action":"keep"},"\\u0030":{"action":"delete"}',1)]
        for text in variants:
            with self.subTest(text=text),self.assertRaises(ValueError):
                indexed.to_legacy_patch({'role':'assistant','content':text},'stop',old)

    def test_extra_fields_invalid_actions_and_wrong_text_do_not_get_repaired(self):
        old=old_state();variants=[]
        for entry in ({'action':'keep','text':'extra'},{'action':'delete','text':'extra'},
                      {'action':'update'},{'action':'update','text':''},
                      {'action':'update','text':True},{'action':'update','text':'x'*2049},
                      {'action':['keep','delete']},{'action':'unknown'},['keep']):
            value=keep_all(old);value['completed']['by_index']['0']=entry;variants.append(value)
        value=keep_all(old);value['extra']={};variants.append(value)
        value=keep_all(old);value['completed']['keep']=[0];variants.append(value)
        value=keep_all(old);value['completed']['add']='new';variants.append(value)
        value=keep_all(old);value['completed']['add']=[''];variants.append(value)
        for value in variants:
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):
                indexed.to_legacy_patch(message(value),'stop',old)

    def test_frozen_parser_is_reapplied_and_its_failure_is_not_bypassed(self):
        old=old_state();source=message(keep_all(old))
        with patch.object(indexed,'parse_update_patch',wraps=parse_update_patch) as fixed:
            indexed.to_legacy_patch(source,'stop',old)
            fixed.assert_called_once()
            args=fixed.call_args.args
            self.assertEqual(args[1:],('stop',old))
            self.assertNotIn('by_index',args[0]['content'])
        with patch.object(indexed,'parse_update_patch',side_effect=ValueError('frozen limit')):
            with self.assertRaisesRegex(ValueError,'frozen limit'):
                indexed.to_legacy_patch(source,'stop',old)

    def test_raw_finish_tools_and_materialized_size_limits_stay_strict(self):
        old=old_state();valid=message(keep_all(old))
        for msg,finish in [(valid,'length'),({**valid,'tool_calls':[{}]},'stop'),
                ({'role':'user','content':valid['content']},'stop'),
                ({'role':'assistant','content':' '*8193},'stop')]:
            with self.subTest(msg=msg,finish=finish),self.assertRaises(ValueError):
                indexed.to_legacy_patch(msg,finish,old)
        old={f:[] for f in indexed.FIELDS};old['completed']=['x']*32
        value=keep_all(old);value['completed']['add']=['one too many']
        with self.assertRaises(ValueError):indexed.to_legacy_patch(message(value),'stop',old)
        old={f:[] for f in indexed.FIELDS};old['completed']=['x'*1900]*4
        value=keep_all(old);value['remaining']['add']=['y'*1000]
        self.assertLess(len(message(value)['content']),8192)
        with self.assertRaises(ValueError):indexed.to_legacy_patch(message(value),'stop',old)

    def test_nonstandard_json_constants_are_not_accepted(self):
        old=old_state();content=message(keep_all(old))['content'].replace('"add":[]','"add":[NaN]',1)
        with self.assertRaisesRegex(ValueError,'non_json_constant'):
            indexed.to_legacy_patch({'role':'assistant','content':content},'stop',old)


if __name__=='__main__':unittest.main()

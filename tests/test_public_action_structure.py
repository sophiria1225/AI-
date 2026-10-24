import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from public_action_structure import comparison, digest, inspect, strict_object, transport_ids


def response(code='print(1)', *, args=None, content=None, name='run_python'):
    if args is None: args=json.dumps({'code':code,'span_ids':[]})
    return dict(status='ok',done_reason='tool_calls',message=dict(content=content,
        tool_calls=[dict(id='generated_reference',function=dict(name=name,arguments=args))]))


class PublicActionStructureTests(unittest.TestCase):
    def test_public_hash_matches_the_existing_public_field_definition(self):
        r=response();expected=dict(content=None,functions=[r['message']['tool_calls'][0]['function']],done_reason='tool_calls')
        self.assertEqual(inspect(r)['public_output_sha256'],digest(expected))

    def test_JSON_spacing_and_key_order_are_removed_only_in_JSON_comparison(self):
        a=inspect(response(args='{"code":"print(1)","span_ids":[]}'))
        b=inspect(response(args='{ "span_ids": [], "code": "print(1)" }'))
        self.assertNotEqual(a['public_output_sha256'],b['public_output_sha256'])
        self.assertEqual(a['json_actions_sha256'],b['json_actions_sha256'])
        self.assertEqual(a['syntax_actions_sha256'],b['syntax_actions_sha256'])

    def test_AST_removes_locations_comments_and_formatting_not_literals(self):
        a=inspect(response('print(1)'));b=inspect(response('# comment\nprint( 1 )\n'));c=inspect(response('print(2)'))
        self.assertNotEqual(a['json_actions_sha256'],b['json_actions_sha256'])
        self.assertEqual(a['syntax_actions_sha256'],b['syntax_actions_sha256'])
        self.assertNotEqual(a['syntax_actions_sha256'],c['syntax_actions_sha256'])
        self.assertFalse(a['semantic_equivalence_established'])

    def test_variable_names_and_statement_order_remain(self):
        a=inspect(response('x=1\nprint(x)'));b=inspect(response('y=1\nprint(y)'))
        c=inspect(response('print(x)\nx=1'))
        self.assertNotEqual(a['syntax_actions_sha256'],b['syntax_actions_sha256'])
        self.assertNotEqual(a['syntax_actions_sha256'],c['syntax_actions_sha256'])

    def test_span_references_and_order_remain(self):
        a=inspect(response(args=json.dumps({'code':'pass','span_ids':['a','b']})))
        b=inspect(response(args=json.dumps({'code':'pass','span_ids':['b','a']})))
        self.assertNotEqual(a['syntax_actions_sha256'],b['syntax_actions_sha256'])

    def test_content_only_is_not_an_empty_valid_action(self):
        r=dict(status='ok',done_reason='stop',message=dict(content='done',tool_calls=[]));s=inspect(r)
        self.assertEqual(s['status'],'no_structured_tool_calls');self.assertEqual(s['tool_calls'],0)
        for key in ('tool_names_sha256','json_actions_sha256','syntax_actions_sha256'):self.assertIsNone(s[key])
        self.assertIsNotNone(s['public_output_sha256'])

    def test_unknown_response_is_not_zero_calls(self):
        s=inspect({'status':'error'});self.assertIsNone(s['tool_calls']);self.assertIsNone(s['public_output_sha256'])

    def test_duplicate_keys_and_nonfinite_arguments_are_not_normalized(self):
        for args in ('{"code":"pass","code":"print(1)","span_ids":[]}', '{"x":NaN}', '{"x":1e999}'):
            s=inspect(response(args=args));self.assertIsNone(s['json_actions_sha256'])
            self.assertIsNone(s['syntax_actions_sha256'])

    def test_missing_argument_and_unhashable_name_are_retained_as_invalid(self):
        for r in (response(args='{"code":"pass"}'),response(name=['not','a','name'])):
            s=inspect(r);self.assertIsNone(s['syntax_actions_sha256']);self.assertEqual(s['interface_shapes_valid'],0)

    def test_invalid_Python_does_not_change_valid_JSON_status(self):
        s=inspect(response('for x in:'));self.assertIsNotNone(s['json_actions_sha256'])
        self.assertIsNone(s['syntax_actions_sha256']);self.assertFalse(s['functions'][0]['Python_AST_valid'])

    def test_tool_order_and_read_span_default_syntax_are_not_rewritten(self):
        a=response(name='read_span',args='{"span_id":"a"}')
        b=response(name='read_span',args='{"span_id":"a","offset":0}')
        self.assertNotEqual(inspect(a)['syntax_actions_sha256'],inspect(b)['syntax_actions_sha256'])
        a['message']['tool_calls'].append(b['message']['tool_calls'][0])
        reversed_calls={**a,'message':{**a['message'],'tool_calls':list(reversed(a['message']['tool_calls']))}}
        self.assertNotEqual(inspect(a)['syntax_actions_sha256'],inspect(reversed_calls)['syntax_actions_sha256'])

    def test_dynamic_code_is_only_parsed_never_executed(self):
        s=inspect(response('exec("raise RuntimeError()")'))
        self.assertIn('dynamic_execution_or_namespace_access',s['functions'][0]['current_program_hazards'])
        self.assertEqual(s['actions_executed'],0)

    def test_transport_mentions_are_counted_without_replacing_content_or_code(self):
        r=response('print("opaque_A")',content='opaque_B')
        a=inspect(r,input_transport_ids={'opaque_A','opaque_B','absent'})
        b=inspect(r,input_transport_ids=())
        self.assertEqual(a['distinct_transport_references_with_public_text_substring_match'],2)
        self.assertEqual(a['syntax_actions_sha256'],b['syntax_actions_sha256'])
        self.assertEqual(a['content_sha256'],b['content_sha256'])

    def test_transport_extraction_reads_only_structured_input_fields(self):
        r={'messages':[{'role':'assistant','tool_calls':[{'id':'a'}],'content':'not_an_id'},
                       {'role':'tool','tool_call_id':'a','content':'b'}]}
        self.assertEqual(transport_ids(r),{'a'})

    def test_bounded_inputs_are_rejected_not_truncated(self):
        with self.assertRaises(ValueError):strict_object(' '*65537)
        with self.assertRaises(ValueError):strict_object('{"x":'+('['*65)+'0'+(']'*65)+'}')
        with self.assertRaises(ValueError):transport_ids({'messages':[{}]*513})

    def test_comparison_keeps_no_action_and_unknown_pairs_unavailable(self):
        empty=inspect(dict(status='ok',done_reason='stop',message={'content':'done'}))
        rows=[dict(case=case,structure=empty) for case in ('A','B') for _ in range(3)]
        result=comparison(rows,['A','B']);cross=result['cross'][0]
        self.assertEqual(cross['public_output']['equal'],9)
        self.assertEqual(cross['json_actions']['unavailable'],9)
        self.assertEqual(cross['both_without_structured_calls'],9)
        self.assertFalse(cross['pairs_are_independent_samples'])


if __name__=='__main__':unittest.main()

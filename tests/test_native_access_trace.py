import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from native_access_trace import Recorder, HELPER, transformed


class NativeAccessTraceTests(unittest.TestCase):
    def execute_pair(self, source, reply, recorder=None):
        outcomes=[]
        rec=recorder or Recorder()
        for instrument in (False, True):
            requests=[]
            def api(*args, **kwargs):
                requests.append((args, kwargs))
                return copy.deepcopy(reply)
            scope={'call_api':api, '__name__':'__main__'}
            if instrument:scope[HELPER]=rec
            stream=io.StringIO();error=None
            try:
                with contextlib.redirect_stdout(stream):
                    if instrument:rec.execute(source,scope,api,'continuation')
                    else:exec(compile(source,'<generated>','exec'),scope,scope)
            except BaseException as exc:
                error=type(exc).__name__+': '+str(exc)
            outcomes.append((stream.getvalue(),error,requests))
        self.assertEqual(*outcomes)
        return rec.summary()

    def test_native_types_and_nested_fields_remain_identical(self):
        r=self.execute_pair('d=call_api("x","read")\nassert type(d) is dict\n'
            'assert type(d["rows"]) is list\nprint(d["rows"][0]["id"])',
            {'rows':[{'id':3,'secret':'private-text'}],'unused':9})
        row=r['responses'][0]
        self.assertEqual(row['explicit_leaf_reads'],1)
        self.assertEqual(row['scalar_leaves'],3)
        self.assertNotIn('private-text',json.dumps(r))
        self.assertFalse(r['unobserved_means_unnecessary'])

    def test_get_defaults_and_missing_key_exception(self):
        r=self.execute_pair('d=call_api("x","read")\nprint(d.get("a"),d.get("missing",7))\nprint(d["missing"])',{'a':2})
        self.assertEqual(r['responses'][0]['explicit_leaf_reads'],1)

    def test_iteration_and_comprehension_observe_scalar_yields(self):
        r=self.execute_pair('a=call_api("x","read")\nprint([v*2 for v in a])',[1,2,3])
        self.assertEqual(r['responses'][0]['explicit_leaf_reads'],3)
        r=self.execute_pair('d=call_api("x","read")\nfor k in d:\n print(k)',{'a':2,'b':3})
        self.assertEqual(r['responses'][0]['explicit_leaf_reads'],0)
        self.assertGreater(r['responses'][0]['structure_operations'],0)

    def test_serialization_print_and_format_are_whole_exposures(self):
        for suffix in ('print(d)','print(f"value={d}")','import json\nprint(json.dumps(d))'):
            with self.subTest(suffix=suffix):
                r=self.execute_pair('d=call_api("x","read")\n'+suffix,{'a':1,'b':[2,3]})
                self.assertEqual(r['responses'][0]['presentation_exposed_leaves'],3)

    def test_opaque_native_calls_and_views_do_not_imply_unused(self):
        r=self.execute_pair('d=call_api("x","read")\nprint(list(d.items()))',{'a':1,'b':2})
        self.assertEqual(r['responses'][0]['opaque_exposed_leaves'],2)

    def test_mutation_and_aliases_mark_lineage_uncertain(self):
        for edit in ('a["v"]=5','a.update(v=5)','del a["v"]'):
            with self.subTest(edit=edit):
                r=self.execute_pair('a=call_api("x","read")\nb=a\n'+edit+'\nprint(b)',{'v':2})
                self.assertTrue(r['responses'][0]['mutation_observed'])

    def test_negative_index_slice_and_scalar_response(self):
        r=self.execute_pair('a=call_api("x","read")\nprint(a[-1],a[1:3])',[1,2,3])
        self.assertEqual(r['responses'][0]['explicit_leaf_reads'],1)
        self.assertEqual(r['responses'][0]['opaque_exposed_leaves'],3)
        r=self.execute_pair('a=call_api("x","read")\nprint(a+1)',3)
        self.assertTrue(r['responses'][0]['scalar_root_untracked'])

    def test_state_persists_across_programs_without_proxy_types(self):
        rec=Recorder();api=lambda *a,**k:{'field':8,'other':9}
        scope={'call_api':api,HELPER:rec}
        rec.execute('saved=call_api("x","read")',scope,api,'prefix')
        rec.execute('answer=saved["field"]\nassert type(saved) is dict',scope,api,'continuation')
        self.assertEqual(scope['answer'],8)
        self.assertEqual(rec.summary()['responses'][0]['explicit_leaf_reads'],1)

    def test_scope_sensitive_calls_kept_native_and_disclosed(self):
        r=self.execute_pair('d=call_api("x","read")\nprint(globals()["d"]["a"])\n'
                            'exec("extra=9")\nprint(extra)',{'a':2})
        self.assertGreater(r['unsupported_operations']['dynamic_code'],0)
        self.assertGreater(r['unsupported_operations']['introspection'],0)

    def test_keyword_function_argument_and_evaluation_order(self):
        r=self.execute_pair('d=call_api("x","read")\n'
            'def f(fn=1,self=2): return fn+self\nprint(f(fn=d["a"],self=5))',{'a':4})
        self.assertEqual(r['responses'][0]['explicit_leaf_reads'],1)

    def test_bounded_scan_and_helper_collision_are_not_silent(self):
        r=self.execute_pair('d=call_api("x","read")\nprint(d)',{'a':[1,2]},Recorder(max_nodes=1))
        self.assertTrue(r['responses'][0]['bounded_scan'])
        self.assertTrue(r['limits'])
        with self.assertRaises(ValueError):transformed(HELPER+' = 1')

    def test_alias_to_frame_sensitive_builtin_is_a_known_negative_control(self):
        # The recorder does not promise arbitrary Python equivalence. A driver
        # must reject this changed stdout instead of treating it as a saving.
        source='saved=7\ng=globals\nprint(g().get("saved"))'
        outputs=[];rec=Recorder()
        for traced in (False,True):
            scope={'__name__':'__main__',HELPER:rec};stream=io.StringIO()
            with contextlib.redirect_stdout(stream):
                if traced:rec.execute(source,scope,None,'continuation')
                else:exec(source,scope,scope)
            outputs.append(stream.getvalue())
        self.assertNotEqual(*outputs)
        self.assertGreater(rec.summary()['unsupported_operations']['introspection'],0)


if __name__=='__main__':unittest.main()

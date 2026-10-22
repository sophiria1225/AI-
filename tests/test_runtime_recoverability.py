import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime_recoverability import (fingerprint,parse_structured_stdout,scan,probe_source,
                                    resolve_witness,Unwitnessed,MAX_NODES)


class RuntimeRecoveryTests(unittest.TestCase):
    def test_typed_and_ordered_values(self):
        digest=lambda v:fingerprint(v,[MAX_NODES]).hex()
        self.assertEqual(digest({'a':1,'b':[2]}),digest({'b':[2],'a':1}))
        for a,b in ((True,1),(1,1.0),([1,2],[2,1]),([1],(1,)),(-0.0,0.0)):
            self.assertNotEqual(digest(a),digest(b))

    def test_only_whole_supported_literals(self):
        for text in ('{"a":[1,true]}',"{'a': [1, True]}"):
            self.assertEqual(parse_structured_stdout(text)['digest'],
                             fingerprint({'a':[1,True]},[MAX_NODES]).hex())
        for text in ('label {"a": 1}', '{"a":1}\n{"b":2}', '{"a":1,"a":2}',
                     "{'a':1,'a':2}", 'NaN', 'float("inf")', '[1]*10000000', '{1,2}'):
            with self.assertRaises((ValueError,SyntaxError)):parse_structured_stdout(text)

    def test_probe_does_not_change_namespace_or_values(self):
        value={'items':[1,2]};namespace={'__name__':'__main__','data':value,'print':1,'globals':2}
        # exec adds __builtins__ itself; set it before comparing the namespace.
        exec('pass',namespace)
        before={k:id(v) for k,v in namespace.items()}
        target=parse_structured_stdout('[1,2]')['digest']
        out=io.StringIO()
        with contextlib.redirect_stdout(out):exec(probe_source({'s1':target}),namespace)
        report=json.loads(out.getvalue())
        self.assertEqual(before,{k:id(v) for k,v in namespace.items()})
        self.assertEqual(value,{'items':[1,2]})
        self.assertEqual(report['matches']['s1'],[[['root','data'],['key','items']]])
        self.assertEqual(resolve_witness(namespace,report['matches']['s1'][0],target),[1,2])

    def test_old_route_invalid_after_rebinding_and_mutation(self):
        target=parse_structured_stdout('[1,2]')['digest'];scope={'data':[1,2]}
        path=scan(scope,{'s1':target})['matches']['s1'][0]
        scope['data'].append(3)
        with self.assertRaises(ValueError):resolve_witness(scope,path,target)
        scope['data']=[1,2]
        self.assertEqual(resolve_witness(scope,path,target),[1,2])
        del scope['data']
        with self.assertRaises(KeyError):resolve_witness(scope,path,target)

    def test_custom_methods_are_not_called(self):
        class Hostile(dict):
            def __iter__(self):raise AssertionError('iteration')
            def items(self):raise AssertionError('items')
            def __repr__(self):raise AssertionError('repr')
        result=scan({'unsafe':Hostile(a=1)}, {'s':parse_structured_stdout('{"a":1}')['digest']})
        self.assertEqual(result['matches']['s'],[])
        self.assertEqual(result['unwitnessed_roots'],{'unsupported_type':1})

    def test_bounds_cycles_and_incomplete_parent(self):
        value=[1];value.append(value)
        with self.assertRaises(Unwitnessed):fingerprint(value,[MAX_NODES])
        result=scan({'loop':value,'too_large':list(range(MAX_NODES+2))},
                    {'s':parse_structured_stdout('[1]')['digest']})
        self.assertTrue(result['node_limit_reached'])
        self.assertEqual(result['matches']['s'],[])

    def test_partial_tree_can_only_witness_checked_children(self):
        scope={'data':{'good':[1,2],'bad':object()}}
        result=scan(scope,{'s':parse_structured_stdout('[1,2]')['digest']})
        self.assertEqual(result['matches']['s'],[[('root','data'),('key','good')]])
        self.assertEqual(result['unwitnessed_roots'],{'unsupported_type':1})


if __name__=='__main__':unittest.main()

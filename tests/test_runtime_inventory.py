import contextlib,io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime_inventory import INVENTORY_CODE,validate_inventory,format_inventory


class RuntimeInventoryTests(unittest.TestCase):
    def run_inventory(self,scope):
        scope.setdefault('__builtins__',__builtins__)
        before={k:id(v) for k,v in scope.items()};out=io.StringIO()
        with contextlib.redirect_stdout(out):exec(INVENTORY_CODE,scope,scope)
        self.assertEqual(before,{k:id(v) for k,v in scope.items()})
        return validate_inventory(json.loads(out.getvalue()))

    def test_inventory_preserves_bindings_and_does_not_show_values(self):
        scope={'answer':{'private':'secret-scalar'},'token':'never-show-value','flag':True,
               '_hidden':'hidden','call_api':lambda:None,'api_schemas':{},'observations':[]}
        data=self.run_inventory(scope)
        self.assertEqual([r['name'] for r in data['bindings']],['answer','flag','token'])
        self.assertEqual(data['bindings'][0]['length'],1)
        self.assertIsNone(data['bindings'][2]['length'])
        self.assertNotIn('secret-scalar',format_inventory(data,['app__a']))
        self.assertNotIn('never-show-value',format_inventory(data,['app__a']))

    def test_custom_object_hooks_are_not_called(self):
        class Trap:
            def __repr__(self):raise AssertionError('repr invoked')
            def __len__(self):raise AssertionError('len invoked')
        data=self.run_inventory({'object':Trap(),'globals':7,'print':'shadow'})
        self.assertEqual(next(r for r in data['bindings'] if r['name']=='object')['type'],'other')

    def test_truncation_is_explicit_and_names_are_sorted(self):
        data=self.run_inventory({f'v{i:03d}':i for i in range(140)})
        self.assertEqual(data['eligible_binding_count'],140)
        self.assertEqual(len(data['bindings']),128);self.assertTrue(data['truncated'])
        bad={**data,'truncated':False}
        with self.assertRaises(ValueError):validate_inventory(bad)

    def test_unexpected_values_and_duplicate_names_are_rejected(self):
        data=self.run_inventory({'a':[1,2],'b':None})
        data['bindings'][0]['value']='private'
        with self.assertRaises(ValueError):validate_inventory(data)
        data=self.run_inventory({'a':[1,2],'b':None});data['bindings'][1]['name']='a'
        with self.assertRaises(ValueError):validate_inventory(data)

    def test_reset_state_does_not_invent_available_user_bindings(self):
        data=self.run_inventory({'call_api':lambda:None,'observations':[],'api_schemas':{}})
        self.assertEqual(data['eligible_binding_count'],0)
        self.assertFalse(data['truncated']);self.assertEqual(data['bindings'],[])

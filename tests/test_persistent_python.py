"""Run only fixed harmless bootstrap fixtures; no generated model code on host."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from persistent_api_python import BOOTSTRAP

class PersistentNamespace(unittest.TestCase):
    def invoke(self,programs):
        p=subprocess.Popen([sys.executable,'-I','-S','-c',BOOTSTRAP],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        results=[]
        try:
            for i,source in enumerate(programs,1):
                p.stdin.write(json.dumps({'program_index':i,'code':source,'observations':[{'n':i}],
                    'api_schemas':{'current':{'n':i}}})+'\n');p.stdin.flush()
                row=json.loads(p.stdout.readline())
                if row['kind']=='api':
                    self.assertEqual(row['id'],1)
                    p.stdin.write(json.dumps({'id':1,'ok':True,'value':7,'new_schemas':{'discovered':{}}})+'\n');p.stdin.flush()
                    row=json.loads(p.stdout.readline())
                results.append(row)
        finally:
            p.stdin.close();p.wait(timeout=5);p.stdout.close();p.stderr.close()
        return results
    def test_values_functions_and_imports_survive_program_boundary(self):
        rows=self.invoke(['import math\nx=7\ndef f():return x+1',
            'print(f(), math.isqrt(81),observations[0]["n"],api_schemas["current"]["n"])'])
        self.assertEqual(rows[1]['stdout'],'8 9 2 2\n')
        self.assertEqual([r['program_index'] for r in rows],[1,2])
    def test_partial_assignments_remain_after_python_error_and_helpers_refresh(self):
        rows=self.invoke(['x=13\ncall_api=None\nraise ValueError("fixture")',
            'print(x, callable(call_api))'])
        self.assertIn('ValueError',rows[0]['error'])
        self.assertEqual(rows[1]['stdout'],'13 True\n')
    def test_api_counter_resets_per_program_but_user_data_survives(self):
        rows=self.invoke(['alias=call_api\nx=alias("api_docs","echo")\nprint("discovered" in api_schemas)',
            'y=alias("api_docs","echo")\nprint(x+y)'])
        self.assertEqual(rows[0]['stdout'],'True\n')
        self.assertEqual(rows[1]['stdout'],'14\n')
    def test_new_interpreter_does_not_inherit_task_data(self):
        self.invoke(['task_private_value=14'])
        row=self.invoke(['print(task_private_value)'])[0]
        self.assertIn('NameError',row['error'])

if __name__=='__main__':unittest.main()

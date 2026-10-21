import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from data_python import DataPython, DataProgramError, run_program


class DataPythonTests(unittest.TestCase):
    def test_csv_quotes_delimiters_unicode_and_newlines(self):
        code = "result = csv_text([['x,y', '音楽'], ['a\\nb', 'c\"d']], ['A','B'])"
        result = run_program(code, [])['content']
        self.assertEqual(result, 'A,B\n"x,y",音楽\n"a\nb","c""d"\n')

    def test_data_dependent_union_and_projection_no_manual_target_values(self):
        obs = [{'ids': [2, 1, 2], 'rows': [
            {'id': 1, 'title': 'Alpha', 'artists': ['A', 'B']},
            {'id': 2, 'title': 'Beta', 'artists': ['C']}]}]
        code = '''wanted = set()
known = {}
for o in observations:
    wanted.update(o['ids'])
    for row in o['rows']:
        known[row['id']] = row
rows = [[known[i]['title'], '|'.join(known[i]['artists'])] for i in sorted(wanted)]
result = csv_text(rows, ['Title','Artists'])
'''
        result = run_program(code, obs)
        self.assertEqual(result['content'], 'Title,Artists\nAlpha,A|B\nBeta,C\n')
        changed = copy.deepcopy(obs)
        changed[0]['ids'] = [2]
        self.assertEqual(run_program(code, changed)['content'], 'Title,Artists\nBeta,C\n')

    def test_comprehension_scope_and_conditional(self):
        code = "x = 4\na = {i: i*2 for i in range(4) if i > 0}\nresult = str(x) + str(a[3])"
        self.assertEqual(run_program(code, [])['content'], '46')

    def test_reject_host_capabilities_and_object_introspection(self):
        for code in ["import os", "result = open('/etc/passwd').read()",
                     "result = observations.__class__.__name__", "result = eval('1')",
                     "result = __import__('os').getenv('HOME')", "while True:\n pass",
                     "def f():\n return 1", "class A:\n pass", "result = getattr('', '__class__')",
                     "result = '%1000000000000000000s' % 'x'"]:
            with self.subTest(code=code), self.assertRaises((DataProgramError, SyntaxError)):
                run_program(code, [])

    def test_step_and_allocation_limits(self):
        for code in ["result = 'x' * 10000000000", "a = list(range(10000000000)); result = ''",
                     "result = 2 ** 1000000000", "result = 'x'.replace('', 'y'*700000)",
                     "a = ['x'*100000]*1000\nresult = str(a)",
                     "result = csv_text([], ['x'*100000]*1000)"]:
            with self.subTest(code=code), self.assertRaises(DataProgramError):
                run_program(code, [])
        with self.assertRaisesRegex(DataProgramError, 'step_limit'):
            DataPython([], max_steps=20).run("for i in range(100):\n a = i\nresult = ''")

    def test_input_mutation_is_local_and_no_state_between_programs(self):
        value = [{'x': []}]
        run_program("observations[0]['x'].append(1)\nresult = 'ok'", value)
        self.assertEqual(value, [{'x': []}])
        self.assertEqual(run_program("result = str(len(observations[0]['x']))", value)['content'], '0')

    def test_missing_data_or_malformed_result_stays_failure(self):
        with self.assertRaises(KeyError):
            run_program("result = observations[0]['missing']", [{}])
        with self.assertRaisesRegex(DataProgramError, 'result_must_be_string'):
            run_program('result = [1, 2]', [])


if __name__ == '__main__':
    unittest.main()

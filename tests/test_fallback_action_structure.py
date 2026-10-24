import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from code_agent_interface import CODE_TOOLS
from fallback_output_replay import CASES, schedule
from inspect_fallback_action_structure import PLAN, ZERO, inspect
from public_action_structure import digest, inspect as describe


class FallbackActionStructureTests(unittest.TestCase):
    def fixture(self,root,storage,*,bad_parameters=False,bad_original=False):
        def save(path,value):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n')
            return hashlib.sha256(path.read_bytes()).hexdigest()
        rows=[]
        for item in schedule():
            folder=storage/'records/context_pilot/P84_fallback_output_v01'/item['id']
            request=dict(messages=[],tools=CODE_TOOLS if not bad_parameters else [])
            response=dict(status='ok',done_reason='tool_calls',message=dict(content=None,
                tool_calls=[dict(id='reference',function=dict(name='run_python',arguments='{"code":"pass","span_ids":[]}'))]))
            row=dict(**item,record_status='audited',request_sha256=save(folder/'request.json',request),
                response_sha256=save(folder/'response.json',response),public_output_sha256=describe(response)['public_output_sha256'])
            if bad_original:row['public_output_sha256']='0'*64
            rows.append(row)
        from itertools import combinations
        cross=[dict(left=a,right=b,equal_public_pairs=9,compared_pairs=9) for a,b in combinations(CASES,2)]
        report=dict(audit_errors=[],all_eighteen_audited=True,rows=rows,unknown_usage_calls=0,
                    owned_processes_absent=True,equality_summary={'cross':cross},model_calls_attempted=18,known_total_tokens=18)
        path='reports/P84_fallback_output_replay.json';report_hash=save(root/path,report)
        save(root/PLAN,dict(phase='P93',cases=list(CASES),schedule=schedule(),max_wall_seconds=120,
            max_file_bytes=16777216,max_public_characters=65536,max_tool_calls_per_response=16,
            max_source_characters=20000,max_ast_nodes=5000,max_JSON_nodes=5000,max_JSON_depth=64,
            max_input_messages=512,max_input_transport_references=512,novel_method_claim=False,
            **{k:0 for k in ZERO},source_sha256={path:report_hash},selection='synthetic fixture'))

    def test_all_eighteen_and_all_fifteen_original_comparisons_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage)
            with patch('inspect_fallback_action_structure.subprocess.check_output',return_value='a'*40):result=inspect(storage,root)
            self.assertEqual(len(result['rows']),18);self.assertEqual(len(result['comparison']['cross']),15)
            self.assertTrue(result['original_public_comparisons_preserved'])
            self.assertEqual(result['saved_code_executions'],0)
            self.assertFalse(result['semantic_equivalence_established'])

    def test_a_different_recorded_interface_is_not_silently_validated(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage,bad_parameters=True)
            with self.assertRaisesRegex(ValueError,'declared_tool_parameters'):inspect(storage,root)

    def test_old_public_fingerprint_is_not_replaced_by_new_normalization(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage,bad_original=True)
            with self.assertRaisesRegex(ValueError,'original_public_payload'):inspect(storage,root)

    def test_changed_private_response_is_rejected_before_inspection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';storage=Path(d)/'storage';self.fixture(root,storage)
            path=storage/'records/context_pilot/P84_fallback_output_v01/call_001/response.json'
            path.write_text('{}')
            with self.assertRaises(ValueError):inspect(storage,root)


if __name__=='__main__':unittest.main()

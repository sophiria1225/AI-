"""Preserve complete cohorts and missing receipts in offline P88 diagnostics."""
import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_whole_task_reasoning_outputs import DEPENDENCIES, inspect
from test_whole_task_reasoning_budget_reporting import fixture, replace_report
from run_context_comparison import write_json
from run_handoff_factors import read, sha
from whole_task_reasoning_budget import BUDGETS, summarize

ROOT = Path(__file__).resolve().parents[1]


def response(code="raise RuntimeError('synthetic_never_execute')"):
    return dict(status='ok', output_tokens=20, done_reason='tool_calls',
        message=dict(reasoning_content='synthetic_private_reasoning', content='', tool_calls=[
            dict(function=dict(name='run_python', arguments=json.dumps({'code': code, 'span_ids': []})))]))


def data(base, variants=None, missing=False, no_run=False):
    root, _, rows = fixture(base); storage = base / 'storage'
    for source in DEPENDENCIES:
        target = root / source; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    for index, row in enumerate(rows):
        if no_run and index == 7:
            for key in list(row):
                if key not in ('run_id','task_id','reasoning_policy','time_visibility'): del row[key]
            row.update(record_status='not_run', success=None, known_total_tokens=None, unknown_usage_calls=None)
            continue
        folder = storage / 'records/context_pilot' / row['run_id']; folder.mkdir(parents=True)
        value = (variants or {}).get(index, response())
        absent = missing and index == 6
        known = value['status'] == 'ok' and not absent
        row['unknown_usage_calls'] = int(not known)
        row['output_tokens'] = value['output_tokens'] if known else 0
        row['known_total_tokens'] = row['input_tokens'] + row['output_tokens'] if known else 0
        for name in ('summary','usage','evaluation'):
            write_json(folder / (name+'.json'), {'fixture': name})
            row[name+'_sha256'] = sha(folder / (name+'.json'))
        sub = folder / 'call_001'; sub.mkdir()
        request = dict(max_tokens=4096, reasoning_budget_tokens=BUDGETS[row['reasoning_policy']])
        if not absent:
            write_json(sub / 'request.json', request); write_json(sub / 'response.json', value)
        row['request_checks'] = [dict(call_id='call_001', status='ok' if known else 'error',
            request_sha256=None if absent else sha(sub / 'request.json'),
            response_sha256=None if absent else sha(sub / 'response.json'))]
    private = storage / 'records/context_pilot/P88_pipeline_v01'; private.mkdir(parents=True)
    write_json(private / 'status.json', {'status':'complete', 'server_stopped': True})
    write_json(private / 'server_final.json', {'status':'stopped'})
    def update(report):
        report.update(rows=rows, **summarize(rows, []),
            pipeline_status_sha256=sha(private/'status.json'), server_final_sha256=sha(private/'server_final.json'))
    replace_report(root, update)
    path = root / 'reports/P88_server_session.json'; session = read(path)
    session['pipeline_source_sha256'] = sha(private/'status.json'); write_json(path, session)
    return root, storage, rows


def run(root, storage, output):
    with contextlib.redirect_stdout(io.StringIO()):
        return inspect(storage, root, output)


class WholeTaskReasoningOutputTests(unittest.TestCase):
    def test_all_calls_bound_without_executing_or_publishing_content(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); root, storage, _=data(base); output=base/'output'
            result=run(root,storage,output)
            self.assertEqual(result['observed_attempts'],8)
            self.assertEqual(len(result['cells']),8)
            self.assertEqual(sum(x['complete_code_submissions'] for x in result['by_policy']),8)
            self.assertFalse(result['syntax_is_task_quality'])
            public=''.join(p.read_text() for p in output.iterdir())
            self.assertNotIn('synthetic_private_reasoning',public)
            self.assertNotIn('synthetic_never_execute',public)

    def test_length_no_action_and_invalid_shapes_remain_distinct(self):
        cap=response(); cap.update(done_reason='length',output_tokens=4096)
        no_action=response(); no_action.update(done_reason='stop'); no_action['message']['tool_calls']=[]
        bad_json=response(); bad_json['message']['tool_calls'][0]['function']['arguments']='{"code":'
        bad_shape=response(); bad_shape['message']['tool_calls'][0]['function']['arguments']='{"code":"x=1"}'
        bad_syntax=response('x = (')
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); root, storage, _=data(base,{0:cap,1:no_action,2:bad_json,3:bad_shape,4:bad_syntax})
            result=run(root,storage,base/'output'); groups=result['by_policy']
            for key in ('at_requested_cap','known_responses_without_tool_calls','malformed_json_calls',
                        'shape_invalid_calls','syntax_invalid_calls'):
                self.assertEqual(sum(x[key] for x in groups),1)
            self.assertEqual(sum(x['complete_code_submissions'] for x in groups),3)
            self.assertEqual(sum(x['explicit_reasoning_token_receipts'] for x in groups),0)
            self.assertFalse(result['forced_budget_activation_observable_from_this_profile'])

    def test_missing_dispatch_receipt_and_unrun_condition_are_not_empty_successes(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); root, storage, _=data(base,missing=True,no_run=True)
            result=run(root,storage,base/'output')
            self.assertEqual(len(result['cells']),8); self.assertEqual(result['observed_attempts'],7)
            self.assertIsNone(result['cells'][-1]['attempts'])
            self.assertEqual(sum(x['unknown_terminals'] for x in result['by_policy']),1)
            self.assertEqual(sum(x['complete_code_submissions'] for x in result['by_policy']),6)
            with (base/'output/all_calls.csv').open() as stream: rows=list(csv.DictReader(stream))
            self.assertEqual(rows[-1]['output_tokens'],''); self.assertEqual(rows[-1]['requested_max_tokens'],'')
            self.assertEqual(rows[-1]['complete_code_submission'],'')

    def test_tampering_order_budget_or_missing_attempt_is_rejected(self):
        for kind in ('bytes','order','budget','attempts','new_file'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                base=Path(temp); root,storage,rows=data(base,missing=kind=='new_file')
                index=6 if kind=='new_file' else 0
                path=storage/'records/context_pilot'/rows[index]['run_id']/'call_001'
                if kind=='bytes': (path/'response.json').write_text('{}')
                elif kind=='new_file': write_json(path/'response.json',response())
                elif kind=='budget':
                    request=read(path/'request.json'); request['reasoning_budget_tokens']=1024
                    write_json(path/'request.json',request)
                    rows[index]['request_checks'][0]['request_sha256']=sha(path/'request.json')
                elif kind=='order': rows[index]['request_checks'][0]['call_id']='call_002'
                else: rows[index]['model_calls']=2
                replace_report(root,lambda r:r.update(rows=rows))
                with self.assertRaises((ValueError,FileNotFoundError)): run(root,storage,base/'output')
                self.assertFalse((base/'output').exists())

    def test_active_pipeline_and_reusing_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); root,storage,_=data(base); output=base/'output'
            run(root,storage,output)
            with self.assertRaises(FileExistsError): run(root,storage,output)
            state=storage/'records/context_pilot/P88_pipeline_v01/status.json'
            write_json(state,{'status':'running','server_stopped':False})
            replace_report(root,lambda r:r.update(pipeline_status_sha256=sha(state)))
            session=root/'reports/P88_server_session.json'; write_json(session,read(session)|{'pipeline_source_sha256':sha(state)})
            with self.assertRaises(ValueError): run(root,storage,base/'second_output')


if __name__ == '__main__': unittest.main()

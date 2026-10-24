import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit_choice_context as audit
from choice_context_replay import conditions, digest, input_comparisons
from probe_prompt_identity import render_summary
from run_context_comparison import write_json
from run_handoff_factors import sha
from test_choice_context_replay import counts, original, plan, worker_fixture


def fixture(base,fail_at=None,tamper=None):
    code,state,sent=worker_fixture(base,fail_at=fail_at)
    root=base/'repo';storage=base/'storage';fixed=plan()
    for case in fixed['cases']:case['source_request_sha256']='synthetic-source'
    requests={key:{**original(),'tool_choice':key.rsplit('__',1)[1],
                  'messages':[{'role':'user','content':key}]} for key in conditions()}
    pre=json.loads((root/audit.PREFLIGHT).read_text());pre['rendered']={}
    for key in conditions():
        choice=key.rsplit('__',1)[1]
        folder=storage/'records/context_pilot/P101_preflight_v01'/('render_'+choice)
        folder.mkdir(parents=True,exist_ok=True)
        value=dict(input_tokens=counts()[key],prompt='synthetic '+key,tokens=[1]*counts()[key],
                   session_controls={'tool_choice':choice},parsed_non_message_parameters={'tool_choice':choice})
        path=folder/(key+'_rendered_private.json');write_json(path,value)
        pre['rendered'][key]={**render_summary(value),'private_rendered_sha256':sha(path)}
        write_json(folder/(key+'_request_private.json'),requests[key])
    pre['reserved_total_tokens']=3*sum(v+4096 for v in counts().values())
    pre['input_comparisons']=input_comparisons(pre['rendered']);pre['rendering_operations']=[];pre['input_count_requests']=12
    for row in pre['rows']:row.update(input_tokens=counts()[row['condition']],status='counted')
    write_json(root/audit.PREFLIGHT,pre)
    pipeline=storage/'records/context_pilot/P101_pipeline_v01';pipeline.mkdir()
    server_dir=storage/'synthetic-server';server_dir.mkdir()
    server=dict(status='stopped',stop_reason='synthetic',started_at='synthetic',wall_seconds=1,
        load_wall_seconds=.1,sampled_peak_rss_bytes=10,peak_system_swap_bytes=0,exit_code=0,
        model_revision='synthetic',runtime={},ctx_size=65536,cache_type_k='q8_0',cache_type_v='q8_0',
        memory_note='synthetic',pid=999998,supervisor_pid=999997,record_directory=str(server_dir))
    write_json(server_dir/'summary.json',server)
    (server_dir/'memory.jsonl').write_text(json.dumps({'swap_used_bytes':0})+'\n')
    write_json(pipeline/'server_final.json',server)
    write_json(pipeline/'status.json',dict(status='complete' if not code else 'stopped',
        server_stopped=True,server_supervisor_pid=999997,wall_seconds=1,stages=[]))
    if tamper=='request':
        folder=storage/'records/context_pilot'/fixed['batch_id']/'call_001'
        value=json.loads((folder/'request.json').read_text());value['tool_choice']='required'
        write_json(folder/'request.json',value)
    elif tamper=='rendering':
        key=conditions()[0];folder=storage/'records/context_pilot/P101_preflight_v01/render_auto'
        path=folder/(key+'_rendered_private.json');value=json.loads(path.read_text());value['tokens'][0]=2;write_json(path,value)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(audit,'sources',return_value=(fixed,{},requests)))
        stack.enter_context(patch.object(audit,'frozen_hashes',return_value={}))
        stack.enter_context(patch.object(audit.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        result=audit.audit(storage,root)
    return result,len(sent)


class ChoiceContextAuditTests(unittest.TestCase):
    def test_full_worker_to_audit_round_trip_preserves_all_slots_and_costs(self):
        with tempfile.TemporaryDirectory() as t:result,sent=fixture(Path(t))
        self.assertEqual(sent,36);self.assertTrue(result['all_36_audited'])
        self.assertEqual(result['audit_errors'],[]);self.assertEqual(len(result['rows']),36)
        self.assertEqual(result['known_total_tokens'],3*sum(v+4 for v in counts().values()))
        self.assertEqual(result['audit_additional_model_calls'],0)
        self.assertTrue(result['static_submission_is_not_execution'])

    def test_unknown_attempt_and_32_unattempted_slots_remain_in_audit(self):
        with tempfile.TemporaryDirectory() as t:result,sent=fixture(Path(t),fail_at=4)
        self.assertEqual(sent,4);self.assertFalse(result['all_36_audited'])
        self.assertEqual(result['audit_errors'],[]);self.assertEqual(result['unknown_usage_calls'],1)
        self.assertEqual(sum(r['record_status']=='unattempted' for r in result['rows']),32)
        self.assertIsNone(result['rows'][3]['output_tokens'])

    def test_mutated_request_or_rendering_is_not_silently_accepted(self):
        for kind in ('request','rendering'):
            with tempfile.TemporaryDirectory() as t:result,sent=fixture(Path(t),tamper=kind)
            self.assertEqual(sent,36);self.assertFalse(result['all_36_audited'])
            self.assertTrue(result['audit_errors']);self.assertEqual(len(result['rows']),36)


if __name__=='__main__':unittest.main()

"""Inspect all eighteen closed P84 public outputs once, without rerunning them."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import time

from code_agent_interface import CODE_TOOLS
from fallback_output_replay import CASES, schedule
from inspect_public_read_opportunity import read_bound, sha
from public_action_structure import comparison, digest, inspect as describe, transport_ids

PLAN='configs/P93_public_action_structure_v01.json'
ZERO=('model_generations','environment_api_requests','evaluator_calls','saved_code_executions',
      'task_databases_read','reserved_scenarios_read')


def inspect(storage,root):
    began=time.monotonic();plan=json.loads((root/PLAN).read_text())
    fixed=dict(phase='P93',cases=list(CASES),schedule=schedule(),max_wall_seconds=120,
        max_file_bytes=16777216,max_public_characters=65536,max_tool_calls_per_response=16,
        max_source_characters=20000,max_ast_nodes=5000,max_JSON_nodes=5000,max_JSON_depth=64,
        max_input_messages=512,max_input_transport_references=512,novel_method_claim=False,
        **{k:0 for k in ZERO})
    if any(plan.get(k)!=v for k,v in fixed.items()):raise ValueError('fixed_P93_scope_changed')
    for name,expected in plan['source_sha256'].items():
        if sha(root/name)!=expected:raise ValueError('fixed_helper_changed: '+name)
    prior=read_bound(root/'reports/P84_fallback_output_replay.json',
        plan['source_sha256']['reports/P84_fallback_output_replay.json'])
    if (prior['audit_errors'] or prior['all_eighteen_audited'] is not True
            or len(prior['rows'])!=18 or prior['unknown_usage_calls']!=0
            or prior['owned_processes_absent'] is not True):
        raise ValueError('closed_all_eighteen_P84_required')
    expected_params={tool['function']['name']:tool['function']['parameters'] for tool in CODE_TOOLS}
    rows=[]
    for item,source in zip(schedule(),prior['rows'],strict=True):
        if any(source[k]!=v for k,v in item.items()) or source['record_status']!='audited':
            raise ValueError('all_fixed_original_rows_required')
        folder=storage/'records/context_pilot/P84_fallback_output_v01'/item['id']
        folder.resolve().relative_to((storage/'records/context_pilot/P84_fallback_output_v01').resolve())
        request=read_bound(folder/'request.json',source['request_sha256'])
        response=read_bound(folder/'response.json',source['response_sha256'])
        tools=request.get('tools')
        if (type(tools) is not list or len(tools)!=2
                or {t['function']['name']:t['function']['parameters'] for t in tools}!=expected_params):
            raise ValueError('declared_tool_parameters_differ_from_inspected_contract')
        structure=describe(response,input_transport_ids=transport_ids(request))
        if structure['public_output_sha256']!=source['public_output_sha256']:
            raise ValueError('original_public_payload_fingerprint_differs')
        rows.append(dict(**item,original=dict(source),structure=structure,
            private_file_sha256={'request.json':source['request_sha256'],'response.json':source['response_sha256']},
            declared_tool_parameters_checked=True))
    compared=comparison(rows,list(CASES))
    for current,original in zip(compared['cross'],prior['equality_summary']['cross'],strict=True):
        if (current['left']!=original['left'] or current['right']!=original['right']
                or current['public_output']['equal']!=original['equal_public_pairs']
                or current['pairs']!=original['compared_pairs']):
            raise ValueError('original_public_comparison_changed')
    return dict(phase='P93',status='complete',checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        plan_sha256=sha(root/PLAN),source_sha256=plan['source_sha256'],rows=rows,
        comparison=compared,original_generations=prior['model_calls_attempted'],
        original_known_logical_tokens=prior['known_total_tokens'],original_unknown_usage_calls=prior['unknown_usage_calls'],
        original_public_comparisons_preserved=True,private_reasoning_inspected_semantically=False,
        literal_and_identifier_values_preserved=True,transport_reference_text_not_rewritten=True,
        semantic_equivalence_established=False,task_quality_measured=False,novel_method_claim=False,
        measured_savings=None,wall_seconds=time.monotonic()-began,**{k:0 for k in ZERO},
        selection=plan['selection'],interpretation='JSON action form and location-free Python AST only. Missing structured calls are not equal valid actions. AST differences do not establish different runtime behavior, correctness, or quality.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    target=root/'reports/P93_public_action_structure.json';failure=root/'reports/P93_public_action_structure_failure.json'
    if target.exists() or failure.exists():raise FileExistsError('preserve_every_P93_inspection')
    def expired(*_):raise TimeoutError('fixed_readonly_deadline')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,120);began=time.monotonic()
    try:
        result=inspect(args.storage_root.resolve(),root);target.write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P93',status='failed_readonly_inspection',error_type=type(error).__name__,
            detail=str(error),wall_seconds=time.monotonic()-began,**{k:0 for k in ZERO}),indent=2)+'\n');raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    print(json.dumps(dict(rows=len(result['rows']),wall_seconds=result['wall_seconds'],
        kinds=[dict(id=r['id'],case=r['case'],kind=r['structure']['status'],tools=r['structure']['tool_calls'],
                   JSON_objects=r['structure']['JSON_objects'],Python_ASTs=r['structure']['Python_ASTs_valid']) for r in result['rows']])))


if __name__=='__main__':main()

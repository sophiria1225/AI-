"""P52: four already-known prefixes, no inference, environment or replay."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from contract_use_retention import MODES,build_use_view
from documentation_print_origin import build_origin_view
from later_handoff_sources import prepare_later_sources

ROOT=Path(__file__).resolve().parents[1]
PLAN='configs/P52_contract_use_retention_v01.json'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def inspect(storage):
    plan=read(ROOT/PLAN)
    if (plan['source_runs']!=[f'P29_{i:02d}_CODE' for i in range(1,5)]
            or plan['modes']!=list(MODES) or plan['boundary_after_model_calls']!=8
            or plan['max_wall_seconds']!=120 or any(plan[k]!=0 for k in
                ('model_generations','tokenizer_requests','environment_api_requests',
                 'program_reexecutions','evaluator_calls','reserved_scenarios_read'))):
        raise ValueError('outside fixed P52 scope')
    for relative,digest in plan['source_reports_sha256'].items():
        if sha(ROOT/relative)!=digest:raise ValueError('source report changed')
    out=storage/'records/context_pilot/P52_contract_use_retention_v01'
    out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();save(out/'plan.json',plan)
    result={'phase':'P52','status':'running','started_at':datetime.now(timezone.utc).isoformat(),
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':{p:sha(ROOT/p) for p in plan['implementation_sources']+[PLAN]},
        'source_reports_sha256':plan['source_reports_sha256'],'rows':[],
        **{k:0 for k in ('model_generations','tokenizer_requests','environment_api_requests',
            'program_reexecutions','evaluator_calls','reserved_scenarios_read')},
        'generation_comparison_authorized':False,'future_irrelevance_proven':False,
        'novel_method_established':False,'quality_preservation_claim':False,'token_savings_measured':False}
    try:
        _,original,_,schemas,items=prepare_later_sources(storage,ROOT)
        if [item['source_run'] for item in items]!=plan['source_runs']:raise ValueError('source order')
        prior=read(ROOT/'reports/P44_documentation_origin.json')
        for item,old in zip(items,prior['rows'],strict=True):
            if time.monotonic()-started>120:raise TimeoutError('P52 passive wall limit')
            if item['boundary_manifest_sha256']!=old['boundary_manifest_sha256']:
                raise ValueError('boundary changed')
            views,origin=build_origin_view(item)
            if origin!=old['selection']:raise ValueError('P44 recognition changed')
            full,formatting=views['full_keep'].for_model(original['observation_page_characters'])
            if formatting!={'text_fallback_turns':0,'paged_spans':0}:raise ValueError('input format')
            previous=storage/'records/context_pilot/P44_documentation_origin_v01'/(
                item['source_run']+'_full_keep_private.json')
            if full!=read(previous):raise ValueError('full input changed')
            full_text=json.dumps(full,ensure_ascii=False,separators=(',',':'))
            row={'source_run':item['source_run'],'task_id':item['task_id'],
                'boundary_manifest_sha256':item['boundary_manifest_sha256'],
                'original_source_sha256':item['source_sha256'],
                'full_input_characters':len(full_text),'candidate_outputs':origin['candidate_outputs'],
                'p44_changed_outputs':origin['changed_outputs'],'views':{}}
            for mode in MODES:
                view,meta=build_use_view(item,schemas,mode)
                messages,fmt=view.for_model(original['observation_page_characters'])
                if fmt!=formatting:raise ValueError('candidate formatting changed')
                path=out/(item['source_run']+'_'+mode+'_private.json');save(path,messages)
                characters=len(json.dumps(messages,ensure_ascii=False,separators=(',',':')))
                row['views'][mode]={'selection':meta,'input_characters':characters,
                    'input_characters_removed':len(full_text)-characters,'private_input_sha256':sha(path)}
            result['rows'].append(row);save(out/'status.json',result)
        if len(result['rows'])!=4 or sum(r['candidate_outputs'] for r in result['rows'])!=23:
            raise ValueError('incomplete original source coverage')
        result['status']='complete'
    except BaseException as error:
        result.update(status='stopped',failure_type=type(error).__name__)
        raise
    finally:
        result['wall_seconds']=time.monotonic()-started
        save(out/'status.json',result);save(ROOT/'reports/P52_contract_use_retention.json',result)
    print(json.dumps({'status':result['status'],'wall_seconds':result['wall_seconds'],'rows':[
        {'source_run':r['source_run'],'modes':{m:{'changed_outputs':v['selection']['changed_outputs'],
        'input_characters_removed':v['input_characters_removed']} for m,v in r['views'].items()}}
        for r in result['rows']]}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',required=True,type=Path)
    inspect(parser.parse_args().storage_root.resolve())

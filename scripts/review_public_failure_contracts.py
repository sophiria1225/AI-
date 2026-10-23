"""Post-P77 source review of all three public program errors; no execution/retry.

Message markers describe this pinned record only. They are not stable Python
error APIs and must not become an online recovery controller.
"""
import ast
import hashlib
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
STORAGE=Path('/Users/tp26013/AI-')
REPORT=ROOT/'reports/P77_public_failure_contract_review.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())


def review():
    if REPORT.exists():raise FileExistsError('preserve_the_public_contract_review')
    started=time.monotonic();p77=read(ROOT/'reports/P77_public_path_scope.json')
    if sha(ROOT/'reports/P77_public_path_scope.json')!='78a8dfe68254dbec4d8fc564fbab915ccefb6b4a10beaafcafb0f663864c7f8a':
        raise ValueError('closed_P77_changed')
    selected=[(row,p) for row in p77['rows'] for p in row['programs'] if p['status']=='execution_error']
    if len(selected)!=3:raise ValueError('all_three_error_population_required')
    result={'scope':'post_P77_public_source_review_all_three_errors','rows':[],
            'P77_source_sha256':sha(ROOT/'reports/P77_public_path_scope.json'),
            'new_model_calls':0,'new_api_requests':0,'new_evaluator_calls':0,
            'saved_code_executions':0,'database_contents_read':0,'reserved_scenarios_read':0,
            'private_reasoning_text_read':0,'automatic_repair_or_retry':False,
            'old_P77_report_changed':False,'source_sha256':{}}
    for row,p in selected:
        if time.monotonic()-started>30:raise TimeoutError('bounded_contract_review')
        path=STORAGE/'records/context_pilot'/row['run_id']/'spans.json'
        if path.stat().st_size>4194304 or sha(path)!=p77['private_record_sha256'][row['run_id']]['spans.json']:
            raise ValueError('original_public_source_changed')
        spans=read(path);span=spans[p['span_id']];observation=span['observation']
        args=json.loads(span['action']['arguments']);code=args['code']
        if hashlib.sha256(code.encode()).hexdigest()!=p['shape']['source_sha256']:
            raise ValueError('public_code_changed')
        tree=ast.parse(code)
        calls=[]
        for receipt in observation['api_receipts']:
            item=spans[receipt['span_id']];raw=item['observation'].get('observation')
            parsed=True
            try:value=json.loads(raw) if isinstance(raw,str) else raw
            except ValueError:value=raw;parsed=False
            calls.append({'api':receipt['api'],'api_request_sent':receipt['api_request_sent'],
                'argument_names':sorted(json.loads(item['action']['arguments'])),
                'value_type_delivered_to_python':type(value).__name__,'json_decoded':parsed,
                'top_level_keys':sorted(value) if type(value)is dict else None,
                'public_text_contains_traceback_marker':type(value)is str and 'Traceback' in value,
                'public_observation_sha256':hashlib.sha256(json.dumps(item['observation'],sort_keys=True).encode()).hexdigest()})
        error=observation['error']
        record={'run_id':row['run_id'],'call_id':p['call_id'],'span_id':p['span_id'],
            'source_sha256':p['shape']['source_sha256'],'exception_type':p['exception_type'],
            'public_error_sha256':hashlib.sha256(error.encode()).hexdigest(),
            'read_only_filesystem_marker':'Read-only file system' in error,
            'errno_30_marker':'[Errno 30]' in error,
            'string_index_type_error_marker':'string indices must be integers' in error,
            'direct_open_sites':[{'line':n.lineno,'literal_mode':n.args[1].value if len(n.args)>1
                    and isinstance(n.args[1],ast.Constant) and n.args[1].value in ('w','wb','a','ab','r','rb') else None}
                for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='open'],
            'subscript_base_names':sorted({n.value.id for n in ast.walk(tree)
                if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Name)}),
            'api_returns':calls,'error_text_is_online_control_contract':False}
        result['rows'].append(record)
        result['source_sha256'][str(path.relative_to(STORAGE))]=sha(path)
    public_sources=['scripts/container_api_python.py','scripts/persistent_api_python.py','scripts/code_agent_interface.py',
                    'scripts/context_preservation.py','scripts/stateful_code_prompts.py']
    result['repository_source_sha256']={name:sha(ROOT/name) for name in public_sources}
    base=STORAGE/'.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps'
    result['public_api_implementation_sha256']={name:sha(base/name) for name in ['phone/apis.py','file_system/apis.py']}
    result['review_script_sha256']=sha(Path(__file__))
    result['wall_seconds']=time.monotonic()-started
    with REPORT.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'reviewed_error_programs':len(result['rows']),'wall_seconds':result['wall_seconds'],
        'rows':[{k:r[k] for k in ['run_id','exception_type','read_only_filesystem_marker','errno_30_marker',
                                'string_index_type_error_marker','direct_open_sites','subscript_base_names']}
                for r in result['rows']]},ensure_ascii=False))


if __name__=='__main__':review()

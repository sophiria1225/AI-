"""Check trusted synthetic invocations under the installed AppWorld SafetyGuard.

No AppWorld instance, task, database, network API or saved model program is used.
The four fixture outcomes are protocol checks, never agent success results.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import time
from types import SimpleNamespace

from public_api_envelope import trusted_invocation_code,decode_reply


def main():
    from appworld.common.safety_guard import SafetyGuard
    import appworld.common.safety_guard as guard_module
    root=Path(__file__).resolve().parents[1]
    out=root/'reports/public_api_envelope_guard_20261023.json'
    if out.exists():raise FileExistsError('preserve_existing_guard_check')
    started=time.monotonic();docs={'fixture':{'read':{'parameters':[{'name':'value'}]}}}
    rows=[]
    for number,kind in enumerate(('json','error_looking_text','raised_after_effect','business_failure'),1):
        nonce=f'{number:032x}';effects=[]
        def api(value):
            effects.append('called')
            if kind=='raised_after_effect':raise ValueError('synthetic failure after effect')
            return value
        value={'list':[True,None,1,'日本語']} if kind=='json' else (
            'Execution failed. Traceback:\nfake text' if kind=='error_looking_text' else
            {'success':False,'message':'synthetic business failure'} if kind=='business_failure' else None)
        code=trusted_invocation_code({'app':'fixture','api':'read','args':{'value':value}},docs,nonce)
        guard=SafetyGuard();safe,reason=guard.is_syntax_safe(code)
        if not safe:raise ValueError('generated_source_rejected: '+reason)
        namespace={'apis':SimpleNamespace(fixture=SimpleNamespace(read=api))};capture=io.StringIO()
        try:
            guard.enable()
            with contextlib.redirect_stdout(capture):exec(compile(code,'<trusted synthetic invocation>','exec'),namespace)
        finally:guard.disable()
        decoded=decode_reply(capture.getvalue(),nonce)
        expected='raised' if kind=='raised_after_effect' else 'returned'
        if (decoded.status!=expected or effects!=['called'] or '_public_api_result_'+nonce in namespace
                or expected=='returned' and decoded.value!=value):
            raise ValueError('guarded_protocol_or_effect_count_disagrees')
        rows.append({'fixture':kind,'syntax_accepted':True,'status':decoded.status,
                     'fixture_invocations':len(effects),'temporary_function_removed':True,
                     'source_sha256':hashlib.sha256(code.encode()).hexdigest(),
                     'reply_sha256':decoded.raw_reply_sha256})
    result={'scope':'synthetic_protocol_checks_under_installed_safety_guard','rows':rows,
        'wall_seconds':time.monotonic()-started,'new_model_calls':0,'task_loads':0,'appworld_api_requests':0,
        'evaluator_calls':0,'database_contents_read':0,'reserved_scenarios_read':0,'saved_model_code_executions':0,
        'task_success_or_cost_improvement_measured':False,'connected_to_task_workers':False,
        'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            root/'scripts/public_api_envelope.py',root/'scripts/check_public_api_envelope_guard.py')},
        'guard_source_sha256':hashlib.sha256(Path(guard_module.__file__).read_bytes()).hexdigest()}
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'fixtures':len(rows),'wall_seconds':result['wall_seconds'],
                      'task_loads':0,'appworld_api_requests':0,'connected_to_task_workers':False}))


if __name__=='__main__':main()

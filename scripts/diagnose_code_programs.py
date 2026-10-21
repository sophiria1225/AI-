"""Post-cohort diagnostics without publishing code, tool arguments or raw errors.

These counters describe execution. They do not identify a causal remedy, and a
Python exception does not imply that earlier API effects were rolled back.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from analyze_code_comparison import require_complete

ROOT = Path(__file__).resolve().parents[1]
ERROR_TYPES = {'SyntaxError','IndentationError','TabError','NameError','KeyError',
               'TypeError','ValueError','IndexError','AttributeError','RuntimeError',
               'ImportError','ModuleNotFoundError','UnboundLocalError','AssertionError',
               'ZeroDivisionError','StopIteration','SystemExit','MemoryError'}


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def classify(usage, events, spans, programs):
    classes = Counter()
    rows = []
    for call in usage:
        ev = [e for e in events if e['call'] == call['id']]
        actual = [e for e in ev if e['api_request_sent']]
        outer = [spans[e['span_id']] for e in ev if e['stage'] == 'model_tool']
        inner = [spans[e['span_id']] for e in ev if e['stage'] == 'python_api']
        executed = programs.get(call['id'], [])
        flags = []
        if call.get('finish_reason') == 'length': flags.append('generation_limit')
        if any('format_error' in s.get('observation', {}) for s in outer):
            flags.append('outer_format_rejected')
        if any('format_error' in s.get('observation', {}) for s in inner):
            flags.append('inner_schema_rejected')
        if any('api_error' in s.get('observation', {}) for s in inner):
            flags.append('api_returned_error')
        if any(p.get('error') for p in executed): flags.append('program_error')
        if any(p.get('stdout_truncated') for p in executed): flags.append('printed_output_truncated')
        if not actual: flags.append('no_api_dispatched')
        if not executed: flags.append('no_program_executed')
        if any(e.get('effects_unknown') for e in ev): flags.append('unknown_effects')
        classes.update(flags)
        rows.append({'call_id':call['id'], 'flags':flags,
                     'sent_api':len(actual), 'programs':len(executed)})
    errors=Counter();status=Counter();after_effect=0
    for ps in programs.values():
        for p in ps:
            status[p['status']]+=1
            if p.get('error'):
                typename=p['error'].split(':',1)[0]
                errors[typename if typename in ERROR_TYPES else 'other_error']+=1
                after_effect+=int(p.get('api_requests',0)>0)
    return {'model_calls':len(usage),'call_flags':dict(classes),'call_rows':rows,
            'program_status_counts':dict(status),'program_error_types':dict(errors),
            'program_errors_after_api_dispatch':after_effect,
            'flag_counts_overlap':True,
            'error_type_scope':'Exception name only; no raw message, credentials, code or arguments.'}


def analyze(storage,root):
    plan=read(root/'configs/P27_code_comparison_v01.json');require_complete(storage,plan)
    destination=root/'reports/P27_program_diagnostics.json'
    if destination.exists():raise FileExistsError('preserve completed diagnostics')
    rows=[]
    for task,arm,rid in plan['run_order']:
        t=storage/'records/context_pilot'/rid
        usage,events,spans=[read(t/n) for n in ('usage.json','events.json','spans.json')]
        programs={}
        for p in sorted((t/'programs').glob('*/result_private.json')):
            programs.setdefault(p.parent.name.rsplit('_',1)[0],[]).append(read(p))
        r=classify(usage,events,spans,programs);r['run_id']=rid
        r['source_sha256']={n:sha(t/n) for n in ('usage.json','events.json','spans.json')}
        r['program_result_sha256']={str(p.relative_to(t)):sha(p) for p in sorted((t/'programs').glob('*/result_private.json'))}
        rows.append(r)
    data={'phase':'P27','all_four_reviewed':True,'trials':rows,
          'model_calls_added':0,'api_requests_added':0,'evaluator_contents_read':False,
          'causal_interpretation':False,'script_sha256':sha(Path(__file__))}
    destination.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'run_id':r['run_id'],'flags':r['call_flags'],
                       'program_error_types':r['program_error_types']} for r in rows]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args();analyze(a.storage_root,a.repo_root)

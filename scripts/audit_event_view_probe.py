"""Recompute a terminal P16 run without inference, environment or evaluator access."""
import argparse
import hashlib
import json
from pathlib import Path

from context_preservation import LEDGER_TOOL
from local_llama import parse_response, payload_for
from run_event_view_probe import messages_for, schedule, structural_outcome

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def audit(run, inputs):
    state, plan, manifest = [read(run/name) for name in ('status.json','plan.json','input_manifest.json')]
    if state['status'] in ('preflight', 'running'):
        raise ValueError('audit only a terminal run')
    frozen, provenance = read(run/'freeze_record.json'), read(run/'provenance.json')
    errors=[]

    def check(condition, label):
        if not condition:
            errors.append(label)

    check(sha(run/'source/configs/P16_event_view_probe_v01.json') == frozen['plan_sha256'], 'plan hash')
    # The saved plan is reserialized. Compare logical content with the pinned source too.
    check(plan == read(run/'source/configs/P16_event_view_probe_v01.json'), 'plan content')
    check(sha(inputs/'manifest.json') == frozen['input_manifest_sha256'], 'input manifest hash')
    check(manifest == read(inputs/'manifest.json'), 'saved input manifest')
    for path, expected in frozen['source_hashes'].items():
        check(sha(run/'source'/path) == expected, 'archived source '+path)
    for name in ('scripts/run_event_view_probe.py','scripts/execution_event_views.py',
                 'scripts/native_ledger_memory.py','scripts/context_preservation.py','scripts/local_llama.py'):
        check(sha(ROOT/name) == frozen['source_hashes'][name], 'audit helper '+name)
    cases={}
    for row in manifest['cases']:
        path=inputs/(row['case_id']+'.json')
        check(sha(path) == row['case_sha256'], 'case hash '+row['case_id'])
        cases[row['case_id']]=read(path)
    order=schedule(plan,manifest)
    check(order == read(run/'schedule.json'), 'fixed schedule')
    counts=read(run/'input_counts.json') if (run/'input_counts.json').exists() else []
    usages=read(run/'usage.json') if (run/'usage.json').exists() else []
    results=read(run/'results.json')
    config=provenance['config']
    rows=[]
    for index,usage in enumerate(usages):
        if index >= len(order):
            errors.append('extra model call');break
        item=order[index]
        call=run/usage['id']
        request,response=read(call/'request.json'),read(call/'response.json')
        cfg=dict(config['model'],seed=item['seed'],temperature=plan['temperature'],num_predict=plan['max_output_tokens'])
        case=cases[item['case_id']]
        expected=payload_for(cfg,messages_for(case,item['variant'],config['observation_page_characters']),[LEDGER_TOOL])
        check(request == expected, usage['id']+' prepared request differs')
        for key in ('status','input_tokens','output_tokens'):
            check(usage[key] == response[key], usage['id']+' usage '+key)
        check(index<len(counts) and usage['predicted_input_tokens']==counts[index]['input_tokens'], usage['id']+' input preflight')
        known=response['status']=='ok'
        if known:
            raw=parse_response(read(call/'raw_response.json'))
            check(all(raw[k]==response[k] for k in raw), usage['id']+' terminal response')
            check(usage['input_tokens']==usage['predicted_input_tokens'], usage['id']+' counted input')
            outcome,ledger=structural_outcome(response['message'],case)
            check(index<len(results),usage['id']+' missing result')
            if index<len(results):
                r=results[index]
                check(all(r[k]==item[k] for k in item),usage['id']+' schedule result')
                check(all(r[k]==v for k,v in outcome.items()),usage['id']+' outcome mismatch')
                check(r['request_sha256']==sha(call/'request.json') and r['response_sha256']==sha(call/'response.json'),usage['id']+' result hashes')
                check(r['known_tokens']==usage['input_tokens']+usage['output_tokens'],usage['id']+' result tokens')
            if ledger is not None:
                check(ledger==read(call/'ledger_private.json'),usage['id']+' parsed ledger')
        else:
            check(usage['input_tokens'] is None and usage['output_tokens'] is None,usage['id']+' unknown usage must stay null')
            check(index==len(usages)-1,usage['id']+' continued after unknown usage')
            outcome={'schema_valid':None,'done_items':None,'items':None,'done_only_rejected_sources':None}
        rows.append({**item,'condition':case['condition'],'call_id':usage['id'],
                     'status':usage['status'],'input_tokens':usage['input_tokens'],'output_tokens':usage['output_tokens'],
                     'wall_seconds':usage['wall_seconds'],**outcome,
                     'prepared_request_digest':digest(request),
                     'public_answer_digest':digest({k:v for k,v in response['message'].items()
                                                    if k!='reasoning_content'}) if known else None,
                     'request_sha256':sha(call/'request.json'),'response_sha256':sha(call/'response.json')})
    known_tokens=sum(r['input_tokens']+r['output_tokens'] for r in rows if r['status']=='ok')
    unknown=sum(r['status']!='ok' for r in rows)
    check(state['model_calls']==len(usages),'status call count')
    check(state['completed_outputs']==len(results),'status output count')
    check(state['known_total_tokens']==known_tokens,'status token count')
    check(state['unknown_usage_calls']==unknown,'status unknown count')
    if state['status']=='complete':
        check(len(rows)==plan['max_calls'] and unknown==0,'complete run size')
    controls=[]
    for c in manifest['cases']:
        if c['condition']!='recorded':continue
        group=[r for r in rows if r['case_id']==c['case_id']]
        controls.append({'case_id':c['case_id'],'observed_outputs':len(group),
                         'unique_prepared_requests':len({r['prepared_request_digest'] for r in group}),
                         'unique_public_answers':len({r['public_answer_digest'] for r in group if r['status']=='ok'})})
        check(len({r['prepared_request_digest'] for r in group})<=1,'unchanged control input '+c['case_id'])
    grouped=[]
    for condition in plan['conditions']:
        for variant in plan['variants']:
            group=[r for r in rows if r['condition']==condition and r['variant']==variant]
            grouped.append({'condition':condition,'variant':variant,'calls':len(group),
                            'schema_valid':sum(r['schema_valid'] is True for r in group),
                            'known_tokens':sum(r['input_tokens']+r['output_tokens'] for r in group if r['status']=='ok'),
                            'unknown_usage_calls':sum(r['status']!='ok' for r in group)})
    return {'run_id':plan['run_id'],'status':state['status'],'audit_errors':errors,
            'calls':len(usages),'known_total_tokens':known_tokens,'unknown_usage_calls':unknown,
            'wall_seconds':state['wall_seconds'],'rows':rows,'groups':grouped,'unchanged_controls':controls,
            'source_hashes':{name:sha(run/name) for name in ('status.json','plan.json','provenance.json','results.json','freeze_record.json')},
            'auditor_sha256':sha(Path(__file__)), 'additional_model_calls':0,'environment_requests':0,
            'evaluation_files_read':False,'semantic_review_complete':False,
            'scope':'Structural and cost audit. Rejected-only done citations are warnings, not semantic error labels. Four development tasks; controlled rejection, no natural incidence or end-to-end success.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=audit(args.run,args.inputs)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','calls','known_total_tokens','unknown_usage_calls','audit_errors')}))
    return bool(result['audit_errors'])


if __name__=='__main__':
    raise SystemExit(main())

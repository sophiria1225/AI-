"""Check usage, budgets, snapshots and frozen artifacts for the completed P1 batch."""
import hashlib
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
rows=[]
errors=[]
for run in sorted((ROOT/'records/p1').glob('*')):
    if not (run/'summary.json').exists():
        continue
    summary=json.loads((run/'summary.json').read_text())
    config=json.loads((run/'config.json').read_text())
    local=[]
    counts={'input_tokens':0,'output_tokens':0,'cached_input_tokens':0}
    cache_complete=True
    terminal_count=0
    truncations=0
    for call in summary['calls']:
        events=[json.loads(line) for line in (run/call['path']/'events.jsonl').read_text().splitlines()]
        terminals=[e for e in events if e.get('done')]
        if len(terminals)!=1:
            local.append('missing/duplicate terminal: '+call['path'])
            continue
        event=terminals[0]
        terminal_count+=1
        truncations+=event.get('done_reason')=='length'
        for src,dest in [('prompt_eval_count','input_tokens'),('eval_count','output_tokens')]:
            if event.get(src)!=call.get(dest):
                local.append('usage mismatch: '+call['path'])
            counts[dest]+=event.get(src,0)
        if call['input_tokens']>call['precall_input_bound']:
            local.append('input bound underestimated: '+call['path'])
        if call['input_tokens']+call['output_tokens']>config['num_ctx']:
            local.append('context window exceeded: '+call['path'])
        cache=event.get('prompt_eval_cached_count')
        if cache is None:
            cache_complete=False
        elif not 0<=cache<=event['prompt_eval_count']:
            local.append('invalid cache accounting')
        else:
            counts['cached_input_tokens']+=cache
        request=json.loads((run/call['path']/'request.json').read_text())
        if request['model']!=config['model'] or request['think']!=config['think']:
            local.append('request setting mismatch')
    total=counts['input_tokens']+counts['output_tokens']
    if total!=summary.get('total_recorded_tokens'):
        local.append('total token mismatch')
    for name,digest in summary['source_hashes'].items():
        if hashlib.sha256((run/name).read_bytes()).hexdigest()!=digest:
            local.append('source snapshot mismatch: '+name)
    if not summary.get('artifact_frozen_at'):
        local.append('artifact not frozen')
    elif hashlib.sha256((run/'final.patch').read_bytes()).hexdigest()!=summary['artifact_sha256']:
        local.append('artifact hash mismatch')
    if total>config['max_total_tokens'] or len(summary['calls'])>config['max_calls']:
        local.append('budget exceeded')
    eval_path=run/'final_evaluation_summary.json'
    evaluated=json.loads(eval_path.read_text()) if eval_path.exists() else None
    if evaluated and evaluated['artifact_sha256']!=summary['artifact_sha256']:
        local.append('evaluation artifact mismatch')
    artifact_manifest=json.loads((run/'artifact_manifest.json').read_text()) if (run/'artifact_manifest.json').exists() else {}
    tool_nonzero=sum(t.get('exit_code') not in [0,None] for t in summary['tools'])
    rows.append({'run_id':run.name,'model':config['model'],'task':config['instance_id'],
        'calls':len(summary['calls']),'tools':len(summary['tools']),'tool_nonzero':tool_nonzero,
        'usage':counts,'total_tokens':total,'cache_complete':cache_complete,
        'usage_complete':summary['usage_complete'] and terminal_count==len(summary['calls']),
        'generation_truncations':truncations,'stop_reason':summary['stop_reason'],
        'wall_seconds':summary['wall_seconds'],'artifact_bytes':summary.get('artifact_bytes'),
        'excluded_files':artifact_manifest.get('excluded',[]),'evaluation':evaluated,'errors':local})
    errors.extend(run.name+': '+e for e in local)
probes=[]
for batch in sorted((ROOT/'records/p1_model_probes').glob('*')):
    if (batch/'summary.json').exists():
        for item in json.loads((batch/'summary.json').read_text()):
            child=ROOT/item['path']
            summary=json.loads((child/'summary.json').read_text())
            actual=0
            for call in summary['calls']:
                terminal=[json.loads(line) for line in (child/call['path']/'events.jsonl').read_text().splitlines() if json.loads(line).get('done')][-1]
                actual+=terminal['prompt_eval_count']+terminal['eval_count']
            if actual!=item['tokens']:
                errors.append('probe token mismatch: '+item['path'])
            probes.append(item)
total_run_tokens=sum(r['total_tokens'] for r in rows)
total_probe_tokens=sum(p['tokens'] for p in probes)
result={'runs':rows,'probes':probes,'all_usage_complete':all(r['usage_complete'] for r in rows),
    'task_calls':sum(r['calls'] for r in rows),'task_tokens':total_run_tokens,
    'probe_calls':sum(p['calls'] for p in probes),'probe_tokens':total_probe_tokens,
    'total_recorded_P1_tokens':total_run_tokens+total_probe_tokens,'errors':errors}
(ROOT/'records/p1_audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(1 if errors else 0)

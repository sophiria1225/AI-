"""Fixed-cohort post-hoc counts; never emit generated code or argument values."""
import argparse
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from analyze_code_comparison import require_complete
from diagnose_p25_public_traces import sent_rows
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def analyze(storage,root):
    plan=read(root/'configs/P27_code_comparison_v01.json');require_complete(storage,plan)
    rows=[]
    for task,arm,rid in plan['run_order']:
        t=storage/'records/context_pilot'/rid;events=read(t/'events.json');spans=read(t/'spans.json')
        groups=defaultdict(list)
        for x in sent_rows(spans,events):groups[x['name']].append(x)
        stats={name:dict(requests=len(rs),distinct_exact_arguments=len({json.dumps(r['args'],sort_keys=True) for r in rs}))
               for name,rs in groups.items()}
        programs=[];hashes={}
        for p in sorted((t/'programs').glob('*/input_private.json')):
            x=read(p);q=p.parent/'result_private.json';r=read(q);tree=ast.parse(x['code'])
            hashes[str(p.relative_to(t))]=sha(p);hashes[str(q.relative_to(t))]=sha(q)
            programs.append(dict(id=p.parent.name,selected_prior_receipts=len(x['observations']),
                has_subprocess_import=any(isinstance(n,ast.Import) and any(a.name=='subprocess' for a in n.names) for n in ast.walk(tree)),api_requests=r['api_requests']))
        rows.append(dict(run_id=rid,programs=len(programs),
            programs_selecting_prior_receipts=sum(p['selected_prior_receipts']>0 for p in programs),
            programs_importing_subprocess=sum(p['has_subprocess_import'] for p in programs),
            first_program_with_api_dispatch=next((i+1 for i,p in enumerate(programs) if p['api_requests']),None),
            request_counts=stats,source_sha256={n:sha(t/n) for n in ('events.json','spans.json')},program_sha256=hashes))
    result=dict(all_four_reviewed=True,trials=rows,model_calls_added=0,api_requests_added=0,
        scope='Post-hoc structural counts. Exact request repetition is not automatically redundant or safe to cache. No source/code/argument values are published.',script_sha256=sha(Path(__file__)))
    (root/'reports/P27_program_structure.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(run_id=r['run_id'],first_program_with_api_dispatch=r['first_program_with_api_dispatch']) for r in rows]))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',required=True,type=Path);p.add_argument('--repo-root',type=Path,default=ROOT)
    a=p.parse_args();analyze(a.storage_root,a.repo_root)

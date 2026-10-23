"""P77: bounded posthoc read of all eight closed P76 public execution paths."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import time

from public_path_scope import inspect_cell, cost

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P77_public_path_scope_v01.json'
REPORT = 'reports/P77_public_path_scope.json'
ZERO = ('model_generations','tokenizer_requests','environment_api_requests','evaluator_calls',
        'task_databases_read','reserved_scenarios_read','saved_code_executions','private_reasoning_text_inspected')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())


def validate_ci(ci, actual):
    if (len(ci) != 2 or {r['event'] for r in ci} != {'push','pull_request'}
            or any(r['head_sha'] != actual or r['job_head_sha'] != actual
                   or r['status'] != 'completed' or r['conclusion'] != 'success'
                   or r['job_name'] != 'accounting-and-syntax' or r['job_conclusion'] != 'success'
                   or type(r['id']) is not int or type(r['job_id']) is not int for r in ci)):
        raise ValueError('both_exact_commit_workflows_and_jobs_required')


def run(storage, expected_sha, ci_path):
    output = ROOT / REPORT
    if output.exists(): raise FileExistsError('preserve_every_P77_attempt')
    started = time.monotonic()
    result = {'phase':'P77','status':'stopped','rows':[],**{k:0 for k in ZERO},
              'all_eight_accounted':False,'runtime_rewriting':False,'novel_method_claim':False,
              'measured_savings':None,'safe_omission_verified':False}
    def expired(*_): raise TimeoutError('bounded_read_deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL,120)
    try:
        actual = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        if not re.fullmatch('[a-f0-9]{40}',expected_sha) or actual != expected_sha:
            raise ValueError('fixed_commit_changed')
        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
            raise ValueError('worktree_not_clean')
        ci=read(ci_path);validate_ci(ci,actual)
        plan=read(ROOT/PLAN)
        if (plan['phase'] != 'P77' or [plan[k] for k in ('cells','model_calls','programs','max_wall_seconds','max_file_bytes',
                                                       'max_source_characters','max_ast_nodes')]
                != [8,43,40,120,4194304,20000,5000] or any(plan[k] != 0 for k in ZERO)
                or plan['runtime_rewriting'] or plan['measured_savings'] is not None):
            raise ValueError('fixed_population_or_scope_changed')
        if set(plan['source_sha256']) != {'reports/P76_comparison.json','reports/P76_server_session.json','scripts/inspect_terminal_cost_scope.py'}:
            raise ValueError('fixed_source_set_changed')
        for name,digest in plan['source_sha256'].items():
            if sha(ROOT/name) != digest: raise ValueError('source_hash_changed')
        audit=read(ROOT/'reports/P76_comparison.json'); session=read(ROOT/'reports/P76_server_session.json')
        if (audit['audit_errors'] or audit['batch_status']!='complete' or len(audit['rows'])!=8
                or session['status']!='stopped' or not session['owned_processes_absent']
                or session['audit_source_sha256'] != sha(ROOT/'reports/P76_comparison.json')):
            raise ValueError('closed_audited_population_required')
        result.update(git_commit=actual,ci=ci,plan_sha256=sha(ROOT/PLAN),source_sha256=plan['source_sha256'],
                      implementation_sha256={name:sha(ROOT/name) for name in (
                          'scripts/public_path_scope.py','scripts/inspect_public_path_scope.py',
                          'tests/test_public_path_scope.py','docs/experiments/P77_public_path_scope.md')},
                      private_record_sha256={})
        all_calls=[]
        for row in audit['rows']:
            if not re.fullmatch(r'P76_0[1-4]_(PUBLIC_ONLY|REASONING_KEEP)',row['run_id']):
                raise ValueError('outside_fixed_cells')
            folder=storage/'records/context_pilot'/row['run_id']
            folder.resolve().relative_to(storage.resolve())
            values=[]; hashes={}
            for name in ('events.json','spans.json','usage.json'):
                path=folder/name
                if path.stat().st_size > plan['max_file_bytes'] or sha(path) != row['source_sha256'][name]:
                    raise ValueError('audited_public_record_hash_or_size_changed')
                hashes[name]=sha(path);values.append(read(path))
            result['private_record_sha256'][row['run_id']]=hashes
            inspected=inspect_cell(*values,row);result['rows'].append(inspected);all_calls.extend(inspected['calls'])
        result.update(total=cost(all_calls),programs=sum(len(r['programs']) for r in result['rows']))
        if (result['total']['model_calls']!=43 or result['programs']!=40
                or result['total']['known_total_tokens']!=588495 or result['total']['unknown_usage_calls']!=2
                or result['total']['sent_api_requests']!=306):
            raise ValueError('all_condition_totals_disagree')
        result.update(status='complete',all_eight_accounted=True)
    except Exception as exc:
        result.update(stop_type=type(exc).__name__,stop_reason=str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        result['wall_seconds']=time.monotonic()-started
        with output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('status','all_eight_accounted','wall_seconds')},ensure_ascii=False))
    return result['status']=='complete'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--expected-sha',required=True)
    p.add_argument('--ci-evidence',type=Path,required=True)
    args=p.parse_args()
    raise SystemExit(0 if run(args.storage_root.resolve(),args.expected_sha,args.ci_evidence.resolve()) else 1)

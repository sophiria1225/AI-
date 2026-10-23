"""Read the fixed P70 inputs once; keep partial results on any batch stop."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import signal
import subprocess
import time

from boundary_lifetime_scope import analyze
from inspect_return_use_scope import validate as validate_source, read, sha, write

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P74_boundary_lifetime_v01.json'
REPORT = 'reports/P74_boundary_lifetime_scope.json'
ZERO_KEYS = ('model_generations', 'environment_api_requests', 'evaluator_calls',
             'task_databases_read', 'reserved_scenarios_read', 'saved_code_executions')


def validate(plan):
    if (plan['phase'] != 'P74' or plan['source_plan'] != 'configs/P70_return_use_scope_v01.json'
            or [plan[k] for k in ('known_tasks','cells','program_occurrences','unique_input_files',
                                  'max_wall_seconds','max_file_bytes','max_source_characters','max_ast_nodes')]
               != [4,12,181,117,120,4194304,20000,5000]
            or any(plan[k] != 0 for k in ZERO_KEYS)
            or plan['runtime_rewriting'] or plan['online_equivalence_verified'] or plan['measured_savings'] is not None):
        raise ValueError('fixed_population_or_scope_changed')
    expected_sources = {'configs/P70_return_use_scope_v01.json','reports/P35_read_footprint.json',
        'reports/P70_return_use_scope.json','scripts/return_use_scope.py','scripts/inspect_return_use_scope.py',
        'scripts/field_read_contract.py'}
    if set(plan['source_sha256']) != expected_sources:
        raise ValueError('fixed_source_set_changed')
    for path, expected in plan['source_sha256'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('fixed_source_hash_changed')
    source = read(ROOT / plan['source_plan'])
    validate_source(source, read(ROOT / 'reports/P35_read_footprint.json'))
    old = read(ROOT / 'reports/P70_return_use_scope.json')
    if (len(old['rows']) != 12 or old['program_occurrences'] != 181 or old['unique_input_files'] != 117
            or old['plan_sha256'] != sha(ROOT / plan['source_plan'])):
        raise ValueError('previous_inventory_changed')
    return source, old


def run(storage, expected_sha, ci_path):
    output = ROOT / REPORT
    if output.exists():
        raise FileExistsError('preserve_existing_P74_result')
    started = time.monotonic()
    result = {'phase':'P74', 'status':'stopped', 'planned_program_occurrences':181,
              'programs':[], 'rows':[], **{k:0 for k in ZERO_KEYS},
              'runtime_rewriting':False, 'online_equivalence_verified':False,
              'novel_method_claim':False, 'measured_savings':None}
    def timed_out(*_):
        raise TimeoutError('read_only_deadline')
    previous = signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        actual = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        if not re.fullmatch(r'[0-9a-f]{40}',expected_sha) or actual != expected_sha:
            raise ValueError('fixed_commit_changed')
        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
            raise ValueError('worktree_not_clean_before_read')
        ci = read(ci_path)
        if (len(ci) != 2 or {r['event'] for r in ci} != {'push','pull_request'}
                or any(r['head_sha'] != actual or r['status'] != 'completed' or r['conclusion'] != 'success'
                       or r['job_name'] != 'accounting-and-syntax' or r['job_conclusion'] != 'success'
                       or r['job_head_sha'] != actual
                       or not isinstance(r['id'],int) or not isinstance(r['job_id'],int) for r in ci)):
            raise ValueError('both_exact_commit_workflows_and_jobs_required')
        plan = read(ROOT / PLAN);source, old = validate(plan)
        result.update(git_commit=actual,ci=ci,plan_sha256=sha(ROOT/PLAN),source_sha256=plan['source_sha256'],
            protocol_sha256=sha(ROOT/'docs/experiments/P74_boundary_lifetime_scope.md'),
            implementation_sha256={p:sha(ROOT/p) for p in (
                'scripts/boundary_lifetime_scope.py','scripts/inspect_boundary_lifetime_scope.py',
                'tests/test_boundary_lifetime_scope.py')})
        result['planned_inputs'] = [{'run_id':row['run_id'],**item} for row in source['rows'] for item in row['inputs']]
        inputs = {}
        for item in result['planned_inputs']:
            path = storage / item['path'];path.resolve().relative_to(storage.resolve())
            if path.stat().st_size > plan['max_file_bytes'] or sha(path) != item['sha256']:
                raise ValueError('original_input_hash_or_size_changed')
            inputs[item['path']] = path
        if len(inputs) != 117:
            raise ValueError('unique_input_population_changed')
        for row, prior in zip(source['rows'],old['rows'],strict=True):
            programs=[]
            for item, prior_program in zip(row['inputs'],prior['programs'],strict=True):
                packet=read(inputs[item['path']])
                if packet['program_index'] != item['program_index']:
                    raise ValueError('program_index_changed')
                record={k:item[k] for k in ('program','phase','program_index','sha256')}
                record.update(run_id=row['run_id'],status='analysis_started')
                result['programs'].append(record)
                try:
                    analysis=analyze(packet['code'])
                except ValueError as exc:
                    record.update(status='unsupported',reason=str(exc))
                else:
                    expected=prior_program['analysis']
                    if (analysis['source_sha256'] != expected['source_sha256']
                            or analysis['counts']['all_call_api_syntax_sites'] != expected['call_api_syntax_sites']
                            or analysis['counts']['root_name_binding_sites'] != expected['use_counts'].get('name_binding',0)):
                        raise ValueError('old_syntax_inventory_disagrees')
                    record.update(status='analyzed',analysis=analysis)
                programs.append(record)
            counts=Counter()
            for record in programs:
                if record['phase'] != 'control':counts.update(record.get('analysis',{}).get('counts',{}))
            result['rows'].append({k:row[k] for k in ('run_id','task_id','arm')} | {
                'program_occurrences':len(programs),'unsupported_programs':sum(r['status']=='unsupported' for r in programs),
                'control_programs':sum(r['phase']=='control' for r in programs),'counts':dict(sorted(counts.items()))})
        result['unique_input_files']=len(inputs)
        result['totals']=dict(sum((Counter(row['counts']) for row in result['rows']),Counter()))
        result['status']='complete'
    except Exception as exc:
        result['error_type']=type(exc).__name__
        # Parser/validation errors are controlled labels; raw saved input is never printed.
        result['error_reason']=str(exc) if isinstance(exc,(ValueError,TimeoutError)) else 'inspect_local_exception_type'
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        done={(r['run_id'],r['program']) for r in result['programs'] if r['status'] in ('analyzed','unsupported')}
        result['unprocessed_inputs']=[{'run_id':r['run_id'],'program':r['program']} for r in result.get('planned_inputs',[])
                                      if (r['run_id'],r['program']) not in done]
        result['wall_seconds']=time.monotonic()-started
        result['accounted_program_occurrences']=len(done)
        write(output,result)
    print(json.dumps({k:result[k] for k in ('status','accounted_program_occurrences','unique_input_files','totals','wall_seconds')}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--expected-sha',required=True);p.add_argument('--ci-evidence',type=Path,required=True)
    args=p.parse_args();run(args.storage_root.resolve(),args.expected_sha,args.ci_evidence.resolve())

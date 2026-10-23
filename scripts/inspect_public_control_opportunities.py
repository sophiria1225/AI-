"""Read closed public aggregates before extending recovery or reuse controls."""
import json
from pathlib import Path
import time

from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json


def inspect(root=ROOT):
    started = time.monotonic()
    target = root / 'reports/P78_public_control_opportunities.json'
    if target.exists(): raise FileExistsError('preserve_existing_opportunity_inspection')
    source = 'reports/P78_call_profile.json'
    closed = read(root / 'reports/P78_results_provenance_20261023.json')
    if sha(root / source) != closed['source_sha256'][source]:
        raise ValueError('closed_P78_profile_changed')
    profile = read(root / source)
    comparison = read(root / 'reports/P78_comparison.json')
    if profile['comparison_sha256'] != sha(root / 'reports/P78_comparison.json'):
        raise ValueError('profile_comparison_identity_mismatch')
    calls, programs = profile['calls'], profile['programs']
    keys = [(r['run_id'], r['call_id']) for r in calls]
    if (len(calls) != 137 or len(programs) != 137 or len(set(keys)) != len(keys)
            or not profile['all_planned_rows_accounted']
            or not comparison['all_eight_complete_with_known_usage']
            or any(c['usage_status'] != 'ok' for c in calls)):
        raise ValueError('closed_complete_P78_profile_required')
    grouped = {key: [p for p in programs if (p['run_id'], p['call_id']) == key] for key in keys}
    if any(len(v) != 1 for v in grouped.values()):
        raise ValueError('one_public_program_per_call_required_for_this_inspection')
    if any(grouped[key][0]['api_requests'] != call['api_requests'] for key, call in zip(keys, calls, strict=True)):
        raise ValueError('call_program_request_counts_disagree')
    failures = [{**{k: c[k] for k in ('run_id','call_id','api_requests','api_invocation_exceptions','python_execution_errors')},
        'program': {k: grouped[(c['run_id'],c['call_id'])][0][k]
                    for k in ('span_id','status','api_requests','exception_type')}}
        for c in calls if c['api_invocation_exceptions']]
    zero_api = [{k: c[k] for k in ('run_id','call_id','known_total_tokens','python_execution_errors')}
                for c in calls if c['api_requests'] == 0]
    if len(failures) != 9 or len(zero_api) != 11:
        raise ValueError('published_cohort_counts_changed')
    result = {'phase':'P78_public_control_opportunity_inspection','profile_calls':len(calls),
        'profile_programs':len(programs),'invocation_exception_calls':failures,
        'all_exception_calls_have_exactly_one_sent_API':all(c['api_requests']==1 and c['api_invocation_exceptions']==1 for c in failures),
        'same_exception_programs_with_earlier_successful_sent_API':sum(c['api_requests']>1 for c in failures),
        'local_assignments_before_exception_or_side_effects_excluded':False,
        'zero_sent_API_calls':zero_api,'zero_sent_API_call_known_tokens':sum(c['known_total_tokens'] for c in zero_api),
        'zero_sent_API_calls_with_python_error':sum(c['python_execution_errors']>0 for c in zero_api),
        'zero_sent_API_is_unnecessary_work':False,'measured_avoidable_tokens':None,
        'model_calls':0,'environment_api_requests':0,'evaluations':0,'private_traces_read':0,
        'generated_programs_executed':0,'reserved_scenarios_read':0,
        'novel_method_claim':False,'source_sha256':{p:sha(root/p) for p in (
            source,'reports/P78_comparison.json','reports/P78_results_provenance_20261023.json')},
        'script_sha256':sha(Path(__file__)),'wall_seconds':time.monotonic()-started}
    write_json(target,result)
    print({k:result[k] for k in ('profile_calls','profile_programs','all_exception_calls_have_exactly_one_sent_API',
        'same_exception_programs_with_earlier_successful_sent_API','zero_sent_API_call_known_tokens','wall_seconds')})


if __name__ == '__main__':
    inspect()

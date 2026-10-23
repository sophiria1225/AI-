"""Read all closed P80 records to locate the fixed half-deadline transition.

These are observed opportunities, not counterfactual outcomes or savings.
"""
import argparse
from pathlib import Path

from build_budget_visibility_report import validated
from compare_budget_visibility_repetitions import trace
from late_time_observation import effective_visibility
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def run(storage):
    target=ROOT/'reports/late_clock_feasibility_20261024.json'
    if target.exists():raise FileExistsError('preserve_first_transition_feasibility')
    plan,report,_,_=validated()
    rows=[]
    for row in report['rows']:
        t=trace(storage,row)
        folder=storage/'records/context_pilot'/row['run_id']
        notices=[v for v in read(folder/'budget_observations.json') if v['model_attempted']]
        if sha(folder/'usage.json')!=row['usage_sha256']:
            raise ValueError('audited_usage_changed')
        usage=read(folder/'usage.json')
        ids=[v['next_call_id'] for v in notices]
        if ids!=[v['call_id'] for v in t['calls']] or ids!=[v['id'] for v in usage]:
            raise ValueError('all_attempts_must_correspond')
        candidates=[i for i,v in enumerate(notices) if effective_visibility(
            'late_half',v['measured_state'],plan['max_wall_seconds'])=='measured']
        first=candidates[0] if candidates else None
        prefix=usage[:first] if first is not None else usage
        rows.append({'run_id':row['run_id'],'original_policy':row['time_visibility'],
            'model_calls':len(usage),'first_transition_call':ids[first] if first is not None else None,
            'remaining_seconds_at_transition':notices[first]['measured_state']['remaining']['wall_seconds_at_snapshot'] if first is not None else None,
            'attempts_at_or_after_transition':len(candidates),
            'known_tokens_before_transition_or_end':sum(v['input_tokens']+v['output_tokens'] for v in prefix if v['status']=='ok'),
            'unknown_usage_before_transition_or_end':sum(v['status']!='ok' for v in prefix),
            'private_notice_sha256':t['notices_sha256'],'private_usage_sha256':row['usage_sha256']})
    result={'phase':'late_clock_feasibility','source_cohort':'P80_all_eight','rows':rows,
        'wall_limit_seconds':plan['max_wall_seconds'],'remaining_fraction':[1,2],
        'development_choice_after_P80_and_partial_P81':True,
        'additional_generations':0,'additional_api_calls':0,'additional_evaluations':0,
        'counterfactual_trajectories_executed':False,'counterfactual_cost_measured':False,
        'novel_method_claim':False,'private_reasoning_inspected_semantically':False,
        'source_sha256':{name:sha(ROOT/name) for name in (
            'reports/P80_comparison.json','reports/P80_server_session.json',
            'configs/P80_budget_visibility_v01.json','scripts/late_time_observation.py',
            'scripts/compare_budget_visibility_repetitions.py')},
        'inspector_sha256':sha(Path(__file__)),
        'interpretation':'Read-only transition opportunities in existing traces. A new notification can change all subsequent behavior; retained prefixes are not measured savings.'}
    write_json(target,result)
    print({'rows':len(rows),'observed_traces_with_transition':sum(v['first_transition_call'] is not None for v in rows)})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    run(p.parse_args().storage_root)

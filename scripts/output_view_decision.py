"""Apply the prespecified descriptive P33 gate after the whole cohort closes.

This is a development gate, not a significance/non-inferiority test, or permission
to run reserved tasks. Success identities matter, not just their aggregate count.
"""
import argparse
import hashlib
import json
from pathlib import Path

from diagnose_handoff_programs import require_complete
from handoff_output_views import ARMS


def assess(report,status):
    require_complete(report,status,'P33')
    rows=report['rows'];by_task={t:{} for t in {r['task_id'] for r in rows}}
    for r in rows:
        if type(r['success']) is not bool:raise ValueError('success must be a measured boolean')
        for name in ('known_total_tokens','unknown_usage_calls'):
            if type(r[name]) is not int or r[name]<0:raise ValueError('invalid cost count')
        by_task[r['task_id']][r['arm']]=r
    totals={a:{'known_total_tokens':sum(r['known_total_tokens'] for r in rows if r['arm']==a),
               'unknown_usage_calls':sum(r['unknown_usage_calls'] for r in rows if r['arm']==a),
               'successes':sum(r['success'] for r in rows if r['arm']==a)} for a in ARMS}
    base=totals['full_keep'];decisions={}
    for arm in ARMS[1:]:
        lost=sorted(t for t,rs in by_task.items() if rs['full_keep']['success'] and not rs[arm]['success'])
        gained=sorted(t for t,rs in by_task.items() if not rs['full_keep']['success'] and rs[arm]['success'])
        known=totals[arm]['unknown_usage_calls']==base['unknown_usage_calls']==0
        change=totals[arm]['known_total_tokens']-base['known_total_tokens'] if known else None
        passed=not lost and known and change<0
        decisions[arm]={'baseline_successes_lost':lost,'new_successes':gained,
            'all_usage_known_in_pair':known,'total_token_change':change,
            'token_change_fraction':change/base['known_total_tokens'] if known and base['known_total_tokens'] else None,
            'prespecified_descriptive_gate_passed':passed,
            'baseline_success_count':base['successes'],
            'quality_preservation_established':False,'novelty_established':False,
            'heldout_evaluation_authorized_by_gate':False}
    return {'phase':'P33','independent_tasks':4,'repetitions_per_cell':1,
            'rule':'No baseline-success task lost AND strictly lower total tokens AND no unknown usage in either arm.',
            'totals':totals,'decisions':decisions,
            'limits':['A gate pass is a descriptive result on known development tasks, not generalization or non-inferiority.',
                      'Unknown usage does not become zero and cannot support an exact savings fraction.',
                      'The gate cannot establish novelty or select a new experiment automatically.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--storage-root',type=Path,required=True);a=p.parse_args()
    source=a.repo_root/'reports/P33_comparison.json'
    status=a.storage_root/'records/context_pilot/P33_batch_v01/status.json'
    target=a.repo_root/'reports/P33_development_gate.json'
    if target.exists():raise FileExistsError('preserve complete gate report')
    result=assess(json.loads(source.read_text()),json.loads(status.read_text()))
    result['source_sha256']={str(path.relative_to(a.repo_root)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source,Path(__file__),a.repo_root/'configs/P33_output_views_v01.json')}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['decisions']))

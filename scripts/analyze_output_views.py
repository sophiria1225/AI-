"""Close all twelve output-view cells; never select an arm from partial results."""
import argparse
from pathlib import Path

from analyze_handoff_factors import trial_row
from handoff_output_views import ARMS
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_output_views import frozen_hashes


def validate_cohort(status, expected):
    if (status.get('status')!='complete' or set(status.get('completed',[]))!=set(expected)
            or len(status.get('completed',[]))!=len(expected)
            or len(status.get('rows',[]))!=len(expected)
            or {r['run_id'] for r in status['rows']}!=set(expected)):
        raise ValueError('require the complete twelve-cell cohort')


def validate_first_view(trial, expected):
    usage=read(trial/'usage.json')
    if not usage:raise ValueError('no continuation request; retain as experiment error')
    actual=read(trial/usage[0]['id']/'request.json')['messages']
    if actual!=expected:raise ValueError('first input differs from preflight view')


def analyze(storage, root):
    plan=read(root/'configs/P33_output_views_v01.json')
    if plan['phase']!='P33' or plan['arms']!=list(ARMS):raise ValueError('plan differs')
    frozen=read(root/'reports/P33_activation_v01.json')
    if frozen['source_hashes']!=frozen_hashes(root):raise ValueError('frozen implementation changed')
    base=storage/'records/context_pilot'
    status=read(base/plan['batch_id']/'status.json')
    expected=[f'P33_{number:02d}_{arm.upper()}' for number in range(1,5) for arm in ARMS]
    validate_cohort(status,expected)
    source_plan=read(root/plan['source_plan']);rows=[]
    for number,source in enumerate(plan['source_runs'],1):
        task_rows=[]
        for arm in ARMS:
            rid=f'P33_{number:02d}_{arm.upper()}';trial=base/rid
            row=trial_row(trial,source_plan,source)
            if row['task_id']!=source_plan['task_ids'][number-1] or row['arm']!=arm:
                raise ValueError('cell identity differs')
            expected_path=base/'P33_preflight_v01'/f'P33_PREFIX_V01_{number:02d}'/(arm+'_private.json')
            validate_first_view(trial,read(expected_path))
            summary=read(trial/'summary.json');transfer=summary['transfer']
            if transfer['view_arm']!=arm or not transfer['runtime_retained']:
                raise ValueError('view/runtime condition differs')
            row.update(masked_span_count=transfer['masked_span_count'],
                       transfer_wall_seconds=transfer['transfer_wall_seconds'],
                       inventory_measurement=transfer.get('inventory_measurement'),
                       preflight_input_sha256=sha(expected_path))
            task_rows.append(row)
        if len({r['source_boundary_sha256'] for r in task_rows})!=1:
            raise ValueError('different source states within task')
        rows+=task_rows
    totals={}
    for arm in ARMS:
        cells=[r for r in rows if r['arm']==arm]
        totals[arm]={'trials':len(cells),'successes':sum(r['success'] for r in cells)}
        for key in ('known_total_tokens','unknown_usage_calls','model_calls','api_requests',
                    'setup_api_requests','setup_wall_seconds','continuation_wall_seconds',
                    'full_wall_seconds','transfer_wall_seconds','archive_read_calls','selected_prior_receipts'):
            totals[arm][key]=sum(r[key] for r in cells)
    return {'phase':'P33','all_twelve_reviewed':True,'audit_errors':[],
            'boundary_after_model_calls':8,'rows':rows,'totals':totals,
            'novel_method_claim':False,'quality_preservation_established':False,
            'limits':['Four known development tasks, one seed per cell; not held-out or independent task expansion.',
                'One-time masking of successful old stdout; commands, status, errors and latest turn retained.',
                'Boundary inventory describes availability only; not inferred relevance or current truth.',
                'Transfer work is charged to continuation; reconstruction is separately reported setup.',
                'Output masking and runtime inventory are ordinary comparators, not a new algorithm.'],
            'source_hashes':{n:sha(root/n) for n in ('configs/P33_output_views_v01.json',
                'reports/P33_prefix_checks.json','reports/P33_activation_v01.json')}}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT)
    p.add_argument('--phase',choices=('P33',),default='P33');a=p.parse_args()
    target=a.repo_root/'reports/P33_comparison.json'
    if target.exists():raise FileExistsError('preserve complete report')
    result=analyze(a.storage_root,a.repo_root);write_json(target,result)
    print(result['totals'])

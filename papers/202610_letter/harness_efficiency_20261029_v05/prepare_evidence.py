"""Derive paper scalars from already-public closed reports; no experiment execution."""
import argparse,hashlib,json
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def derive(root):
    bindings=json.loads((Path(__file__).parent/'evidence_sources.json').read_text())['source_sha256']
    for name,h in bindings.items():
        if sha(root/name)!=h:raise ValueError('source differs: '+name)
    a=json.loads((root/'reports/P123_comparison.json').read_text())
    assert a['planned_rows']==12 and not a['audit_errors'] and a['all_twelve_complete_with_known_usage'] is True
    tasks=['34d9492_1','3c13f5a_1','60d0b5b_1','6104387_1']
    modes=['single_checkpoint','rolling_separate','rolling_inline']
    actual=sorted(set(r['checkpoint_policy'] for r in a['rows']))
    assert set(actual)==set(modes),actual
    ar=[]
    for tid in tasks:
        for mode in modes:
            x,=[r for r in a['rows'] if r['task_id']==tid and r['checkpoint_policy']==mode]
            assert x['success'] is True and x['record_status']=='evaluated' and x['unknown_usage_calls']==0
            assert x['known_total_tokens']==x['input_tokens']+x['output_tokens']
            ar.append({k:x[k] for k in ['task_id','run_id','checkpoint_policy','success','known_total_tokens','input_tokens','output_tokens','cached_input_tokens','model_calls','api_requests','checkpoint_installations','unknown_usage_calls']})
    totals={m:sum(r['known_total_tokens'] for r in ar if r['checkpoint_policy']==m) for m in modes}
    assert totals==a['total_tokens_by_policy']==dict(zip(modes,[893529,785656,836922]))
    assert [ar[i]['known_total_tokens']-ar[i+1]['known_total_tokens'] for i in range(0,12,3)]==[0,0,0,107873]
    b=json.loads((root/'reports/P66_completion_audit.json').read_text())
    old=json.loads((root/'reports/P64_public_name_audit.json').read_text())
    assert not b['audit_errors'] and not old['audit_errors']
    br=[]
    for arm in ['documented','named']:
        new,=[r for r in b['rows'] if r['arm']==arm]
        ref=new['baseline_comparison']
        prev,=[r for r in old['rows'] if r['run_id']==ref['reference_run']]
        assert prev['official_success'] is new['official_success'] is True
        assert prev['known_total_tokens']==ref['reference_known_tokens']
        assert new['unknown_usage_calls']==prev['unknown_usage_calls']==0
        assert ref['changed_final_database_files']==[] and ref['same_prefix_events'] is True
        assert ref['same_entire_executed_model_prefix'] is False
        for label,x in [('ordinary',prev),('evidence_stop',new)]:
            assert x['known_total_tokens']==x['input_tokens']+x['output_tokens']
            br.append(dict(interface=arm,condition=label,**{k:x[k] for k in ['run_id','official_success','known_total_tokens','input_tokens','output_tokens','cached_input_tokens','model_calls','api_requests','unknown_usage_calls']}))
    assert [r['known_total_tokens'] for r in br]==[130439,91116,151664,112233]
    return {'scope':'separate closed studies; no pooled effect or independent replication claim','study_A':{'phase':'P123','known_tasks':4,'model_seed':57,'world_seed':42,'rows':ar,'totals':totals,'success_each':4,'rolling_savings':107873,'rolling_savings_pct':100*107873/893529,'inline_extra_vs_rolling':51266,'inline_extra_pct':100*51266/785656,'rolling_savings_all_from_CSV':True},'study_B':{'phase':'P64/P66','known_tasks':1,'interfaces':2,'seed_base':42,'rows':br,'paired_savings':[39323,39431],'paired_savings_pct':[100*39323/130439,100*39431/151664],'same_final_13_database_hashes':True,'strict_model_prefix_equal':False,'same_executed_API_prefix':True,'handwritten_requirement_template':True},'source_sha256':bindings,'all_logical_input_output_counted':True,'cached_input_deducted':False,'studies_pooled':False,'reserved_reads':0,'additional_experiment_calls':0}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    d=derive(args.repo_root)
    with args.output.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Closed public data: 12 + 4 observations verified; studies not pooled.')
if __name__=='__main__':main()

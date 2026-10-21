"""Align executor positions with memory calls excluded from alignment, not from costs."""
import argparse
import hashlib
import json
from pathlib import Path

from analyze_native_pair import canonical_transport_ids, public_actions, read


def compare(left, right):
    ls, rs = read(left/'summary.json'), read(right/'summary.json')
    if ls['task_id'] != rs['task_id']:
        raise ValueError('different task identities')
    a, b = read(left/'plan.json'), read(right/'plan.json')
    for key in ('model','seed','agent_temperature','max_calls','max_total_tokens',
                'max_wall_seconds','max_api_requests','max_output_tokens','discovery_policy'):
        if a[key] != b[key]: raise ValueError('different base condition: '+key)
    lu, ru = read(left/'usage.json'), read(right/'usage.json')
    la, ra = [[r for r in usage if r['role']=='agent'] for usage in (lu,ru)]
    views = {r['next_call_id']: r for r in read(right/'memory_views.json')}
    rows=[]
    for position,(a,b) in enumerate(zip(la,ra),1):
        pa,pb=read(left/a['id']/'request.json'),read(right/b['id']/'request.json')
        ma,mb=read(left/a['id']/'response.json'),read(right/b['id']/'response.json')
        comparable=a['status']=='ok' and b['status']=='ok'
        rows.append({'executor_position':position,'left_call_id':a['id'],'right_call_id':b['id'],
                     'exact_request_equal':pa==pb,
                     'request_equal_ignoring_transport_ids':canonical_transport_ids(pa)==canonical_transport_ids(pb),
                     'both_responses_known':comparable,
                     'public_actions_equal':public_actions(ma['message'])==public_actions(mb['message'])
                                             if comparable else None,
                     'right_uses_partial_history':views[b['id']]['selection']['memory_note_added'],
                     'input_output_sha256':{label:{n:hashlib.sha256((folder/call/n).read_bytes()).hexdigest()
                                                   for n in ('request.json','response.json')}
                                            for label,folder,call in (('left',left,a['id']),('right',right,b['id']))}})
    first=lambda key,wanted: next((r['executor_position'] for r in rows if r[key]==wanted),None)
    return {'left_run':left.name,'right_run':right.name,'shared_positions':rows,
            'first_input_difference_beyond_transport_ids':first('request_equal_ignoring_transport_ids',False),
            'first_different_public_action_position':first('public_actions_equal',False),
            'first_partial_history_position':first('right_uses_partial_history',True),
            'left_total_calls':len(lu),'right_total_calls':len(ru),
            'source_hashes':{label:{n:hashlib.sha256((folder/n).read_bytes()).hexdigest()
                                    for n in ('summary.json','usage.json','plan.json')}
                             for label,folder in (('left',left),('right',right))},
            'model_calls':0,'environment_operations':0,'evaluator_accessed':False,
            'scope':'Descriptive executor-position alignment only. Memory calls remain in full '
                    'accounting; unknown responses are not equal successes. Offline ID normalization '
                    'does not change actual inputs, costs, cache or establish same-state causality.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--left',type=Path,required=True)
    parser.add_argument('--right',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=compare(args.left,args.right)
    result['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k.startswith('first_')}))

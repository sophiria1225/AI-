"""An explicit completed-cohort decision is required before stateful task runs."""
import hashlib
import json
from pathlib import Path
from stateful_code_prompts import stateful_system_prompt
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(plan,root=ROOT):
    if plan['phase']!='P29':return
    previous=json.loads((root/'configs/P28_code_clarification_v01.json').read_text())
    allowed={'phase','version','batch_id','wait_for_native_batch','run_order','scope','interpretation',
        'server_lease_end_utc','server_lease_basis'}
    for k,v in previous.items():
        if k not in allowed and plan.get(k)!=v:raise ValueError('P29 changed fixed field: '+k)
    if set(plan)-set(previous)!={'python_state_version'}:raise ValueError('unexpected new setting')
    expected=[[t,a,r.replace('P28_','P29_',1)] for t,a,r in previous['run_order']]
    if (plan['run_order']!=expected or plan['batch_id']!='P29_batch_v01'
        or plan['wait_for_native_batch']!=previous['batch_id']):raise ValueError('wrong full cohort')
    record_path=root/'reports/P29_activation_v01.json'
    if not record_path.exists():raise ValueError('P29 is preparation only; completed P28 review and explicit activation required')
    record=json.loads(record_path.read_text())
    if (record['decision']!='task_local_python_state_all_four'
        or record['system_prompt_sha256']!=hashlib.sha256(stateful_system_prompt(plan).encode()).hexdigest()
        or not record['why'] or not record['alternatives']):raise ValueError('missing P29 activation decision')
    for name,digest in record['prerequisite_sha256'].items():
        if sha(root/name)!=digest:raise ValueError('changed prerequisite: '+name)
    result=json.loads((root/'reports/P28_comparison.json').read_text())
    if not result['all_four_reviewed'] or len(result['pairs'])!=4:raise ValueError('P28 full review is incomplete')

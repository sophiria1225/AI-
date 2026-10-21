"""Fixed conditions for code-runtime calibration; no adaptive task selection."""
import hashlib
import json
from pathlib import Path
from code_runtime_prompts import control_system_prompt
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(plan,root=ROOT):
    if plan['phase']!='P28':return
    previous=json.loads((root/'configs/P27_code_comparison_v01.json').read_text())
    allowed={'phase','version','batch_id','wait_for_native_batch','code_runtime_guidance_version',
             'run_order','scope','discovery_policy','interpretation','server_lease_end_utc','server_lease_basis'}
    for key,value in previous.items():
        if key not in allowed and plan.get(key)!=value:raise ValueError('P28 changed fixed field: '+key)
    if set(plan)-set(previous) != {'code_runtime_guidance_version'}:raise ValueError('unexpected new setting')
    expected=[[t,a,'P28_'+n.split('_',1)[1]] for t,a,n in previous['run_order']]
    if (plan['run_order']!=expected or plan['batch_id']!='P28_batch_v01'
        or plan['wait_for_native_batch']!=previous['batch_id']):raise ValueError('wrong full cohort')
    record=json.loads((root/'reports/P28_activation_v01.json').read_text())
    if (record['decision']!='clarify_provided_globals_only'
        or record['system_prompt_sha256']!=hashlib.sha256(control_system_prompt(plan).encode()).hexdigest()
        or not record['why'] or not record['alternatives']):raise ValueError('missing activation decision')
    for p,h in record['prerequisite_sha256'].items():
        if sha(root/p)!=h:raise ValueError('changed prerequisite: '+p)
    result=json.loads((root/'reports/P27_comparison.json').read_text())
    if not result['all_four_reviewed'] or len(result['pairs'])!=4:raise ValueError('P27 incomplete')

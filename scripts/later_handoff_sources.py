"""Fixed eighth-response sources, selected before complete P31 outcomes."""
from handoff_factors import ARMS, handoff_conversation, prefix_at_fixed_boundary
from recorded_python_replay import load_programs
from run_handoff_factors import prepare_sources, read, sha


def prepare_later_sources(storage,root):
    earlier, source_plan, tools, schemas, originals=prepare_sources(storage,root)
    plan=read(root/'configs/P32_handoff_factors_v01.json')
    if (plan['phase']!='P32' or plan['source_runs']!=earlier['source_runs']
            or plan['boundary_after_model_calls']!=8 or plan['recent_complete_turns']!=1
            or plan['arms']!=list(ARMS)):
        raise ValueError('outside fixed later-boundary design')
    for key in ('max_calls','max_total_tokens','max_wall_seconds','max_setup_seconds','order_rule'):
        if plan[key]!=earlier[key]:raise ValueError('later comparison must retain suffix controls')
    prepared=[]
    for original in originals:
        trial=storage/'records/context_pilot'/original['source_run']
        prefix=prefix_at_fixed_boundary(trial,8)
        ids={c['id'] for c in prefix['usage']}
        programs=[p for p in load_programs(trial,schemas) if p['name'].rsplit('_',1)[0] in ids]
        if not programs or sum(len(p['entries']) for p in programs)!=sum(e['stage']=='python_api' for e in prefix['events']):
            raise ValueError('later Python prefix correspondence differs')
        for arm in ARMS:handoff_conversation(prefix['conversation_private'],prefix['public_task'],arm,8)
        prepared.append({**original,'prefix':prefix,'programs':programs,
            'boundary_manifest_sha256':sha(trial/'boundaries/manifests/call_008.json')})
    return plan,source_plan,tools,schemas,prepared

"""Bounded source reconstruction for the first observed hidden-clock ID gap."""
import copy
import hashlib
from pathlib import Path

from api_error_comparison import initial_conversation
from budget_observation import notification
from budget_visibility_comparison import canonical_messages
from model_provenance import verified_model
from prompt_identity import renamed_request
from protocol_stable_history import StableReferenceConversation
from run_handoff_factors import read,sha

IDS=('P83_P80_ORIGINAL','P83_R2_ORIGINAL','P83_P80_NORMALIZED','P83_R2_NORMALIZED',
     'P83_NATIVE_IDS_CONTROL','P83_CONTENT_CONTROL')
SOURCE_RUNS=('BOC_P80_04_NOT_EXPOSED','BOC_P81_R2_04_NOT_EXPOSED')
SUFFIX='\nP83 offline input reconstruction control.'


def validate_plan(plan):
    fixed={'phase':'P83','batch_id':'P83_fallback_prompt_v01','max_renderings':6,
        'max_wall_seconds':180,'max_sampled_rss_bytes':2**31,'max_input_file_bytes':2**21,
        'source_call':'call_014','source_runs':list(SOURCE_RUNS),'case_ids':list(IDS),
        'negative_control_suffix':SUFFIX,'model_generations':0,'evaluator_calls':0,
        'environment_api_requests':0,'reserved_scenarios_read':0,
        'runtime_commit':'620d2225cc436ab0b001e3200e590e3b286ef9ab',
        'source_plan':'configs/P29_stateful_code_v01.json',
        'required_closed_pipeline':'records/context_pilot/P81_pipeline_v01',
        'source_checkpoint':'.runtime/P81_checkpoint_08.json'}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in fixed.items()):
        raise ValueError('fixed_six_input_reconstruction_changed')
    for name in ('effective_template_sha256','raw_template_sha256'):
        if type(plan.get(name)) is not str or len(plan[name])!=64:
            raise ValueError('fixed_template_hash_required')


def controls(original):
    renamed,count=renamed_request(original)
    if not count:raise ValueError('native_reference_control_needs_bound_calls')
    negative=copy.deepcopy(original)
    if negative['messages'][0]['role']!='system':raise ValueError('first_system_message_required')
    negative['messages'][0]['content']+=SUFFIX
    return renamed,negative


def reconstruct(storage,row,original,target):
    folder=storage/'records/context_pilot'/row['run_id']
    config,public=read(folder/'plan.json'),read(folder/'public_task.json')
    base=initial_conversation(original,public)
    normalized=StableReferenceConversation(base.messages()[0]['content'],public)
    events,spans=read(folder/'events.json'),read(folder/'spans.json')
    signals={s['next_call_id']:s for s in read(folder/'budget_observations.json') if s['model_attempted']}
    usage={s['id']:s for s in read(folder/'usage.json')}
    for check in row['request_checks']:
        cid=check['call_id'];rp=folder/cid/'request.json';sp=folder/cid/'response.json'
        if sha(rp)!=check['request_sha256'] or sha(sp)!=check['response_sha256']:
            raise ValueError('audited_request_or_response_changed')
        request,response=read(rp),read(sp)
        rendered,_=base.for_model(config['observation_page_characters'])
        state=signals[cid]['measured_state']
        expected,_=notification(canonical_messages(rendered),state,'not_exposed')
        if request['messages']!=expected:raise ValueError('original_history_not_reconstructed')
        if cid==target:
            transformed=copy.deepcopy(request)
            visible,stats=normalized.for_model(config['observation_page_characters'])
            transformed['messages'],_=notification(visible,state,'not_exposed')
            if stats['text_fallback_turns']!=1 or response['status']!='ok':
                raise ValueError('fixed_single_fallback_known_response_required')
            if response['input_tokens']!=usage[cid]['input_tokens']:
                raise ValueError('historical_input_accounting_changed')
            return request,transformed,{'run_id':row['run_id'],'call_id':cid,
                'known_input_tokens':response['input_tokens'],'request_sha256':sha(rp),
                'response_sha256':sha(sp),'source_fallback_turns':stats['text_fallback_turns']}
        if response['status']!='ok':raise ValueError('known_causal_prefix_required')
        outer=[spans[e['span_id']] for e in events if e['call']==cid and e['stage']=='model_tool']
        if not outer:raise ValueError('complete_causal_prefix_required')
        base.append(response['message'],outer);normalized.append(response['message'],outer)
    raise ValueError('fixed_source_call_not_found')


def sources(storage,root,plan):
    validate_plan(plan)
    for name,expected in plan['source_sha256'].items():
        if sha(root/name)!=expected:raise ValueError('fixed_repository_source_changed:'+name)
    for name,expected in plan['private_source_sha256'].items():
        if sha(storage/name)!=expected:raise ValueError('fixed_private_source_changed:'+name)
    build=read(root/'reports/P83_renderer_build.json')
    if (build['exit_code']!=0 or build['runtime_commit']!=plan['runtime_commit']
            or sha(storage/build['renderer_relative'])!=build['renderer_sha256']
            or sha(root/'scripts/render_fallback_chat.cpp')!=build['source_cpp_sha256']
            or sha(storage/build['source_archive_relative'])!=build['source_archive_sha256']):
        raise ValueError('fixed_vocabulary_only_renderer_changed')
    for name,value in build['library_sha256'].items():
        if sha(storage/name)!=value:raise ValueError('pinned_runtime_library_changed')
    for name,value in build['header_sha256'].items():
        if sha(storage/build['source_tree_relative']/name)!=value:raise ValueError('pinned_header_changed')
    original=read(root/plan['source_plan'])
    selection,_,model=verified_model(original['model_selection'],root=storage)
    runtime=[read(storage/f'records/context_pilot/P{n}_pipeline_v01/server_runtime.json') for n in (80,81)]
    if (runtime[0]['command']!=runtime[1]['command']
            or any(r['runtime']['commit']!=plan['runtime_commit'] or r['model_revision']!=selection['revision'] for r in runtime)
            or Path(runtime[0]['command'][runtime[0]['command'].index('--model')+1])!=model):
        raise ValueError('two_recorded_commands_or_model_identity_differ')
    raw=(storage/'.runtime/p73-template-sources/model_chat_template.jinja').read_bytes()
    if (hashlib.sha256(raw).hexdigest()!=plan['raw_template_sha256'] or not raw.endswith(b'\n')
            or hashlib.sha256(raw[:-1]).hexdigest()!=plan['effective_template_sha256']):
        raise ValueError('exact_raw_and_effective_templates_required')
    anchor=read(root/'reports/P80_comparison.json')
    checkpoint=read(storage/plan['source_checkpoint'])
    rows=[next(r for r in group if r['run_id']==rid) for group,rid in
          zip((anchor['rows'],checkpoint['audited_rows']),SOURCE_RUNS,strict=True)]
    payloads,proof=[],[]
    for row in rows:
        for name in ('summary','usage','evaluation'):
            if sha(storage/'records/context_pilot'/row['run_id']/(name+'.json'))!=row[name+'_sha256']:
                raise ValueError('closed_cell_record_changed')
        a,b,evidence=reconstruct(storage,row,original,plan['source_call'])
        payloads.append((a,b));proof.append(evidence)
    variants=[payloads[0][0],payloads[1][0],payloads[0][1],payloads[1][1],*controls(payloads[0][0])]
    if variants[2]!=variants[3]:raise ValueError('normalization_does_not_remove_the_fixed_source_difference')
    return build,model,runtime[0]['command'],dict(zip(IDS,variants,strict=True)),proof


def interpret(rendered,proof):
    if set(rendered)!=set(IDS) or len(proof)!=2:raise ValueError('all_six_inputs_and_two_sources_required')
    fields=('prompt','tokens','session_controls','parsed_non_message_parameters')
    equal=lambda a,b:{k:rendered[a][k]==rendered[b][k] for k in fields}
    if any(rendered[k]['input_tokens']!=p['known_input_tokens'] for k,p in zip(IDS[:2],proof,strict=True)):
        raise ValueError('historical_input_count_not_reproduced')
    native=equal(IDS[0],IDS[4]);negative=equal(IDS[0],IDS[5]);normalized=equal(IDS[2],IDS[3])
    if not all(native.values()) or negative['prompt'] or negative['tokens']:
        raise ValueError('native_reference_or_negative_content_control_failed')
    if not all(normalized.values()):raise ValueError('normalized_input_control_failed')
    return {'original_pair_equal':equal(*IDS[:2]),'normalized_pair_equal':normalized,
        'native_reference_control_equal':native,'content_control_equal':negative,
        'historical_input_counts_match':True,'actual_original_state_replayed':False,
        'causal_output_effect_identified':False,'quality_or_savings_established':False}

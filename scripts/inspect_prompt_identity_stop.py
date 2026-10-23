"""Read all existing P73 artifacts after its raw/effective-template guard stopped.

Never invokes the renderer, vocabulary loader, tokenizer, environment or model.
The original stopped report and original exact-input criterion remain immutable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import time

from probe_prompt_identity import PLAN, digest, render_summary, verify_sources
from prompt_identity import renamed_request
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

LOCKED = {
    'reports/P73_prompt_identity.json': 'd5a38803fb709e46f481bd7d5bddb95c89325ca8c08b8ed3f8f642e9247b03f1',
    'reports/P73_prompt_identity_audit.json': 'a4237db92c593e6cdf395650251e4f91a61ddefdbedfa8518192c624d454d2a5',
}


def inspect(storage, frozen):
    started = time.monotonic()
    for path, expected in LOCKED.items():
        if sha(ROOT / path) != expected: raise ValueError('original stopped record changed')
    original = read(ROOT / 'reports/P73_prompt_identity.json')
    old_audit = read(ROOT / 'reports/P73_prompt_identity_audit.json')
    plan = read(frozen / PLAN)
    if (original['status'] != 'stopped' or original['renderer_exit_code'] != 0
            or original['rendered_input_files'] != 69 or original['rendering_attempts'] != 69
            or original['pairs'] or original['calibrations']
            or not old_audit['all_69_inputs_accounted'] or old_audit['all_33_pairs_validated']
            or old_audit['audit_errors']):
        raise ValueError('specific completed-rendering, stopped-analysis record required')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    if (read(folder / 'status.json') != original
            or (folder / 'error_private.txt').read_text() != 'template or vocabulary-only execution differs'):
        raise ValueError('original private status or exact stop reason differs')
    for path, expected in original['code_sha256'].items():
        if sha(frozen / path) != expected or sha(ROOT / path) != expected:
            raise ValueError('frozen implementation changed')
    build, model, command, pairs = verify_sources(storage, plan)
    identities = [r['run_id'] + '_' + r['call_id'] for p in pairs for r in p]
    controls = ['P73_UNCHANGED', 'P73_RENAMED_IDS', 'P73_CHANGED_CONTENT']
    if original['planned_input_ids'] != identities + controls:
        raise ValueError('all original inputs must be retained')
    metadata = read(folder / 'renderer_metadata_private.json')
    raw_template_path = storage / '.runtime/p73-template-sources/model_chat_template.jinja'
    raw = raw_template_path.read_bytes(); effective = metadata['default_template'].encode()
    if (hashlib.sha256(raw).hexdigest() != plan['template_sha256']
            or len(raw) != 11756 or b'\r' in raw or not raw.endswith(b'\n')
            or raw[:-1] != effective or len(effective) != 11755
            or not metadata['vocabulary_only'] or metadata['decode_calls'] or metadata['inference_contexts_created']):
        raise ValueError('only the exact final LF difference is explained by this diagnosis')
    source_tree = storage / build['source_tree_relative']
    source_hashes = {name:sha(source_tree / name) for name in (
        'common/jinja/lexer.cpp','common/chat.cpp','tools/server/server-common.cpp','tools/server/server-context.cpp','src/llama.cpp')}
    manifest = read(folder / 'render_manifest_private.json')
    expected_cases = [{'id':r['run_id']+'_'+r['call_id'],'request_path':str(storage/'records/context_pilot'/r['run_id']/r['call_id']/'request.json')} for pair in pairs for r in pair]
    expected_cases += [{'id':identity,'request_path':str(folder/(identity+'_request_private.json'))} for identity in controls]
    if manifest != {'recorded_server_command':command,'model_path':str(model),'output_dir':str(folder),'cases':expected_cases}:
        raise ValueError('renderer manifest or input mapping differs')
    if read(folder/'renderer_complete.json') != {'renderings':69,'decode_calls':0}:
        raise ValueError('renderer completion receipt differs')
    inputs, rendered = {}, {}
    for entry in expected_cases:
        identity = entry['id']
        if read(folder/(identity+'_started.json')) != {'id':identity,'status':'rendering_started'}:
            raise ValueError('missing or inconsistent start receipt')
        inputs[identity] = read(Path(entry['request_path']))
        renamed_request(inputs[identity])
        value = read(folder/(identity+'_rendered_private.json'))
        if (value['id'] != identity or value['media_files'] != 0
                or not isinstance(value['prompt'],str) or type(value['input_tokens']) is not int
                or len(value['tokens']) != value['input_tokens']
                or any(type(t) is not int or t < 0 for t in value['tokens'])):
            raise ValueError('invalid saved rendering')
        rendered[identity] = value
    rows = []
    for index, pair in enumerate(pairs,1):
        ids = [r['run_id']+'_'+r['call_id'] for r in pair]
        values = [rendered[identity] for identity in ids]
        bound = [renamed_request(inputs[identity]) for identity in ids]
        rows.append({'index':index,'reference_run':pair[0]['run_id'],'controlled_run':pair[1]['run_id'],
            'call_id':pair[0]['call_id'],'raw_requests_equal':inputs[ids[0]]==inputs[ids[1]],
            'bound_id_renamed_requests_equal':bound[0][0]==bound[1][0],
            'historical_tool_bindings':[b[1] for b in bound],
            'historical_input_tokens':[r['input_tokens'] for r in pair],
            'rendered_input_tokens':[v['input_tokens'] for v in values],
            'historical_input_counts_match':[v['input_tokens']==r['input_tokens'] for v,r in zip(values,pair,strict=True)],
            'equal':{k:values[0][k]==values[1][k] for k in ('prompt','tokens','session_controls','parsed_non_message_parameters')},
            'rendered':[render_summary(v) for v in values],
            'source_sha256':[{k:r[k] for k in ('request_sha256','response_sha256')} for r in pair],
            'private_rendering_sha256':[sha(folder/(identity+'_rendered_private.json')) for identity in ids]})
    reference = '_'.join(plan['calibration_reference'])
    base = inputs[reference]
    changed = json.loads(json.dumps(base));changed['messages'][0]['content'] += plan['negative_control_suffix']
    expected = {'P73_UNCHANGED':base,'P73_RENAMED_IDS':renamed_request(base)[0],'P73_CHANGED_CONTENT':changed}
    calibration = {}
    for identity in controls:
        if inputs[identity] != expected[identity]: raise ValueError('calibration input changed')
        calibration[identity] = {'equal':{k:rendered[identity][k]==rendered[reference][k] for k in (
            'prompt','tokens','session_controls','parsed_non_message_parameters')},
            'rendered':render_summary(rendered[identity]),'source_sha256':sha(folder/(identity+'_request_private.json')),
            'private_rendering_sha256':sha(folder/(identity+'_rendered_private.json'))}
    groups=[]
    for before,after,count in plan['pair_runs']:
        group=[r for r in rows if r['reference_run']==before and r['controlled_run']==after]
        if len(group)!=count: raise ValueError('fixed comparison lost a row')
        groups.append({'reference_run':before,'controlled_run':after,'pairs':count,
            'raw_request_equal_pairs':sum(r['raw_requests_equal'] for r in group),
            'bound_id_renamed_equal_pairs':sum(r['bound_id_renamed_requests_equal'] for r in group),
            'equal_pairs':{k:sum(r['equal'][k] for r in group) for k in group[0]['equal']},
            'historical_input_counts_matching':sum(sum(r['historical_input_counts_match']) for r in group)})
    total=time.monotonic()-started
    if total>120: raise TimeoutError('read-only diagnosis deadline')
    return {'phase':'P73_stop_diagnosis','status':'complete','original_batch_status':'stopped',
        'original_comparison_pairs_validated':0,'posthoc_pairs_inspected':len(rows),'all_69_existing_renderings_accounted':True,
        'template_normalization':{'raw_bytes':len(raw),'effective_bytes':len(effective),'removed_final_LF_bytes':1,
            'raw_sha256':hashlib.sha256(raw).hexdigest(),'effective_sha256':hashlib.sha256(effective).hexdigest(),
            'other_template_bytes_changed':False,'metadata_source_sha256':sha(folder/'renderer_metadata_private.json')},
        'groups':groups,'pairs':rows,'calibrations':calibration,
        'all_historical_input_counts_match':all(all(r['historical_input_counts_match']) for r in rows),
        'all_reconstructed_prompts_equal':all(r['equal']['prompt'] for r in rows),
        'all_reconstructed_token_sequences_equal':all(r['equal']['tokens'] for r in rows),
        'all_reconstructed_generation_controls_equal':all(r['equal']['session_controls'] and r['equal']['parsed_non_message_parameters'] for r in rows),
        'source_sha256':{**LOCKED,'configs/P73_prompt_identity_v01.json':sha(frozen/PLAN),
            'docs/P73_stop_diagnosis_scope.md':sha(ROOT/'docs/P73_stop_diagnosis_scope.md')},
        'upstream_implementation_sha256':source_hashes,'inspector_sha256':sha(Path(__file__)),
        'additional_vocabulary_loads':0,'additional_renderings':0,'additional_input_tokenizations':0,
        'additional_model_calls':0,'additional_api_requests':0,'additional_evaluator_calls':0,'reserved_scenarios_read':0,
        'original_criteria_changed':False,'original_outcomes_relabelled':False,'wall_seconds':total,
        'limits':['Posthoc read-only analysis after a prespecified source guard stopped the batch.',
                  'Original exact request/response criterion and all original outcomes/costs remain unchanged.',
                  'Reconstructed inputs do not restore historical GPU, random-generator or timing state.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True);p.add_argument('--frozen-root',type=Path,required=True);args=p.parse_args()
    out=ROOT/'reports/P73_stop_diagnosis.json'
    if out.exists():raise FileExistsError('preserve original read-only diagnosis')
    def timeout(*_):raise TimeoutError('read-only diagnosis deadline')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    result=inspect(args.storage_root,args.frozen_root);write_json(out,result);signal.alarm(0)
    print({k:result[k] for k in ('status','original_batch_status','groups','all_historical_input_counts_match','wall_seconds')})

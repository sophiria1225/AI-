"""Read all P73 artifacts without executing the renderer or tokenizer again."""
import argparse
import hashlib
import json
from pathlib import Path

from probe_prompt_identity import PLAN, digest, render_summary, verify_sources
from prompt_identity import renamed_request
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit(storage, frozen):
    public = frozen / 'reports/P73_prompt_identity.json'
    report = read(public); plan = read(frozen / PLAN)
    if report['status'] not in ('complete', 'stopped') or report['source_plan_sha256'] != sha(frozen / PLAN):
        raise ValueError('closed fixed reconstruction report required')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    if read(folder / 'status.json') != report: raise ValueError('public/private report mismatch')
    for path, expected in report['code_sha256'].items():
        if sha(frozen / path) != expected or sha(ROOT / path) != expected:
            raise ValueError('executed source differs: ' + path)
    _, _, _, pairs = verify_sources(storage, plan)
    identities = [r['run_id'] + '_' + r['call_id'] for pair in pairs for r in pair]
    controls = ('P73_UNCHANGED', 'P73_RENAMED_IDS', 'P73_CHANGED_CONTENT')
    if report['planned_input_ids'] != identities + list(controls): raise ValueError('complete fixed selection differs')
    statuses = []
    expected_requests = {}
    for pair in pairs:
        for row in pair:
            identity = row['run_id'] + '_' + row['call_id']
            expected_requests[identity] = read(storage / 'records/context_pilot' / row['run_id'] / row['call_id'] / 'request.json')
    reference = '_'.join(plan['calibration_reference'])
    expected_requests['P73_UNCHANGED'] = expected_requests[reference]
    expected_requests['P73_RENAMED_IDS'] = renamed_request(expected_requests[reference])[0]
    changed = json.loads(json.dumps(expected_requests[reference]))
    changed['messages'][0]['content'] += plan['negative_control_suffix']
    expected_requests['P73_CHANGED_CONTENT'] = changed
    for identity in report['planned_input_ids']:
        output = folder / (identity + '_rendered_private.json')
        start = folder / (identity + '_started.json')
        if output.exists() and not start.exists(): raise ValueError('output without started receipt')
        if start.exists() and read(start) != {'id': identity, 'status': 'rendering_started'}:
            raise ValueError('rendering receipt differs')
        if identity in controls:
            saved = folder / (identity + '_request_private.json')
            if saved.exists() and read(saved) != expected_requests[identity]: raise ValueError('control input changed')
        statuses.append({'id': identity, 'status': 'rendered' if output.exists() else 'attempted_incomplete' if start.exists() else 'not_run'})
    if (sum(s['status'] == 'rendered' for s in statuses) != report['rendered_input_files']
            or sum(s['status'] != 'not_run' for s in statuses) != report['rendering_attempts']):
        raise ValueError('attempted or completed rendering count differs')
    checked = []
    for index, pair in enumerate(pairs, 1):
        public_pair = next((p for p in report['pairs'] if p['index'] == index), None)
        if public_pair is None:
            checked.append({'index': index, 'status': 'not_validated'}); continue
        ids = [r['run_id'] + '_' + r['call_id'] for r in pair]
        values = [read(folder / (identity + '_rendered_private.json')) for identity in ids]
        if (public_pair['reference_run'] != pair[0]['run_id'] or public_pair['controlled_run'] != pair[1]['run_id']
                or public_pair['call_id'] != pair[0]['call_id']
                or public_pair['private_rendering_sha256'] != [sha(folder / (i + '_rendered_private.json')) for i in ids]
                or public_pair['rendered'] != [render_summary(v) for v in values]
                or public_pair['source_sha256'] != [{k:r[k] for k in ('request_sha256','response_sha256')} for r in pair]):
            raise ValueError('pair source or output linkage differs')
        equal = {k: values[0][k] == values[1][k] for k in ('prompt','tokens','session_controls','parsed_non_message_parameters')}
        expected_raw = expected_requests[ids[0]] == expected_requests[ids[1]]
        bound = [renamed_request(expected_requests[identity]) for identity in ids]
        if (public_pair['equal'] != equal or public_pair['raw_requests_equal'] != expected_raw
                or public_pair['bound_id_renamed_requests_equal'] != (bound[0][0] == bound[1][0])
                or public_pair['historical_tool_bindings'] != [b[1] for b in bound]
                or not public_pair['historical_input_counts_match']
                or any(v['input_tokens'] != r['input_tokens'] or len(v['tokens']) != r['input_tokens']
                       or v['id'] != identity or v['media_files'] != 0 for v,r,identity in zip(values,pair,ids,strict=True))):
            raise ValueError('pair comparison or original input count differs')
        checked.append({'index': index, 'reference_run': pair[0]['run_id'], 'controlled_run': pair[1]['run_id'],
            'call_id': pair[0]['call_id'], 'status': 'validated', 'equal': equal,
            'raw_requests_equal': expected_raw, 'bound_id_renamed_requests_equal': bound[0][0] == bound[1][0],
            'historical_input_tokens': [r['input_tokens'] for r in pair]})
    if len({p['index'] for p in report['pairs']}) != len(report['pairs']): raise ValueError('duplicate comparison')
    if report['status'] == 'complete':
        if (any(s['status'] != 'rendered' for s in statuses) or any(p['status'] != 'validated' for p in checked)
                or report['renderer_exit_code'] != 0 or report['original_criteria_changed']
                or report['inference_contexts_created'] or report['model_generations']
                or report['evaluator_calls'] or report['environment_api_requests'] or report['reserved_scenarios_read']):
            raise ValueError('incomplete or out-of-scope successful report')
        meta = read(folder / 'renderer_metadata_private.json')
        if (sha(folder / 'renderer_metadata_private.json') != report['renderer_metadata_sha256']
                or hashlib.sha256(meta['default_template'].encode()).hexdigest() != plan['template_sha256']
                or not meta['vocabulary_only'] or meta['decode_calls'] or meta['inference_contexts_created']):
            raise ValueError('metadata or vocabulary-only execution differs')
        base = read(folder / (reference + '_rendered_private.json'))
        for identity in controls:
            value = read(folder / (identity + '_rendered_private.json'))
            entry = report['calibrations'][identity]
            equal = {k: base[k] == value[k] for k in ('prompt','tokens','session_controls','parsed_non_message_parameters')}
            if (entry['equal'] != equal or entry['rendered'] != render_summary(value)
                    or entry['source_sha256'] != sha(folder / (identity + '_request_private.json'))
                    or entry['private_rendering_sha256'] != sha(folder / (identity + '_rendered_private.json'))):
                raise ValueError('calibration output or linkage differs')
        if (not all(report['calibrations']['P73_UNCHANGED']['equal'].values())
                or any(report['calibrations']['P73_CHANGED_CONTENT']['equal'][k] for k in ('prompt','tokens'))):
            raise ValueError('unchanged or changed-content calibration did not hold')
        for report_key, keys in [
            ('all_pair_prompts_equal', ['prompt']), ('all_pair_token_sequences_equal', ['tokens']),
            ('all_pair_controls_equal', ['session_controls','parsed_non_message_parameters'])]:
            if report[report_key] != all(p['equal'][k] for p in checked for k in keys):
                raise ValueError('aggregate comparison differs')
    return {'phase':'P73_audit','batch_status':report['status'],'audit_errors':[],
        'all_69_inputs_accounted':True,'all_33_pairs_validated':all(p['status']=='validated' for p in checked),
        'inputs':statuses,'pairs':checked,'calibrations':report['calibrations'],
        'original_sources_unchanged':True,'original_criteria_changed':False,
        'source_report_sha256':sha(public),'source_plan_sha256':sha(frozen / PLAN),
        'auditor_sha256':sha(Path(__file__)),
        'additional_renderings':0,'additional_model_calls':0,'additional_api_requests':0,'additional_evaluator_calls':0,
        'scope':'Read-only validation of pinned-runtime reconstruction; original full-request/response failure remains unchanged.'}


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True);p.add_argument('--frozen-root',type=Path,required=True)
    args=p.parse_args();target=ROOT/'reports/P73_prompt_identity_audit.json'
    if target.exists(): raise FileExistsError('preserve prior audit')
    result=audit(args.storage_root,args.frozen_root);write_json(target,result)
    print({k:result[k] for k in ('batch_status','all_69_inputs_accounted','all_33_pairs_validated')})

"""Passive P38 opportunity audit. Lookup always precedes the current response.

This diagnostic reuses the frozen contract as a shadow cache in all three arms.
It does not change requests, relax invalidation, read answers or invoke a model.
Public output contains counts/hashes, never object identifiers or values.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

from analyze_structured_reuse import decode
from field_read_contract import (CONTRACT_ID, FIELDS, SOURCE, TARGET, canonical,
                                 target_identity)
from projected_read_runtime import ARMS, ProjectedReadRuntime
from run_context_comparison import write_json
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]


def model_payload(message):
    """Exclude transport-generated call IDs, retain all generated content."""
    result=copy.deepcopy(message)
    for call in result.get('tool_calls') or []:
        call.pop('id',None)
    return result


def classify(runtime, api, arguments, fields, previously_observed):
    """Explain a projected request using only the cache available before it."""
    identity = target_identity(api, arguments)
    if identity is None: return 'unsupported_target_or_arguments'
    hit = runtime.cache.lookup(api, arguments, fields, runtime.context())
    if hit is not None: return 'hit_' + hit.source
    exact = runtime.cache.exact.get(canonical(arguments), {})
    partial = runtime.cache.fields.get(identity, {})
    if len(exact) > 1 or any(len(partial.get(f, {})) > 1 for f in fields):
        return 'conflicting_versions'
    if identity not in runtime.cache.fields and not exact:
        return ('previous_value_no_longer_available' if identity in previously_observed
                else 'object_not_previously_observed')
    if not set(fields) <= FIELDS: return 'fields_outside_contract'
    return 'required_fields_not_covered'


def run(storage, root):
    report = read(root / 'reports/P38_comparison.json')
    status = read(storage / 'records/context_pilot/P38_batch_v01/status.json')
    expected = ['P38_04_' + a.upper() for a in ARMS]
    if (status['status'] != 'complete' or status['completed'] != expected
            or not report['all_three_reviewed'] or [r['run_id'] for r in report['rows']] != expected):
        raise ValueError('wait for the closed cohort')
    activation = read(root / 'reports/P38_activation_v01.json')
    for name in ('scripts/field_read_contract.py', 'scripts/projected_read_runtime.py'):
        if sha(root/name) != activation['source_hashes'][name]: raise ValueError('changed contract')
    target = root / 'reports/P38_miss_diagnostics.json'
    if target.exists(): raise FileExistsError('preserve completed diagnostics')
    rows=[]; first_requests=[]; first_outputs=[]
    for original in report['rows']:
        rid=original['run_id']; trial=storage/'records/context_pilot'/rid
        for name in ('events.json','spans.json','usage.json'):
            if sha(trial/name) != original['source_hashes'][name]: raise ValueError('changed records')
        prefix=read(trial/'prefix_events.json'); events=read(trial/'events.json'); spans=read(trial/'spans.json')
        runtime=ProjectedReadRuntime('contract',execution_scope='shadow:'+rid,verified_contract=CONTRACT_ID)
        ever=set(); seeded=set(); reasons=Counter(); observed_target_requests=0; prefix_revision=0
        for stage,sequence in (('prefix',prefix),('suffix',events)):
            if stage == 'suffix':
                seeded=set(runtime.cache.fields); prefix_revision=runtime.revision
            for event in sequence:
                if event['stage'] != 'python_api': continue
                span=spans[event['span_id']]; action=span['action']; args=json.loads(action['arguments'])
                meta=span['observation'].get('field_read')
                # Only recorded explicit field requests, not fields inferred from future code.
                if stage == 'suffix' and meta and not meta['full_api_response']:
                    reasons[classify(runtime,action['name'],args,meta['requested_fields'],ever)]+=1
                    observed_target_requests+=int(target_identity(action['name'],args) in seeded)
                ever.update(runtime.cache.fields)
                for exact in runtime.cache.exact:
                    identity=target_identity(TARGET,json.loads(exact))
                    if identity is not None: ever.add(identity)
                if event['api_request_sent']:
                    ok,value=decode(span['observation'])
                    runtime.observed_sent(action['name'],args,success=ok,value=value)
        usage=read(trial/'usage.json'); first=trial/usage[0]['id']
        request=read(first/'request.json'); response=read(first/'response.json')
        # Compare model-produced fields, excluding timestamps, usage and timings.
        if response['status'] != 'ok' or type(response.get('message')) is not dict:
            raise ValueError('cannot compare a missing first generation')
        produced=model_payload(response['message'])
        first_requests.append(request);first_outputs.append(produced)
        rows.append({'run_id':rid,'arm':original['arm'],'available_source_objects_at_boundary':len(seeded),
                     'explicit_projected_requests':sum(reasons.values()),'shadow_contract_reasons':dict(reasons),
                     'requests_for_boundary_source_objects':observed_target_requests,
                     'suffix_invalidations':runtime.revision-prefix_revision,
                     'first_request_sha256':sha(first/'request.json'),
                     'first_response_file_sha256':sha(first/'response.json'),
                     'first_produced_sha256':hashlib.sha256(canonical(produced).encode()).hexdigest(),
                     'source_sha256':{n:sha(trial/n) for n in ('prefix_events.json','events.json','spans.json','usage.json')}})
    result={'phase':'P38_miss_diagnostics','rows':rows,'all_three_diagnosed':True,
            'identical_first_request':all(r==first_requests[0] for r in first_requests),
            'identical_first_produced_fields':all(r==first_outputs[0] for r in first_outputs),
            'cache_arms_first_produced_fields_equal':first_outputs[1]==first_outputs[2],
            'model_calls_added':0,'api_requests_added':0,'evaluator_calls_added':0,'reserved_scenarios_read':0,
            'source_sha256':{p:sha(root/p) for p in ('reports/P38_comparison.json','scripts/diagnose_projected_misses.py',
                                                   'scripts/field_read_contract.py','scripts/projected_read_runtime.py')},
            'limits':['A shadow lookup over fixed recorded requests is not a model counterfactual.',
                      'First-message comparisons exclude only transport-generated tool-call IDs.',
                      'The first request can be identical even if sampled generations differ.',
                      'Different cache/prefill counts are observed, but do not establish why outputs differ.']}
    write_json(target,result)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args();run(a.storage_root,a.repo_root)

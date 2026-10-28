"""Bind all closed saved inputs before the finite P145 transport diagnostic."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from run_handoff_factors import ROOT, read, sha
from run_update_transport_p145 import PLAN, CASES, schedule, validate_plan


def prepare(storage, root):
    target = root / PLAN
    if target.exists():
        raise FileExistsError('preserve_P145_protocol')
    prior = read(root / 'configs/P144R1_continuation_v01.json')
    paths = set(prior['source_sha256']) | {'configs/P144R1_continuation_v01.json'}
    for area in ('scripts', 'tests'):
        paths.update(str(p.relative_to(root)) for p in (root / area).glob('*p145.py'))
    paths.add('docs/experiments/P145_update_transport_20261029.md')
    registry = read(storage / '.runtime/research_ledger_names.json')
    if len(registry) != len(set(registry)):
        raise ValueError('unique_ledger_registry_required')
    binding_count = 0
    for name in registry:
        path = 'reports/' + name + '.json'
        value = read(root / path)
        paths.add(path)
        for rel, expected in value['source_sha256'].items():
            if sha(root / rel) != expected:
                raise ValueError('old_registered_source_changed:' + rel)
            paths.add(rel)
        binding_count += len(value['source_sha256'])
    private = ['.runtime/P145_user_authorization_20261029.json',
        '.runtime/P144R1_closed_independent_check_20261029.json',
        '.runtime/P144R1_update_rejection_diagnosis_20261029.json',
        'records/context_pilot/P144R1_pipeline_v01/status.json',
        'records/context_pilot/P144R1_pipeline_v01/server_final.json']
    cases = []
    for number, rid, cid in CASES:
        next_call = f'call_{int(cid[5:])+1:03d}'
        cases.append(dict(task_slot=number, source_run=rid, source_call=cid, next_actor_call=next_call))
        base = 'records/context_pilot/' + rid + '/'
        private.extend(base + rel for rel in (cid + '/request.json', cid + '/response.json',
            next_call + '/request.json', 'summary.json', 'rolling_offers_private.json'))
    value = dict(phase='P145', created_at=datetime.now(timezone.utc).isoformat(),
        cases=cases, schedule=[dict(task_slot=n, arm=a) for n, a in schedule()],
        max_model_calls=12, max_total_tokens=450000, output_cap=4096,
        call_timeout_seconds=480, server_max_lifetime_seconds=8100,
        max_environment_api_calls=0, max_evaluator_calls=0, automatic_retries=0,
        latest_launch_jst='2026-10-29T02:15:00+09:00',
        operational_latest_launch_is_not_a_user_deadline=True,
        candidate_for_whole_task='schema_bounded', candidate_selection_from_results=False,
        source_inputs_selected_after_failure=True, full_task_quality_or_savings_claim=False,
        task_requirements_or_answers_added=False, preserved_scientific_output_cap=4096,
        reasoning_budgets=[-1,2048], output_formats=['native','schema'],
        prior_registry_sha256=sha(storage / '.runtime/research_ledger_names.json'),
        prior_ledger_count=len(registry), prior_binding_count=binding_count,
        source_sha256={rel:sha(root / rel) for rel in sorted(paths)},
        private_source_sha256={rel:sha(storage / rel) for rel in private})
    validate_plan(value)
    with target.open('x') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')
    return value


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage-root',type=Path,required=True)
    args=p.parse_args()
    v=prepare(args.storage_root.resolve(),ROOT)
    print({k:v[k] for k in ('phase','max_model_calls','prior_ledger_count','prior_binding_count')})

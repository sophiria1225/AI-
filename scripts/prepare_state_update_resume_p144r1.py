"""Freeze the explicitly authorized ten-cell shutdown continuation; no generation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from run_handoff_factors import ROOT, read, sha
from state_update_resume_config_p144r1 import REMAINING, original_cell_id, remaining_ids
from run_state_update_resume_p144r1 import SPEC, AUTH, RECOVERY, HANDOFF, validate_spec


def prepare(storage, root):
    target = root / SPEC
    if target.exists():
        raise FileExistsError('preserve_continuation_protocol')
    old_path = root / 'configs/P144_state_update_v01.json'
    old = read(old_path)
    for rel, expected in old['source_sha256'].items():
        if sha(root / rel) != expected:
            raise ValueError('original_P144_source_changed:' + rel)
    registry_path = storage / '.runtime/research_ledger_names.json'
    registry = read(registry_path)
    if type(registry) is not list or len(registry) != len(set(registry)):
        raise ValueError('unique_provenance_registry_required')
    bindings = {}
    for name in registry:
        relative = 'reports/' + name + '.json'
        ledger = read(root / relative)
        sources = ledger['source_sha256']
        for rel, expected in sources.items():
            if sha(root / rel) != expected:
                raise ValueError('prior_provenance_source_changed:' + rel)
        bindings[name] = dict(ledger_sha256=sha(root / relative), source_sha256=sources)
    new_sources = [str(p.relative_to(root)) for area in ('scripts', 'tests')
                   for p in (root / area).glob('*p144r1.py')]
    new_sources.append('docs/experiments/P144R1_shutdown_continuation_20261028.md')
    paths = set(old['source_sha256']) | {'configs/P144_state_update_v01.json'} | set(new_sources)
    for name, binding in bindings.items():
        paths.add('reports/' + name + '.json')
        paths.update(binding['source_sha256'])
    value = dict(phase='P144R1', created_at=datetime.now(timezone.utc).isoformat(),
        inherited_plan='configs/P144_state_update_v01.json', inherited_plan_sha256=sha(old_path),
        remaining_run_ids=list(remaining_ids()),
        canonical_remaining_run_ids=[original_cell_id(n, m) for n, m in REMAINING],
        max_new_cells=10, max_new_model_calls=800, max_new_reserved_tokens=4500000,
        max_new_environment_api_requests=880, max_new_evaluator_calls=10,
        saved_evaluator_recovery_calls=1, max_new_summary_calls=20,
        server_max_lifetime_seconds=21000, batch_timeout_seconds=20220,
        latest_launch_jst='2026-10-28T17:20:00+09:00',
        deadline_jst='2026-10-28T23:15:00+09:00',
        reporting_deadline_jst='2026-10-28T23:59:00+09:00',
        automatic_retries=0, regenerate_completed_cells=False,
        choose_conditions_from_outcomes=False, reserved_scenarios_read=0,
        original_phase_reports_immutable=True, original_stop_marker_preserved=True,
        scientific_parameters_inherited_unchanged=True, continuation_is_same_server_session=False,
        resume_authorization_sha256=sha(storage / AUTH),
        shutdown_handoff_sha256=sha(storage / HANDOFF),
        saved_evaluation_recovery_sha256=sha(storage / RECOVERY),
        container_restore_sha256=sha(storage / '.runtime/P144R1_container_restore_20261028.json'),
        prior_registry_sha256=sha(registry_path), prior_ledger_count=len(bindings),
        prior_binding_count=sum(len(v['source_sha256']) for v in bindings.values()),
        prior_ledgers=bindings, source_sha256={rel: sha(root / rel) for rel in sorted(paths)},
        required_CI_events=['push', 'pull_request'], model_generations_started=False)
    validate_spec(value)
    with target.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    return value


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--storage-root', type=Path, required=True)
    args = p.parse_args()
    result = prepare(args.storage_root.resolve(), ROOT)
    print(json.dumps({k: result[k] for k in ('phase', 'max_new_cells', 'prior_ledger_count', 'prior_binding_count')}))

"""Reconstruct every P43 saved input without a model, environment or evaluator."""
import argparse
import json
from pathlib import Path

from input_exposure_accounting import COMPONENTS, token_increments
from inspect_input_exposure import prepare
from run_handoff_factors import ROOT, read, sha


def audit_row(expected, row, cases, folder, *, tokens):
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError('source output classification or identity differs')
    entries = row['cumulative_inputs']
    if [e['component'] for e in entries] != ['envelope', *COMPONENTS]:
        raise ValueError('incomplete or reordered cumulative inputs')
    for case, entry in zip(cases, entries, strict=True):
        if case['component'] != entry['component']:
            raise ValueError('component identity differs')
        path = folder / f'{row["source_run"]}_{entry["component"]}_private.json'
        if sha(path) != entry['input_sha256'] or read(path) != case:
            raise ValueError('saved cumulative input differs from reconstruction')
    if tokens:
        counts = {e['component']: e['input_tokens'] for e in entries}
        if (row['ordered_token_increments'] != token_increments(counts)
                or list(counts.values())[-1] != row['p42_full_input_tokens']):
            raise ValueError('token accounting or P42 full-input correspondence differs')
    return {'source_run': row['source_run'], 'inputs_reconstructed': len(entries),
            'outputs_verified': len(row['outputs']), 'p42_candidates': row['p42_candidates_accounted']}


def audit(root, storage):
    _, rows, inputs = prepare(storage, root)
    checked = []
    for mode in ('structure', 'tokens'):
        path = root / f'reports/P43_input_exposure_{mode}.json'
        result = read(path)
        folder = storage / f'records/context_pilot/P43_input_exposure_{mode}_v01'
        if result != read(folder / 'status.json') or result['status'] != 'complete':
            raise ValueError('complete public and saved status must match')
        if len(result['rows']) != 4 or result['component_order'] != ['envelope', *COMPONENTS]:
            raise ValueError('incomplete fixed cohort or components')
        if result['p42_report_sha256'] != sha(root / 'reports/P42_documentation_exposure.json'):
            raise ValueError('P42 reference changed')
        if (result['input_count_requests'] != (44 if mode == 'tokens' else 0)
                or any(result[key] != 0 for key in ('failed_input_count_requests', 'model_generations',
                      'environment_api_requests', 'python_replay_programs', 'evaluator_calls', 'reserved_scenarios_read'))):
            raise ValueError('unexpected resource use or incomplete counting')
        for name, value in result['source_sha256'].items():
            if sha(root / name) != value:
                raise ValueError('accounting source changed: ' + name)
        checks = [audit_row(expected, measured, cases, folder, tokens=mode == 'tokens')
                  for expected, measured, cases in zip(rows, result['rows'], inputs, strict=True)]
        checked.append({'mode': mode, 'report_sha256': sha(path), 'rows': checks})
    return {'phase': 'P43', 'checked': checked, 'errors': [], 'auditor_sha256': sha(Path(__file__)),
            'additional_input_count_requests': 0, 'model_generations': 0,
            'environment_api_requests': 0, 'evaluator_calls': 0,
            'scope': 'Saved inputs, source hashes, output grouping and accounting identities. Interior token counts are saved server measurements, not independently retokenized here. Text equality is not dataflow.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    target = args.repo_root / 'reports/P43_input_exposure_integrity.json'
    if target.exists():
        raise FileExistsError('preserve previous integrity report')
    result = audit(args.repo_root, args.storage_root)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print({'modes': len(result['checked']), 'inputs_reconstructed': 88, 'errors': result['errors']})

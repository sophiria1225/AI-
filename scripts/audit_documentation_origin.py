"""Audit P44 saved inputs, exact permitted edits, literals and archive links."""
import argparse
import copy
import json
from pathlib import Path

from documentation_exposure import DOCUMENTATION_APIS
from documentation_print_origin import build_origin_view
from handoff_factors import split_turns
from input_exposure_accounting import digest
from inspect_documentation_origin import prepare
from later_handoff_sources import prepare_later_sources
from native_conversation import recover_turn
from run_handoff_factors import ROOT, read, sha


def verify_edits(full, selected, meta, archive):
    if full[:2] != selected[:2]:
        raise ValueError('system or task changed')
    pairs = list(zip(split_turns(full), split_turns(selected), strict=True))
    if not pairs or pairs[-1][0] != pairs[-1][1]:
        raise ValueError('latest complete turn changed')
    chosen = {row['span_id']: row for row in meta['checks'] if row['changed']}
    changed, literal_characters, references = [], 0, set()
    for before, after in pairs:
        if before[0] != after[0]:
            raise ValueError('original model action changed')
        for old, new in zip(recover_turn(before), recover_turn(after), strict=True):
            if old == new:
                continue
            if old['id'] not in chosen:
                raise ValueError('unselected output changed')
            row = chosen[old['id']]
            if not row['recognized'] or row['receipt_group'] != 'documentation_only':
                raise ValueError('unrecognized or mixed output changed')
            a, b = copy.deepcopy(old), copy.deepcopy(new)
            for value in (a, b):
                value['observation'].pop('stdout', None)
                value['observation'].pop('stdout_view', None)
            if a != b:
                raise ValueError('non-stdout observation fields changed')
            stdout = old['observation']['stdout']
            receipt_ids = {r['span_id'] for r in old['observation']['api_receipts']}
            expected, previous, used = [], 0, []
            for part in row['segments']:
                start, end, sid = part['start'], part['end'], part['receipt_id']
                if type(start) is not int or type(end) is not int or start != previous or not start < end <= len(stdout):
                    raise ValueError('output partition is incomplete or overlapping')
                text = stdout[start:end]
                if digest(text) != part['text_sha256']:
                    raise ValueError('segment content differs')
                if sid is None:
                    expected.append(text); literal_characters += len(text)
                else:
                    if (sid not in receipt_ids or sid not in archive
                            or archive[sid]['action']['name'] not in DOCUMENTATION_APIS):
                        raise ValueError('invalid documentation archive reference')
                    expected.append(f'[API documentation omitted; read archived span {sid}.]')
                    used.append(sid); references.add(sid)
                previous = end
            if previous != len(stdout) or ''.join(expected) != new['observation']['stdout']:
                raise ValueError('literal output or omission text changed')
            annotation = {'omitted': True, 'source_span_id': old['id'],
                          'documentation_receipt_ids': list(dict.fromkeys(used)),
                          'literal_output_preserved': True}
            if new['observation'].get('stdout_view') != annotation:
                raise ValueError('archive annotation differs')
            changed.append(old['id'])
    if set(changed) != set(chosen) or len(changed) != meta['changed_outputs']:
        raise ValueError('not every selected output was changed exactly once')
    return {'changed_outputs': len(changed), 'literal_characters_preserved': literal_characters,
            'distinct_documentation_references': len(references)}


def audit(root, storage):
    path = root / 'reports/P44_documentation_origin.json'; report = read(path)
    folder = storage / 'records/context_pilot/P44_documentation_origin_v01'
    if report != read(folder / 'status.json') or report['status'] != 'complete':
        raise ValueError('complete saved and public measurements must match')
    if report['input_count_requests'] != 8 or any(report[k] != 0 for k in (
            'failed_input_count_requests', 'model_generations', 'environment_api_requests',
            'python_replay_programs', 'evaluator_calls', 'reserved_scenarios_read')):
        raise ValueError('unexpected resource use')
    for name, value in report['source_sha256'].items():
        if sha(root / name) != value:
            raise ValueError('fixed accounting source changed: ' + name)
    original, expected, inputs = prepare(storage, root)
    _, _, _, _, items = prepare_later_sources(storage, root)
    checked = []
    for measured, row, outputs, item in zip(report['rows'], expected, inputs, items, strict=True):
        if any(measured.get(k) != v for k, v in row.items()):
            raise ValueError('reconstructed selection differs')
        if list(measured['views']) != list(outputs):
            raise ValueError('incomplete input views')
        for name, messages in outputs.items():
            source = folder / f'{row["source_run"]}_{name}_private.json'
            if sha(source) != measured['views'][name]['input_sha256'] or read(source) != messages:
                raise ValueError('saved input differs from reconstruction')
        views, meta = build_origin_view(item)
        check = verify_edits(views['full_keep'].messages(), views['documentation_origin_keep'].messages(),
                             meta, item['prefix']['spans'])
        full = measured['views']['full_keep']['input_tokens']
        selected = measured['views']['documentation_origin_keep']['input_tokens']
        if (type(full) is not int or type(selected) is not int or min(full, selected) < 1
                or full != row['p42_full_input_tokens'] or full - selected != measured['input_tokens_removed']
                or measured['development_cost_gate_met'] != (full - selected >= 1000)):
            raise ValueError('recorded count or development gate differs')
        checked.append({'source_run': row['source_run'], 'inputs_reconstructed': len(outputs), **check})
    if report['additional_generation_design_gate'] != (sum(r['development_cost_gate_met'] for r in report['rows']) >= 2):
        raise ValueError('overall development gate differs')
    return {'phase': 'P44', 'report_sha256': sha(path), 'auditor_sha256': sha(Path(__file__)),
            'rows': checked, 'errors': [], 'additional_input_count_requests': 0,
            'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
            'quality_preservation_proven': False, 'future_irrelevance_proven': False,
            'scope': 'Exact saved-input reconstruction and permitted display edits under the restricted print grammar; no claim of general Python provenance or task-quality preservation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--storage-root', type=Path, required=True); args = parser.parse_args()
    target = args.repo_root / 'reports/P44_documentation_origin_integrity.json'
    if target.exists():
        raise FileExistsError('preserve earlier audit')
    report = audit(args.repo_root, args.storage_root)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print({'inputs_reconstructed': sum(r['inputs_reconstructed'] for r in report['rows']),
           'changed_outputs': sum(r['changed_outputs'] for r in report['rows']), 'errors': report['errors']})

"""Verify saved P42 inputs and allowed edits without generation or recounting."""
import argparse
import json
from pathlib import Path

from documentation_exposure import views
from handoff_factors import split_turns
from later_handoff_sources import prepare_later_sources
from native_conversation import recover_turn
from run_handoff_factors import sha
from run_context_comparison import write_json


def audit(root, storage):
    source = root / 'reports/P42_documentation_exposure.json'
    report = json.loads(source.read_text())
    if report['status'] != 'complete' or len(report['rows']) != 4:
        raise ValueError('require the complete four-boundary inspection')
    for name, digest in report['source_sha256'].items():
        if sha(root / name) != digest: raise ValueError('source changed: ' + name)
    _, original, _, _, prepared = prepare_later_sources(storage, root)
    folder = storage / 'records/context_pilot/P42_documentation_exposure_v01'
    checked, changed = [], 0
    for item, row in zip(prepared, report['rows'], strict=True):
        if item['source_run'] != row['source_run'] or item['boundary_manifest_sha256'] != row['boundary_manifest_sha256']:
            raise ValueError('boundary identity mismatch')
        proposed, meta = views(item['prefix'])
        if meta != row['selection']: raise ValueError('selection reconstruction differs')
        for name, conversation in proposed.items():
            path = folder / (item['source_run'] + '_' + name + '_private.json')
            messages, formatting = conversation.for_model(original['observation_page_characters'])
            saved = row['views'][name]
            if sha(path) != saved['input_sha256'] or json.loads(path.read_text()) != messages or formatting != saved['formatting']:
                raise ValueError('saved model input differs')
            checked.append({'source_run': item['source_run'], 'view': name, 'input_sha256': sha(path)})
        full = proposed['full_keep'].messages()
        selected = proposed['documentation_stdout_mask_keep'].messages()
        if full[:2] != selected[:2]: raise ValueError('system or task changed')
        pairs = list(zip(split_turns(full), split_turns(selected), strict=True))
        if pairs[-1][0] != pairs[-1][1]: raise ValueError('latest turn changed')
        selected_ids = {x['span_id'] for x in meta['checks'] if x['matched']}
        for before, after in pairs:
            if before[0] != after[0]: raise ValueError('assistant action changed')
            for old, new in zip(recover_turn(before), recover_turn(after), strict=True):
                if old == new: continue
                if old['id'] not in selected_ids: raise ValueError('non-selected result changed')
                changed += 1
                def without_stdout(span):
                    return {**span, 'observation': {k: v for k, v in span['observation'].items()
                                                   if k not in ('stdout', 'stdout_view')}}
                if without_stdout(old) != without_stdout(new): raise ValueError('non-stdout fields changed')
                if new['observation']['stdout_view']['source_span_id'] != old['id']:
                    raise ValueError('archive reference changed')
        full_count = row['views']['full_keep']['input_tokens']
        for name, key in (('documentation_stdout_mask_keep', 'documentation_input_tokens_removed'),
                          ('all_stdout_mask_keep', 'all_stdout_input_tokens_removed')):
            if full_count - row['views'][name]['input_tokens'] != row[key]: raise ValueError('arithmetic mismatch')
        if row['development_cost_gate_met'] != (row['documentation_input_tokens_removed'] >= 1000):
            raise ValueError('per-task gate mismatch')
    gate = sum(r['development_cost_gate_met'] for r in report['rows']) >= 2
    if gate != report['additional_generation_design_gate']: raise ValueError('gate mismatch')
    result = {'phase': 'P42', 'report_sha256': sha(source), 'auditor_sha256': sha(Path(__file__)),
              'inputs_reconstructed': checked, 'changed_outputs': changed, 'errors': [],
              'model_generations': 0, 'additional_input_count_requests': 0, 'environment_api_requests': 0,
              'evaluator_calls': 0, 'allowed_edits_and_archive_references_verified': True,
              'semantic_independence_or_future_irrelevance_proven': False}
    write_json(root / 'reports/P42_exposure_integrity.json', result)
    print({'inputs_reconstructed': len(checked), 'changed_outputs': changed, 'errors': []})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--repo-root', type=Path, required=True)
    p.add_argument('--storage-root', type=Path, required=True); a = p.parse_args()
    audit(a.repo_root, a.storage_root)

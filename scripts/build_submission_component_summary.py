"""Recompute the closed P103 public summaries and export every recorded unit."""
from datetime import datetime, timezone
import csv
import json
from pathlib import Path

from build_recorded_action_summary import csv_write, sha
from submission_components import compare, summarize

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'materials/20261025_p103_results'


def build():
    report_path = ROOT / 'reports/P103_submission_components.json'
    report = json.loads(report_path.read_text())
    original = json.loads((ROOT / 'reports/P98_recorded_action_agreement.json').read_text())
    if report['status'] != 'complete' or len(report['runs']) != 24 or len(report['pairs']) != 60:
        raise ValueError('all_original_units_required')
    for rel, expected in report['source_sha256'].items():
        if sha(ROOT / rel) != expected:
            raise ValueError('bound_source_changed:' + rel)
    inventory = []
    lookup = {}
    for run, old in zip(report['runs'], original['rows'], strict=True):
        for key in old.keys() - {'calls', 'private_record_sha256', 'private_response_sha256'}:
            if run[key] != old[key]:
                raise ValueError('original_run_metadata_changed')
        for call, before in zip(run['calls'], old['calls'], strict=True):
            for key in call.keys() - {'components'}:
                if call[key] != before[key]:
                    raise ValueError('original_generation_metadata_changed')
            component = call['components']
            if (component['public_output_sha256'] != before['response']['public_output_sha256']
                    or component['original_syntax_actions_sha256'] != before['response']['syntax_actions_sha256']):
                raise ValueError('original_fingerprint_changed')
            lookup[run['run_id'], call['ordinal']] = component
            inventory.append(dict(run_id=run['run_id'], task_id=run['task_id'],
                **{k: v for k, v in call.items() if k != 'components'}, **component))
    positions = []
    for pair, old in zip(report['pairs'], original['pairs'], strict=True):
        for key in old.keys() - {'rows'}:
            if pair[key] != old[key]:
                raise ValueError('original_pair_metadata_changed')
        for row, before in zip(pair['rows'], old['rows'], strict=True):
            expected = dict(**before, **compare(lookup.get((pair['left'], row['ordinal'])),
                lookup.get((pair['right'], row['ordinal'])), before))
            if row != expected:
                raise ValueError('public_component_comparison_disagrees')
            positions.append(dict(task_id=pair['task_id'], left=pair['left'], right=pair['right'], **row))
    all_rows = summarize(report['pairs'], report['runs'])
    matched = summarize(report['pairs'], report['runs'], matched_prefix_only=True)
    if (all_rows != report['all_aligned'] or matched != report['matched_prior_API_prefix']
            or len(inventory) != 426 or len(positions) != 1132
            or sum(c['known_total_tokens'] or 0 for c in inventory) != original['original_known_tokens']
            or sum(c['known_total_tokens'] is None for c in inventory) != 4
            or sum(c['API_requests'] for c in inventory) != original['original_API_requests']):
        raise ValueError('all_original_counts_and_costs_required')
    folder = ROOT / FOLDER
    folder.mkdir(exist_ok=False)
    csv_write(folder / 'all_426_recorded_calls.csv', inventory)
    csv_write(folder / 'all_1132_aligned_positions.csv', positions)
    csv_write(folder / 'all_24_runs.csv', [{k: v for k, v in r.items() if k != 'calls'} for r in report['runs']])
    csv_write(folder / 'all_60_pairs.csv', [dict(task_id=p['task_id'], left=p['left'], right=p['right'],
        all_aligned=summarize([p], report['runs']),
        matched_prior_API_prefix=summarize([p], report['runs'], matched_prefix_only=True)) for p in report['pairs']])
    for name, expected in [('all_426_recorded_calls.csv', 426), ('all_1132_aligned_positions.csv', 1132),
                           ('all_24_runs.csv', 24), ('all_60_pairs.csv', 60)]:
        with (folder / name).open(newline='') as stream:
            if len(list(csv.DictReader(stream))) != expected:
                raise ValueError('exported_inventory_changed')
    summary = dict(generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=sha(report_path), builder_sha256=sha(Path(__file__)),
        all_aligned=all_rows, matched_prior_API_prefix=matched,
        original_generations=426, original_known_tokens=original['original_known_tokens'],
        original_unknown_usage_calls=4, original_API_requests=original['original_API_requests'],
        private_analysis_wall_seconds=report['wall_seconds'],
        public_verification_scope='Published hashes, comparisons, metadata and arithmetic; not a private reanalysis or a semantic-equivalence proof.',
        additional_private_record_reads=0, model_generations=0, environment_API_requests=0,
        saved_code_executions=0, evaluations=0, reserved_scenarios_read=0,
        P101_intermediate_results_read=False, novel_method_established=False)
    with (folder / 'summary.json').open('x') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(folder=FOLDER, all_aligned=all_rows, matched_prior_API_prefix=matched)))


if __name__ == '__main__':
    build()

"""Render all eight P125 conditions from closed, hash-bound public artifacts.

Preparation of this renderer does not inspect a running experiment. The loader
requires the closed audit, stopped server record and published material bundle.
No model, tokenizer, API, evaluator or generated task code is invoked.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator

POLICIES = ('eager_cached', 'automatic_projection_cached')
LABELS = ('Eager + ordinary cache', 'Automatic projection + ordinary cache')
TASKS = ('Photo', 'Expenses', 'Refund', 'CSV')
COLORS = ('#4477AA', '#228877')
MATERIALS = 'materials/20261026_p125_results'
REPORT = 'reports/P125_comparison.json'
SESSION = 'reports/P125_server_session.json'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def count(value):
    return type(value) is int and value >= 0


def key(row):
    match = re.fullmatch(r'BOC_P125_0([1-4])_(EAGER_CACHED|AUTOMATIC_PROJECTION_CACHED)', row['run_id'])
    require(match is not None, 'fixed_P125_identity_required')
    require(row['projection_policy'] == match.group(2).lower(), 'policy_identity_differs')
    return int(match.group(1)), row['projection_policy']


def aggregate_counts(rows):
    known = [r['known_total_tokens'] for r in rows if r['known_total_tokens'] is not None]
    unknown = [r['unknown_usage_calls'] for r in rows if r['unknown_usage_calls'] is not None]
    exact = bool(rows) and len(known) == len(unknown) == len(rows) and sum(unknown) == 0
    return {'planned_conditions': len(rows), 'accounted_conditions': len(known),
        'evaluated_conditions': sum(r['record_status'] == 'evaluated' for r in rows),
        'successful_conditions': sum(r['success'] is True for r in rows),
        'known_token_subtotal': sum(known), 'recorded_unknown_usage_calls': sum(unknown),
        'unknown_usage_count_missing_conditions': len(rows) - len(unknown),
        'exact_total_tokens': sum(known) if exact else None, 'all_condition_usage_known': exact}


def verify_aggregates(rows, summary, error_count):
    indexed = {key(r): r for r in rows}
    task_ids = []
    common = set()
    losses = 0
    for number in range(1, 5):
        pair = [indexed[(number, policy)] for policy in POLICIES]
        require(pair[0]['task_id'] == pair[1]['task_id'], 'paired_task_ids_differ')
        task_ids.append(pair[0]['task_id'])
        if all(r['success'] is True for r in pair):
            common.add(number)
        losses += int(pair[0]['success'] is True and pair[1]['success'] is False)
    require(len(set(task_ids)) == 4, 'four_distinct_tasks_required')
    require(summary['common_successful_tasks'] == len(common), 'common_success_count_differs')
    require(set(summary['by_policy']) == set(summary['common_success_costs_by_policy']) == set(POLICIES),
            'fixed_policy_totals_required')
    groups = [(rows, summary['all_conditions'])]
    for policy in POLICIES:
        groups.append(([r for r in rows if r['projection_policy'] == policy], summary['by_policy'][policy]))
        groups.append(([r for r in rows if r['projection_policy'] == policy and key(r)[0] in common],
                       summary['common_success_costs_by_policy'][policy]))
    for subset, supplied in groups:
        require(all(supplied.get(k) == v for k, v in aggregate_counts(subset).items()),
                'row_derived_aggregate_differs')
    complete = all(r['record_status'] == 'evaluated' and r['unknown_usage_calls'] == 0
                   and r['known_total_tokens'] is not None for r in rows)
    contracts_intact = all(r['projection_contract_failed'] is False for r in rows)
    hits = [indexed[(n, POLICIES[1])]['projection_hits'] for n in common]
    activated = bool(common) and all(count(v) for v in hits) and sum(hits) >= 1
    total_delta = sum(indexed[(n, POLICIES[1])]['known_total_tokens'] -
                      indexed[(n, POLICIES[0])]['known_total_tokens'] for n in range(1, 5)) if complete else None
    common_delta = sum(indexed[(n, POLICIES[1])]['known_total_tokens'] -
                       indexed[(n, POLICIES[0])]['known_total_tokens'] for n in common) if complete else None
    expected_gate = bool(complete and error_count == 0 and losses == 0 and total_delta < 0
                         and common_delta < 0 and activated and contracts_intact)
    require(summary['audited_criteria'].get('development_gate_met') is expected_gate,
            'row_derived_fixed_gate_differs')


def load_closed(root):
    root = Path(root).resolve()
    names = [REPORT, SESSION, MATERIALS + '/summary.json',
             MATERIALS + '/conditions.csv', MATERIALS + '/build_manifest.json']
    paths = {name: root / name for name in names}
    require(all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root)
                for p in paths.values()), 'closed_public_artifacts_required')
    hashes = {name: sha(path) for name, path in paths.items()}
    report, session, summary, manifest = [json.loads(paths[name].read_text()) for name in
        (REPORT, SESSION, MATERIALS + '/summary.json', MATERIALS + '/build_manifest.json')]
    require(report.get('phase') == session.get('phase') == summary.get('phase') == manifest.get('phase') == 'P125',
            'P125_phase_required')
    require(report.get('batch_status') in ('complete', 'stopped')
            and report.get('owned_processes_absent') is True
            and session.get('status') == 'stopped' and session.get('owned_processes_absent') is True,
            'closed_batch_and_stopped_owned_server_required')
    require(session.get('audit_source_sha256') == hashes[REPORT], 'session_audit_binding_differs')
    require(all(manifest['source_sha256'].get(name) == hashes[name] for name in (REPORT, SESSION)),
            'material_source_binding_differs')
    require(all(manifest['artifact_sha256'].get(name) == hashes[MATERIALS + '/' + name]
                for name in ('summary.json', 'conditions.csv')), 'material_artifact_hash_differs')
    errors = report.get('audit_errors')
    require(type(errors) is list and summary.get('audit_error_count') == len(errors), 'audit_error_count_differs')
    require(type(summary.get('audited_criteria')) is dict and
            all(report.get(k) == v for k, v in summary['audited_criteria'].items()), 'audited_criteria_differ')
    with paths[MATERIALS + '/conditions.csv'].open(newline='') as handle:
        csv_rows = list(csv.DictReader(handle))
    rows = summary['conditions']
    raw_rows = report['rows']
    expected = {(n, p) for n in range(1, 5) for p in POLICIES}
    require(all(len(group) == 8 and {key(r) for r in group} == expected
                for group in (rows, raw_rows, csv_rows)), 'all_eight_slots_required')
    csv_by_key, raw_by_key = ({key(r): r for r in group} for group in (csv_rows, raw_rows))
    data = []
    audit_fields = ('run_id', 'task_id', 'projection_policy', 'checkpoint_policy', 'record_status',
                    'success', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                    'projection_hits', 'projection_contract_failed')
    for row in rows:
        number, policy = key(row)
        other, raw = csv_by_key[(number, policy)], raw_by_key[(number, policy)]
        require(set(other) == set(row) and all(other[k] == ('' if v is None else str(v))
                                               for k, v in row.items()), 'all_csv_fields_must_match_materials')
        require(all(raw.get(k) == row.get(k) for k in audit_fields), 'audit_row_differs')
        require(row['checkpoint_policy'] == 'single_checkpoint', 'fixed_common_checkpoint_required')
        status, success = row['record_status'], row['success']
        require(status in ('evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error'),
                'known_status_required')
        require(type(success) is bool if status == 'evaluated' else success is None,
                'official_evaluation_status_required')
        if status not in ('evaluated', 'unevaluated'):
            require(all(row.get(k) is None for k in ('known_total_tokens', 'unknown_usage_calls',
                'exact_total_tokens', 'api_requests', 'projection_hits', 'projection_contract_failed')),
                'unaccounted_slot_cannot_gain_zero_measurements')
        for field in ('known_total_tokens', 'unknown_usage_calls', 'api_requests', 'projection_hits'):
            require(row[field] is None or count(row[field]), 'nonnegative_count_or_unknown_required')
        known, unknown = row['known_total_tokens'], row['unknown_usage_calls']
        exact = known if known is not None and unknown == 0 else None
        require(row['exact_total_tokens'] == exact, 'exact_total_must_remain_unknown_if_usage_missing')
        require(row['projection_contract_failed'] is None or type(row['projection_contract_failed']) is bool,
                'explicit_contract_flag_or_unknown_required')
        data.append({'task_number': number, 'task_label': TASKS[number - 1], 'policy': policy,
            'known_logical_tokens': known, 'exact_logical_tokens': exact, 'unknown_usage_calls': unknown,
            'record_status': status, 'success': success,
            'evaluation_label': 'Success' if success is True else 'Failure' if success is False else 'Not evaluated',
            'api_requests': row['api_requests'], 'projection_hits': row['projection_hits'],
            'projection_contract_failed': row['projection_contract_failed']})
    verify_aggregates(rows, summary, len(errors))
    data.sort(key=lambda r: (r['task_number'], POLICIES.index(r['policy'])))
    known_sum = sum(r['known_logical_tokens'] for r in data if r['known_logical_tokens'] is not None)
    all_exact = all(r['exact_logical_tokens'] is not None for r in data)
    total = summary['all_conditions']
    require(total['planned_conditions'] == 8 and total['known_token_subtotal'] == known_sum
            and total['exact_total_tokens'] == (known_sum if all_exact else None), 'all_condition_total_differs')
    figure_data = {'phase': 'P125', 'fixed_slots': 8, 'rows': data, 'audit_error_count': len(errors),
        'known_logical_token_subtotal': known_sum, 'exact_all_condition_tokens': known_sum if all_exact else None,
        'audited_criteria': summary['audited_criteria'], 'by_policy': summary['by_policy'],
        'common_successful_tasks': summary['common_successful_tasks'],
        'common_success_costs_by_policy': summary['common_success_costs_by_policy'],
        'unknown_usage_is_not_zero': True, 'outcome_based_selection': False,
        'general_quality_preservation_claim': False, 'novel_method_claim': False}
    require(all(sha(paths[name]) == value for name, value in hashes.items()), 'sources_changed_while_reading')
    return figure_data, hashes


def render(data, output):
    rows = data['rows']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(2, 1, figsize=(12.5, 10.3))
    width = 0.34
    for panel, field in enumerate(('known_logical_tokens', 'api_requests')):
        ax = axes[panel]
        maximum = max([r[field] or 0 for r in rows] + [1])
        for row in rows:
            method = POLICIES.index(row['policy'])
            x = row['task_number'] - 1 + (method - 0.5) * width
            value = row[field]
            incomplete = panel == 0 and row['exact_logical_tokens'] is None
            if value is None:
                ax.plot(x, 0, marker='x', color=COLORS[method], markersize=8, markeredgewidth=1.8)
                label = 'Not\nmeasured'
            else:
                ax.bar(x, value, width=width * 0.86, color=COLORS[method], edgecolor='#263238',
                       linewidth=0.55, hatch='///' if incomplete else None, zorder=3)
                label = f'{value:,}' + (' known' if incomplete else '')
            if panel == 0:
                label += '\n' + row['evaluation_label'].replace('Not evaluated', 'Not\nevaluated')
                if incomplete and value is not None:
                    label += '\nUsage incomplete'
                if row['projection_contract_failed'] is True:
                    label += '\nContract stop'
            else:
                hits = row['projection_hits']
                label += '\nPartial hits: ' + ('\nunknown' if hits is None else str(hits))
            ax.text(x, (value or 0) + maximum * 0.023, label, ha='center', va='bottom',
                    fontsize=8.8, linespacing=1.25)
        ax.set_xticks(range(4), TASKS)
        ax.set_xlim(-0.6, 3.6)
        ax.set_ylim(0, maximum * (1.42 if panel == 0 else 1.28))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        if panel == 0:
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v / 1000:,.0f}k'))
        ax.set_ylabel('Logical input + output tokens' if panel == 0 else 'Dispatched API requests')
        ax.yaxis.grid(True, alpha=0.2)
        ax.set_axisbelow(True)
    handles = [Patch(facecolor=color, edgecolor='#263238', label=label)
               for color, label in zip(COLORS, LABELS)]
    if any(r['known_logical_tokens'] is not None and r['exact_logical_tokens'] is None for r in rows):
        handles.append(Patch(facecolor='white', edgecolor='#263238', hatch='///', label='Known subtotal only'))
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.925), frameon=False, ncol=2)
    fig.suptitle('P125 — Whole-job cost, outcomes and mechanism use', fontsize=17, y=0.98)
    fig.text(0.5, 0.944, 'All 4 development tasks × both fixed policies; one seed; common single checkpoint',
             ha='center', fontsize=10.5)
    gate = data['audited_criteria'].get('development_gate_met')
    note = ('All model roles, summaries, failures and recovery are included in logical tokens. '
            'API requests and partial hits are separate counts, not tokens.\n'
            'Partial hits do not equal net backend savings: later full reads and ordinary cache reuse can offset them.\n'
            'Cheap failures do not establish quality-preserving savings. These development runs give no general quality or novelty guarantee.\n'
            f'Audited adoption gate: {gate}. Audit errors: {data["audit_error_count"]}. '
            'All conditions are retained, including incomplete and unevaluated conditions.')
    fig.text(0.075, 0.025, note, fontsize=8.7, linespacing=1.55)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.86, bottom=0.17, hspace=0.30)
    for extension in ('svg', 'png', 'pdf'):
        fig.savefig(output / f'p125_cost_outcomes.{extension}', dpi=220,
                    metadata={'Creator': 'draw_p125_results_20261026.py'})
    plt.close(fig)


def main(repo_root, output_dir):
    data, hashes = load_closed(repo_root)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    render(data, output)
    (output / 'figure_data.json').write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    (output / 'README.md').write_text('''# P125 figure: all eight conditions

The upper panel shows whole-job logical input plus output tokens, including all roles, summaries, failures and recovery. Every predefined task and policy is present, with its audited official outcome. Hatched bars denote known subtotals with incomplete usage. An x marked "Not measured" is missing data, not zero cost. Contract stops retain the independent evaluation result and are explicitly marked.

The lower panel shows dispatched API requests and separately labels partial hits. A hit is not a net saved request: ordinary complete cache reuse and later full reads can offset it. Neither API counts nor control bytes are model tokens. The all-condition and common-success totals, original adoption criteria and audit-error count are retained in figure_data.json.

This is one known-task development comparison with a single common checkpoint. It does not establish statistical non-inferiority, general quality preservation, superiority over rolling-separate checkpoints, or technical novelty. No result was selected or omitted according to outcome. The renderer only reads closed public audit and server artifacts plus their hash-bound material bundle. It makes no model, API, tokenizer or evaluator calls.
''')
    manifest = {'phase': 'P125', 'source_sha256': hashes, 'drawing_script_sha256': sha(__file__),
        'artifact_sha256': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        'matplotlib_version': matplotlib.__version__, 'all_eight_conditions_retained': True,
        'closed_public_audit_and_session_verified': True, 'outcome_based_selection': False,
        'new_model_calls': 0, 'new_API_requests': 0, 'new_tokenizer_calls': 0, 'new_evaluations': 0,
        'private_task_values_or_generated_programs_read': False}
    require(all(sha(Path(repo_root) / name) == digest for name, digest in hashes.items()),
            'sources_changed_during_render')
    (output / 'source_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'conditions': len(data['rows']), 'output_directory': str(output), 'source_sha256': hashes}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(main(args.repo_root, args.output_dir)))

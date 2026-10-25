"""Redraw the fixed 12-slot P123 figure from closed public audit artifacts.

This script reads audited public aggregates only. It never opens private task
data, model traces, generated code, evaluator contents, or an inference backend.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator


POLICIES = ('single_checkpoint', 'rolling_separate', 'rolling_inline')
LABELS = ('single', 'rolling separate', 'rolling inline')
TASKS = ('Photo', 'Expenses', 'Refund', 'CSV')
COLORS = ('#4477AA', '#EE9933', '#228877')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_key(row):
    match = re.fullmatch(r'BOC_P123_0([1-4])_(SINGLE_CHECKPOINT|ROLLING_SEPARATE|ROLLING_INLINE)', row['run_id'])
    require(match is not None, 'expected_fixed_P123_cell_identifier')
    policy = row['checkpoint_policy']
    require(policy == match.group(2).lower() and policy in POLICIES, 'cell_policy_disagrees')
    return int(match.group(1)), policy


def main(repo_root, output_dir, initial_evidence):
    ROOT = Path(repo_root).resolve()
    OUT = Path(output_dir).resolve()
    MATERIALS = ROOT / 'materials/20261025_p123_results'
    evidence_path = Path(initial_evidence).resolve()
    evidence = json.loads(evidence_path.read_text())
    require(evidence.get('phase') == 'P123' and evidence.get('initial_render') == 'v01'
            and evidence.get('initial_render_verified_after_collector_closed') is True,
            'initial_render_provenance_required')
    require(set(evidence) == {'phase', 'initial_render', 'initial_collector_end_sha256',
        'initial_manifest_sha256', 'initial_drawing_script_sha256', 'initial_figure_data_sha256',
        'initial_PNG_sha256', 'initial_render_verified_after_collector_closed', 'private_path_names_published'}
        and all(re.fullmatch('[0-9a-f]{64}', value) for key, value in evidence.items() if key.endswith('_sha256'))
        and evidence['private_path_names_published'] is False, 'hash_only_initial_provenance_required')
    OUT.mkdir(parents=True, exist_ok=True)
    destinations = [OUT / name for name in (
        'p123_logical_tokens.svg', 'p123_logical_tokens.png', 'p123_logical_tokens.pdf',
        'figure_data.json', 'source_manifest.json', 'interpretation_note.md')]
    require(not any(path.exists() for path in destinations), 'preserve_existing_figures')
    report_path = ROOT / 'reports/P123_comparison.json'
    report = json.loads(report_path.read_text())
    session_path = ROOT / 'reports/P123_server_session.json'
    session = json.loads(session_path.read_text())
    require(session.get('phase') == 'P123' and session.get('owned_processes_absent') is True
            and session.get('audit_source_sha256') == sha(report_path), 'closed_session_audit_binding_required')
    material_summary = json.loads((MATERIALS / 'summary.json').read_text())
    manifest = json.loads((MATERIALS / 'build_manifest.json').read_text())
    require(report.get('phase') == material_summary.get('phase') == 'P123'
            and report.get('owned_processes_absent') is True
            and not report.get('audit_errors') and report.get('batch_status') in ('complete', 'stopped'),
            'closed_P123_audit_required')
    require(manifest['source_sha256']['reports/P123_comparison.json'] == sha(report_path),
            'material_source_does_not_match_audit')
    require(manifest['source_sha256']['reports/P123_server_session.json'] == sha(session_path),
            'material_session_source_does_not_match')
    for name in ('summary.json', 'all_conditions.csv'):
        require(manifest['artifact_sha256'][name] == sha(MATERIALS / name), 'material_hash_changed')
    with (MATERIALS / 'all_conditions.csv').open() as handle:
        csv_rows = list(csv.DictReader(handle))
    rows = report['rows']
    expected = {(task, policy) for task in range(1, 5) for policy in POLICIES}
    require(len(rows) == len(csv_rows) == 12
            and {row_key(row) for row in rows} == expected
            and {row_key(row) for row in csv_rows} == expected, 'all_twelve_fixed_slots_required')
    csv_by_key = {row_key(row): row for row in csv_rows}
    data = []
    for row in rows:
        number, policy = row_key(row)
        other = csv_by_key[(number, policy)]
        for field in ('known_total_tokens', 'unknown_usage_calls', 'success', 'record_status'):
            expected_text = '' if row.get(field) is None else str(row[field])
            require(other[field] == expected_text, 'csv_audit_value_disagrees')
        known, unknown, success = (row.get(field) for field in
                                   ('known_total_tokens', 'unknown_usage_calls', 'success'))
        require(known is None or type(known) is int and known >= 0, 'invalid_known_subtotal')
        require(unknown is None or type(unknown) is int and unknown >= 0, 'invalid_unknown_usage_count')
        require(success is None or type(success) is bool, 'invalid_evaluation_status')
        require((row['record_status'] == 'evaluated') == (type(success) is bool),
                'evaluation_status_mismatch')
        data.append({'task_number': number, 'task_label': TASKS[number - 1],
            'policy': policy, 'method_label': LABELS[POLICIES.index(policy)],
            'known_logical_tokens': known, 'unknown_usage_calls': unknown,
            'exact_logical_tokens': known if known is not None and unknown == 0 else None,
            'record_status': row['record_status'],
            'evaluation_label': 'Success' if success is True else 'Failure' if success is False else 'Not evaluated'})
    data.sort(key=lambda row: (row['task_number'], POLICIES.index(row['policy'])))
    known_sum = sum(row['known_logical_tokens'] for row in data if row['known_logical_tokens'] is not None)
    all_exact = all(row['exact_logical_tokens'] is not None for row in data)
    require(material_summary['recorded_known_tokens'] == known_sum
            and material_summary['exact_all_condition_tokens'] == (known_sum if all_exact else None),
            'material_total_disagrees')

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none'})
    fig, ax = plt.subplots(figsize=(13.4, 7.2))
    width = 0.245
    maximum = max([row['known_logical_tokens'] or 0 for row in data] + [1])
    offset = maximum * 0.018
    for row in data:
        method = POLICIES.index(row['policy'])
        x = row['task_number'] - 1 + (method - 1) * width
        known = row['known_logical_tokens']
        incomplete = row['exact_logical_tokens'] is None
        if known is None:
            ax.plot(x, 0, marker='x', color=COLORS[method], markersize=8, markeredgewidth=1.8)
            label = 'Not measured\n' + row['evaluation_label']
        else:
            ax.bar(x, known, width=width * 0.88, color=COLORS[method],
                   edgecolor='#263238', linewidth=0.55, hatch='///' if incomplete else None,
                   zorder=3)
            label = f'{known:,}' + (' known' if incomplete else '') + '\n' + row['evaluation_label']
            if incomplete:
                label += '\nUsage incomplete'
        ax.text(x, (known or 0) + offset, label, ha='center', va='bottom',
                fontsize=8.5, linespacing=1.25, color='#182028')
    ax.set_xticks(range(4), TASKS, fontsize=12)
    ax.tick_params(axis='x', length=0, pad=10)
    ax.set_xlim(-0.6, 3.6)
    ax.set_ylim(0, maximum * 1.29)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value / 1000:,.0f}k'))
    ax.set_ylabel('Logical tokens: input + output, all roles', labelpad=10)
    ax.yaxis.grid(True, alpha=0.2, zorder=0)
    ax.set_axisbelow(True)
    handles = [Patch(facecolor=color, edgecolor='#263238', label=label)
               for color, label in zip(COLORS, LABELS)]
    if any(row['exact_logical_tokens'] is None for row in data):
        handles.append(Patch(facecolor='white', edgecolor='#263238', hatch='///',
                             label='Known subtotal; usage incomplete'))
    ax.legend(handles=handles, frameon=False, ncol=4, loc='upper center',
              bbox_to_anchor=(0.5, 1.08), fontsize=10)
    fig.suptitle('P123 — Whole-job logical tokens and task outcomes', fontsize=17,
                 fontweight='semibold', y=0.97)
    fig.text(0.5, 0.92, 'All 4 development tasks × all 3 methods; no outcome-based selection',
             ha='center', fontsize=10.5, color='#424B54')
    note = ('Tokens include task, summary, failure, and recovery work. Bars show the recorded known subtotal; '
            'incomplete usage is never an exact total.\n'
            'Outcome labels are audited official results. Lower tokens on a failed task do not establish a quality-preserving saving.\n'
            'One fixed development run per task and method; no uncertainty interval, general quality guarantee, or novelty claim.')
    fig.text(0.075, 0.035, note, ha='left', va='bottom', fontsize=8.7,
             color='#424B54', linespacing=1.5)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.80, bottom=0.21)
    for extension in ('svg', 'png', 'pdf'):
        fig.savefig(OUT / f'p123_logical_tokens.{extension}', dpi=220,
                    metadata={'Creator': 'draw_p123_tokens.py'})
    plt.close(fig)
    (OUT / 'figure_data.json').write_text(json.dumps({'phase': 'P123', 'rows': data,
        'recorded_known_tokens': known_sum, 'exact_all_condition_tokens': known_sum if all_exact else None,
        'fixed_slots': 12, 'unknown_usage_is_not_zero': True}, indent=2) + '\n')
    require(sha(OUT / 'figure_data.json') == evidence['initial_figure_data_sha256'],
            'portable_figure_data_differs_from_initial_render')
    (OUT / 'interpretation_note.md').write_text('''# P123 figure interpretation

The figure retains all 12 predefined conditions: Photo, Expenses, Refund, and CSV under single, rolling separate, and rolling inline. Task aliases follow the fixed task order (01–04); no task data is reproduced.

Bar height is recorded logical input plus output tokens across all roles, including summary, failed, and recovery work. An exact total is asserted only when recorded usage is complete. Hatched bars are known subtotals with incomplete usage. An unmeasured condition receives an x marker at the baseline and an explicit label, not an invented zero-token bar. Success, Failure, and Not evaluated are shown for every condition.

Differences can reflect changed execution, failure, or completion as well as history size. A cheap failure cannot establish a quality-preserving token reduction. The four known tasks and one fixed run per method do not establish general quality preservation, statistical non-inferiority, or technical novelty. No condition was selected or removed based on outcome. This is a descriptive reference figure, not a manuscript claim.

The portable plotting script reads only the closed public audit and server record, material summary, condition table, material manifest, and hash-only provenance of the initial rendering. The private collector marker is not required to redraw this figure; its initial SHA-256 is retained as provenance. It performs no model, API, tokenizer, or evaluator call. The source hashes and aggregate figure data are saved alongside the figure. SVG/PDF are vector outputs; PNG is a 220 dpi preview.
''')
    paths = [report_path, session_path, MATERIALS / 'summary.json', MATERIALS / 'all_conditions.csv',
             MATERIALS / 'build_manifest.json']
    output_files = [path for path in OUT.iterdir() if path.is_file() and path.name != 'source_manifest.json']
    source_manifest = {'phase': 'P123', 'render_version': 'portable_v02',
        'source_sha256': {path.relative_to(ROOT).as_posix(): sha(path) for path in paths},
        'drawing_script_sha256': sha(Path(__file__)), 'initial_evidence_sha256': sha(evidence_path),
        'initial_render_evidence': evidence,
        'artifact_sha256': {path.name: sha(path) for path in sorted(output_files)},
        'matplotlib_version': matplotlib.__version__, 'all_twelve_conditions_retained': True,
        'new_model_calls': 0, 'new_API_requests': 0, 'new_tokenizer_calls': 0, 'new_evaluations': 0,
        'private_task_values_or_generated_programs_read': False,
        'closed_public_audit_and_session_verified': True, 'private_collector_required_to_redraw': False,
        'portable_figure_data_matches_initial_render': True}
    (OUT / 'source_manifest.json').write_text(json.dumps(source_manifest, indent=2) + '\n')
    print(json.dumps({'output_directory': str(OUT), 'conditions': len(data),
        'audit_source_sha256': sha(report_path), 'all_usage_complete': all_exact}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--initial-evidence', type=Path,
                        default=Path(__file__).with_name('initial_render_evidence.json'))
    arguments = parser.parse_args()
    main(arguments.repo_root, arguments.output_dir, arguments.initial_evidence)

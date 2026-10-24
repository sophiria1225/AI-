"""All P111 conditions and P112 accounting components, with missing costs explicit."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

POLICIES = ('full', 'recent', 'execution_gated')
LABELS = {'full': 'Full', 'recent': 'Recent', 'execution_gated': 'Execution gated'}
TASKS = {
    '34d9492_1': 'Photos', '3c13f5a_1': 'Expense splitting',
    '60d0b5b_1': 'Refund', '6104387_1': 'CSV export',
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def success_label(value):
    return 'success' if value is True else 'failed' if value is False else 'not evaluated'


def sources(root):
    paths = {
        'audit': root/'reports/P111_comparison.json',
        'session': root/'reports/P111_server_session.json',
        'diagnosis': root/'reports/P112_realized_history_inputs.json',
        'plan': root/'configs/P112_realized_history_inputs_v01.json',
    }
    data = {name: read(path) for name, path in paths.items()}
    audit, session, diagnosis, plan = (data[k] for k in ('audit', 'session', 'diagnosis', 'plan'))
    require(not audit['audit_errors'] and audit['owned_processes_absent']
            and audit['batch_status'] in ('complete', 'stopped')
            and session['status'] == 'stopped' and session['owned_processes_absent']
            and session['audit_source_sha256'] == sha(paths['audit']), 'closed_audited_P111_required')
    expected = {(task, policy) for task in TASKS for policy in POLICIES}
    keys = [(row['task_id'], row['reasoning_display_policy']) for row in audit['rows']]
    require(len(keys) == len(set(keys)) == 12 and set(keys) == expected, 'all_twelve_conditions_required')
    require(diagnosis['source_audit_sha256'] == sha(paths['audit'])
            and diagnosis['plan_sha256'] == sha(paths['plan'])
            and len(diagnosis['rows']) == plan['planned_renderings'], 'bound_P112_report_required')
    lookup = {row['run_id']: row for row in audit['rows']}
    require(len(diagnosis['cells']) == 12
            and {cell['run_id'] for cell in diagnosis['cells']} == set(lookup), 'all_P112_conditions_required')
    for cell in diagnosis['cells']:
        row = lookup[cell['run_id']]
        require(cell['task_id'] == row['task_id']
                and cell['actual_policy'] == row['reasoning_display_policy']
                and cell['actual_success'] is row['success']
                and cell['actual_known_total_tokens'] == row.get('known_total_tokens')
                and cell['actual_unknown_usage_calls'] == row.get('unknown_usage_calls'),
                'original_condition_labels_changed')
    return data, {str(path.relative_to(root)): sha(path) for path in paths.values()}


def save(fig, folder, name):
    for extension in ('png', 'pdf', 'svg'):
        fig.savefig(folder/(name+'.'+extension), dpi=180, facecolor='white')


def costs_figure(audit, folder, plt, Patch):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5))
    rows = {(row['task_id'], row['reasoning_display_policy']): row for row in audit['rows']}
    maximum = max((row.get('known_total_tokens') or 0)/1000 for row in audit['rows'])
    limit = max(1, maximum)*1.32
    for ax, (task, title) in zip(axes.flat, TASKS.items(), strict=True):
        for position, policy in enumerate(POLICIES):
            row = rows[task, policy]
            recorded = row['record_status'] in ('evaluated', 'unevaluated')
            if not recorded:
                ax.text(position, limit*.08, row['record_status'].replace('_', '\n'),
                        ha='center', va='bottom', color='#596575', fontsize=9)
                continue
            inputs = row['input_tokens']/1000
            outputs = row['output_tokens']/1000
            require(row['known_total_tokens'] == row['input_tokens']+row['output_tokens'],
                    'known_cost_components_disagree')
            unknown = row['unknown_usage_calls'] != 0
            hatch = '///' if unknown else None
            ax.bar(position, inputs, width=.6, color='#4676a8', edgecolor='#274665', hatch=hatch)
            ax.bar(position, outputs, bottom=inputs, width=.6, color='#e6a24b',
                   edgecolor='#825319', hatch=hatch)
            amount = f"{row['known_total_tokens']:,}"+(' + ?' if unknown else '')
            text = amount+'\n'+success_label(row['success'])
            if unknown:
                text += f"\n{row['unknown_usage_calls']} unknown usage"
            ax.text(position, inputs+outputs+limit*.025, text, ha='center', va='bottom', fontsize=9)
        ax.set_title(title+'  /  '+task, loc='left', fontsize=12, fontweight='bold')
        ax.set_xticks(range(3), [LABELS[p] for p in POLICIES], fontsize=10)
        ax.set_xlim(-.6, 2.6)
        ax.set_ylim(0, limit)
        ax.set_ylabel('Logical input + output tokens (thousands)')
        ax.grid(axis='y', alpha=.22)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('P111: whole-task cost and final outcome', fontsize=17, fontweight='bold', y=.98)
    fig.legend(handles=[Patch(facecolor='#4676a8', label='Input, including cached input'),
                        Patch(facecolor='#e6a24b', label='Output'),
                        Patch(facecolor='white', edgecolor='#596575', hatch='///', label='Known subtotal; total unknown')],
               loc='upper center', bbox_to_anchor=(.5,.94), ncol=3, frameon=False, fontsize=9)
    fig.text(.06, .025, 'Four known tasks; one run per policy. All 12 conditions retained. '
             'Unrun conditions have no cost bar.\n'
             'Short or failed runs do not establish savings with preserved quality. Unknown usage is not zero.',
             fontsize=10, color='#394452')
    fig.tight_layout(rect=(0,.09,1,.90))
    save(fig, folder, 'P111_all_conditions')
    plt.close(fig)


def decomposition_figure(audit, diagnosis, folder, plt, Patch, Line2D):
    expected = [(task, policy) for task in TASKS for policy in POLICIES[1:]]
    rows = diagnosis.get('accounting_decompositions', [])
    lookup = {(row['task_id'], row['actual_policy']): row for row in rows}
    require(len(rows) == len(lookup), 'duplicate_decomposition')
    require(not rows or set(lookup) == set(expected), 'all_eight_decompositions_required')
    actual = {(row['task_id'], row['reasoning_display_policy']): row for row in audit['rows']}
    values = [0.0]
    for row in rows:
        if row['all_logical_usage_known']:
            total = row['observed_cost_difference_from_full']
            omitted = row['local_input_omission_on_candidate_path']
            remainder = row['remainder_after_adding_back_local_omission']
            require(total == -omitted+remainder and row['remainder_is_not_a_causal_effect'] is True,
                    'accounting_identity_changed')
            values += [-omitted/1000, remainder/1000, total/1000]
    low, high = min(values), max(values)
    padding = max(1, high-low)*.22
    fig, ax = plt.subplots(figsize=(13, 8))
    labels = []
    for position, (task, policy) in enumerate(expected):
        row = lookup.get((task, policy))
        baseline = actual[task, 'full']
        candidate = actual[task, policy]
        labels.append(TASKS[task]+' / '+LABELS[policy]+'\n'
                      +success_label(baseline['success'])+' -> '+success_label(candidate['success']))
        if row is None or not row['all_logical_usage_known']:
            label = 'Diagnosis incomplete' if row is None else 'Whole-task difference unknown'
            ax.text(0, position, label, ha='left', va='center', fontsize=9, color='#596575',
                    bbox={'facecolor':'white', 'edgecolor':'none', 'alpha':.9})
            continue
        for offset, field, color, sign in (
            (-.16, 'local_input_omission_on_candidate_path', '#329285', -1),
            (.16, 'remainder_after_adding_back_local_omission', '#b695c8', 1),
        ):
            ax.barh(position+offset, sign*row[field]/1000, height=.27, color=color)
        ax.plot(row['observed_cost_difference_from_full']/1000, position,
                marker='D', color='#222a35', markersize=5, linestyle='none')
    ax.set_yticks(range(8), labels, fontsize=10)
    ax.set_ylim(7.65, -.65)
    ax.set_xlim(low-padding, high+padding)
    ax.axvline(0, color='#596575', linewidth=.8)
    ax.grid(axis='x', alpha=.2)
    ax.set_axisbelow(True)
    ax.spines[['top','right']].set_visible(False)
    ax.set_xlabel('Difference from full policy (thousands of logical tokens)')
    fig.suptitle('P112: local display omission and whole-task difference',
                 fontsize=16, fontweight='bold', y=.98)
    fig.legend(handles=[Patch(facecolor='#329285', label='-D: same-path input omission'),
                        Patch(facecolor='#b695c8', label='R: accounting remainder'),
                        Line2D([], [], color='#222a35', marker='D', linestyle='none', label='Observed difference = -D + R')],
               loc='upper center', bbox_to_anchor=(.5,.94), ncol=3, frameon=False, fontsize=9)
    fig.text(.04,.025, 'D holds the actual outputs and budget notices fixed. It is not a new full-policy run.\n'
             'R is an accounting remainder, not a causal effect. Original P111 outcomes are retained.',
             fontsize=10, color='#394452')
    fig.tight_layout(rect=(0,.10,1,.90))
    save(fig, folder, 'P112_accounting_components')
    plt.close(fig)


def main(root):
    data, source_hashes = sources(root)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family':'DejaVu Sans', 'svg.fonttype':'none', 'font.size':10})
    folder = root/'materials/20261025_p111_p112_figures'
    folder.mkdir()
    costs_figure(data['audit'], folder, plt, Patch)
    decomposition_figure(data['audit'], data['diagnosis'], folder, plt, Patch, Line2D)
    write_new(folder/'build_manifest.json', dict(
        created_at=datetime.now(timezone.utc).isoformat(), builder_sha256=sha(Path(__file__)),
        source_sha256=source_hashes, matplotlib_version=matplotlib.__version__,
        artifacts={path.name:sha(path) for path in sorted(folder.iterdir())},
        P111_conditions_retained=12, P112_comparison_slots_retained=8,
        additional_model_calls=0, additional_API_requests=0, additional_evaluations=0,
        unknown_usage_imputed=False, new_quality_or_causal_claim=False,
    ))
    print(json.dumps({'figures':2,'formats':['png','pdf','svg'],'all_conditions_retained':12}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    main(parser.parse_args().repo_root.resolve())

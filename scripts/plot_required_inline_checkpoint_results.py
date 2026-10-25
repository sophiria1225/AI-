"""All eight P120 slots, with summary costs and unknown usage made explicit."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from plot_receipt_history_results import read, sha, write_new, require, success_label, save, TASKS

POLICIES = ('single_checkpoint', 'inline_checkpoint')
COMPONENTS = (
    ('agent', 'input_tokens', 'Agent input (incl. inline prompt)', '#4676a8'),
    ('agent', 'output_tokens', 'Agent output (incl. inline metadata)', '#94b5d4'),
    ('focus', 'input_tokens', 'Separate summary input', '#d0802a'),
    ('focus', 'output_tokens', 'Separate summary output', '#f3c27a'),
)


def sources(root):
    paths = {key: root / rel for key, rel in (
        ('audit', 'reports/P120_comparison.json'),
        ('session', 'reports/P120_server_session.json'),
        ('plan', 'configs/P120_whole_task_required_inline_checkpoint_v01.json'))}
    data = {key: read(path) for key, path in paths.items()}
    audit, session, plan = (data[k] for k in ('audit', 'session', 'plan'))
    require(audit['phase'] == 'P120' and not audit['audit_errors'] and
            audit['owned_processes_absent'] and audit['batch_status'] in ('complete', 'stopped') and
            session['phase'] == 'P120' and session['status'] == 'stopped' and
            session['owned_processes_absent'] and session['audit_source_sha256'] == sha(paths['audit']),
            'closed_owned_audited_P120_required')
    require(audit['plan_sha256'] == sha(paths['plan']) and plan['contemporaneous_comparison'] is True,
            'fixed_contemporaneous_plan_required')
    require({x['task_id'] for x in plan['known_tasks']} == set(TASKS), 'fixed_four_tasks_required')
    return data, {str(path.relative_to(root)): sha(path) for path in paths.values()}


def costs_figure(rows, folder, plt, Patch, *, synthetic=False):
    lookup = {(r['task_id'], r['checkpoint_policy']): r for r in rows}
    require(len(rows) == len(lookup) == 8 and
            set(lookup) == {(t, p) for t in TASKS for p in POLICIES}, 'all_eight_slots_required')
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    maximum = max((r.get('known_total_tokens') or 0) / 1000 for r in rows)
    limit = max(1, maximum) * 1.55
    for ax, (task, title) in zip(axes.flat, TASKS.items(), strict=True):
        for position, policy in enumerate(POLICIES):
            row = lookup[task, policy]
            if row['record_status'] not in ('evaluated', 'unevaluated'):
                ax.text(position, limit * .07, row['record_status'].replace('_', '\n'),
                        ha='center', va='bottom', fontsize=11, color='#596575')
                continue
            roles = row['usage_by_role']
            require(set(roles) == {'agent', 'focus'}, 'explicit_both_role_ledgers_required')
            for role in roles.values():
                require(all(type(role[k]) is int and role[k] >= 0 for k in
                            ('calls', 'unknown_usage', 'input_tokens', 'output_tokens')),
                        'nonnegative_known_role_subtotals_required')
                require(role['unknown_usage'] <= role['calls'], 'unknown_usage_exceeds_attempts')
            require(sum(role['calls'] for role in roles.values()) == row['model_calls'] and
                    sum(role['unknown_usage'] for role in roles.values()) == row['unknown_usage_calls'],
                    'all_role_attempts_must_be_accounted')
            require(sum(roles[r][k] for r, k, _, _ in COMPONENTS) == row['known_total_tokens'],
                    'all_role_cost_components_disagree')
            unknown = row['unknown_usage_calls'] > 0
            bottom = 0
            for role, key, _, color in COMPONENTS:
                value = roles[role][key] / 1000
                ax.bar(position, value, bottom=bottom, width=.55, color=color,
                       edgecolor='#506070', linewidth=.6, hatch='///' if unknown else None)
                bottom += value
            label = f"{row['known_total_tokens']:,}" + (' + ?' if unknown else '')
            label += '\n' + success_label(row['success'])
            label += f"\nCalls: {roles['agent']['calls']} agent + {roles['focus']['calls']} summary"
            installed = row.get('checkpoint_installed')
            require(type(installed) is bool, 'accounted_checkpoint_installation_status_required')
            label += '\nCheckpoint: ' + ('installed' if installed else 'not installed')
            if unknown:
                label += f"\n{row['unknown_usage_calls']} unknown usage"
            ax.text(position, bottom + limit * .025, label, ha='center', va='bottom', fontsize=9)
        ax.set_title(title + ' / ' + task, loc='left', fontsize=12, fontweight='bold')
        ax.set_xticks(range(2), ['Separate checkpoint', 'Required inline checkpoint'], fontsize=10)
        ax.set_xlim(-.65, 1.65)
        ax.set_ylim(0, limit)
        ax.set_ylabel('Logical input + output tokens (thousands)')
        ax.grid(axis='y', alpha=.22)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('P120: separate and required inline checkpoints',
                 fontsize=16, fontweight='bold', y=.98)
    handles = [Patch(facecolor=color, label=label) for _, _, label, color in COMPONENTS]
    handles += [Patch(facecolor='white', edgecolor='#596575', hatch='///',
                      label='Known subtotal; total unknown')]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .945),
               ncol=3, frameon=False, fontsize=9)
    fig.text(.05, .025,
        'Four known development tasks; one run per condition. All eight slots retained. Cached input counts as input.\n'
        'All checkpoint instructions, schema and output are charged. Summary costs include rejected summaries. Unknown use is not zero; missing slots are not free runs.\n'
        'Required schema does not establish actual installation. Lower cost alone does not establish preserved quality. Ordinary-control comparison.',
        fontsize=9, color='#394452')
    if synthetic:
        fig.text(.5, .5, 'SYNTHETIC PREVIEW — NOT EXPERIMENT RESULTS', ha='center', va='center',
                 rotation=25, color='#a00000', fontsize=23, alpha=.45, weight='bold')
    fig.tight_layout(rect=(0, .10, 1, .88))
    save(fig, folder, 'P120_all_conditions')
    plt.close(fig)


def main(root):
    data, hashes = sources(root)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none', 'font.size': 10})
    folder = root / 'materials/20261025_p120_figures'
    folder.mkdir()
    costs_figure(data['audit']['rows'], folder, plt, Patch)
    write_new(folder / 'build_manifest.json', {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'builder_sha256': sha(Path(__file__)),
        'helper_sha256': sha(root / 'scripts/plot_receipt_history_results.py'),
        'source_sha256': hashes,
        'public_artifact_sha256': {p.name: sha(p) for p in sorted(folder.iterdir())},
        'matplotlib_version': matplotlib.__version__, 'all_conditions': 8,
        'summary_cost_included': True, 'unknown_usage_imputed': False,
        'additional_model_calls': 0, 'additional_API_requests': 0, 'additional_evaluations': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    main(parser.parse_args().repo_root.resolve())

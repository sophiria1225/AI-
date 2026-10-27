"""Small P138 plotting draft. CLI accepts handwritten synthetic data only.

No experiment result, closure marker, model, API, evaluator or tokenizer is read.
A future reviewed closed-data adapter may call render_summary(..., synthetic=False)
after verifying closure/source/collector/review; this draft is not that adapter.
Fixed comparison values and gates are displayed, never independently estimated.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

MODES = ('rolling_separate', 'fixed_interval', 'prefix_exposure')
LABELS = {'rolling_separate': 'Threshold 16k', 'fixed_interval': 'Fixed 3 turns',
          'prefix_exposure': 'Paid prefix exposure'}
COLORS = {'rolling_separate': '#697A8B', 'fixed_interval': '#3985A6', 'prefix_exposure': '#CA7939'}
ROW_KEYS = ('run_id', 'task_id', 'prefix_exposure_mode', 'record_status', 'success',
            'known_total_tokens', 'unknown_usage_calls', 'prefix_exposure_contract_failed',
            'prefix_exposure_accounting_complete')
PAIR_KEYS = ('task_id', 'baseline', 'baseline_success', 'candidate_success', 'both_evaluated',
             'both_usage_known', 'success_lost', 'both_successful', 'candidate_minus_baseline_tokens')
COMP_KEYS = ('baseline', 'all_four_pairs_complete_with_known_usage', 'all_task_token_difference',
             'common_success_tasks', 'common_success_token_difference',
             'changed_decision_on_common_success', 'comparison_gate_met')


def require(value, message):
    if not value:
        raise ValueError(message)


def nonnegative(value):
    return type(value) is int and value >= 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_summary(summary, synthetic):
    """Allowlisted public plotting data; validates shape but does not re-audit gates."""
    require(type(synthetic) is bool and type(summary) is dict, 'typed input required')
    require(summary.get('phase') == 'P138' and summary.get('planned_rows') == 12,
            'P138 twelve planned rows required')
    require(type(summary.get('conditions')) is list and len(summary['conditions']) == 12,
            'all twelve conditions required')
    rows = [{k: deepcopy(row.get(k)) for k in ROW_KEYS} for row in summary['conditions']]
    tasks = list(dict.fromkeys(row['task_id'] for row in rows))
    require(len(tasks) == 4 and all(type(t) is str and t for t in tasks), 'four task IDs required')
    require(len({r['run_id'] for r in rows}) == 12 and
            {(r['task_id'], r['prefix_exposure_mode']) for r in rows} ==
            {(t, m) for t in tasks for m in MODES}, 'unique balanced twelve slots required')
    for row in rows:
        require(type(row['run_id']) is str and type(row['record_status']) is str,
                'condition identity and record status required')
        require(row['success'] is None or type(row['success']) is bool, 'typed outcome required')
        require(row['success'] is None or row['record_status'] == 'evaluated',
                'success requires evaluated row')
        for field in ('known_total_tokens', 'unknown_usage_calls'):
            require(row[field] is None or nonnegative(row[field]), 'nonnegative count or null required')
        for field in ('prefix_exposure_contract_failed', 'prefix_exposure_accounting_complete'):
            require(row[field] is None or type(row[field]) is bool, 'typed accounting flag required')
    comparisons = []
    require(type(summary.get('comparisons')) is list and len(summary['comparisons']) == 2,
            'both fixed comparisons required')
    for original, baseline in zip(summary['comparisons'], MODES[:2], strict=True):
        require(original.get('baseline') == baseline, 'comparison order changed')
        comp = {k: deepcopy(original.get(k)) for k in COMP_KEYS}
        require(type(comp['common_success_tasks']) is list and
                len(set(comp['common_success_tasks'])) == len(comp['common_success_tasks']) and
                set(comp['common_success_tasks']) <= set(tasks), 'common-success IDs must name tasks')
        for k in ('all_task_token_difference', 'common_success_token_difference'):
            require(comp[k] is None or type(comp[k]) is int, 'signed fixed difference or null required')
        require(type(comp['comparison_gate_met']) is bool, 'fixed comparison gate required')
        pairs = [{k: deepcopy(p.get(k)) for k in PAIR_KEYS} for p in original['pairs']]
        require(len(pairs) == 4 and {p['task_id'] for p in pairs} == set(tasks), 'all four pairs required')
        for pair in pairs:
            require(pair['baseline'] == baseline, 'pair belongs to wrong comparison')
            require(pair['candidate_minus_baseline_tokens'] is None or
                    type(pair['candidate_minus_baseline_tokens']) is int, 'pair difference must be signed or null')
            for k in ('baseline_success', 'candidate_success', 'both_evaluated', 'both_usage_known',
                      'success_lost', 'both_successful'):
                require(pair[k] is None or type(pair[k]) is bool, 'typed pair disposition required')
        comp['pairs'] = pairs
        comparisons.append(comp)
    gates = {k: summary.get(k) for k in ('primary_utility_gate_met', 'both_control_development_gate_met')}
    require(all(type(v) is bool for v in gates.values()), 'fixed two-stage gates required')
    return dict(phase='P138', synthetic=synthetic, task_order=tasks, modes=list(MODES),
                model_seed=57, independent_tasks=4, conditions=rows, comparisons=comparisons,
                **gates, gates_recomputed_by_plotter=False, closed_audit_performed_by_plotter=False)


def outcome(row):
    if row['success'] is True:
        value = 'SUCCESS'
    elif row['success'] is False:
        value = 'FAILURE'
    else:
        value = row['record_status'].replace('_', ' ').upper()
    if row['prefix_exposure_contract_failed'] is True:
        value += '\nCONTRACT FAILURE'
    elif row['prefix_exposure_accounting_complete'] is False:
        value += '\nEXPOSURE ACCOUNTING\nINCOMPLETE'
    return value


def cost_text(row):
    known, unknown = row['known_total_tokens'], row['unknown_usage_calls']
    if known is None:
        return 'Usage unmeasured'
    if type(unknown) is int and unknown == 0:
        return f'{known:,} exact'
    suffix = f'{unknown} unknown call(s)' if unknown is not None else 'unknown-call count missing'
    return f'≥ {known:,} known\nTotal unknown; {suffix}'


def delta_text(value):
    return 'Not estimable' if value is None else f'{value:+,}'


def transition(pair):
    a, b = pair['baseline_success'], pair['candidate_success']
    if a is None or b is None:
        return 'Not both evaluated'
    return {(True, True): 'Both successful', (False, False): 'Both failed',
            (True, False): 'Success lost', (False, True): 'Success gained'}[(a, b)]


def render_summary(summary, output, *, synthetic, input_sha256=None):
    data = project_summary(summary, synthetic)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'pdf.fonttype': 42})
    rows = {(r['task_id'], r['prefix_exposure_mode']): r for r in data['conditions']}
    labels = {task: f'Task {i+1}' for i, task in enumerate(data['task_order'])}
    prefix = 'SYNTHETIC — NOT EXPERIMENT RESULTS\n' if synthetic else ''
    ceiling = max([1] + [r['known_total_tokens'] for r in data['conditions'] if r['known_total_tokens'] is not None])
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), sharey=True)
    fig.subplots_adjust(left=.075, right=.98, bottom=.19, top=.80, hspace=.53, wspace=.17)
    for ax, task in zip(axes.flat, data['task_order'], strict=True):
        for x, mode in enumerate(MODES):
            row = rows[task, mode]; known = row['known_total_tokens']
            if known is None:
                ax.text(x, .055, '× Usage unmeasured\n'+outcome(row),
                        transform=ax.get_xaxis_transform(), ha='center', va='bottom', color='#555555', fontsize=8.8)
                continue
            else:
                bar = ax.bar(x, known, color=COLORS[mode], width=.60)[0]
                if row['unknown_usage_calls'] is None or row['unknown_usage_calls'] > 0:
                    bar.set_hatch('///'); bar.set_edgecolor('#333333')
                y = known + ceiling*.025
            text = (cost_text(row)+'\n' if known is not None else '') + outcome(row)
            ax.text(x, y, text, ha='center', va='bottom', fontsize=8.8, linespacing=1.3)
        ax.set_title(labels[task], fontweight='bold')
        ax.set_xticks(range(3), ['Threshold\n16k', 'Fixed\n3 turns', 'Paid prefix\nexposure'])
        ax.set_xlim(-.6, 2.6); ax.set_ylim(0, ceiling*1.55)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value/1000:,.0f}k'))
        ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    axes[0, 0].set_ylabel('Logical input + output tokens')
    axes[1, 0].set_ylabel('Logical input + output tokens')
    fig.suptitle(prefix+'P138 — Whole-job cost and official outcome', y=.98, fontsize=16)
    fig.legend(handles=[Patch(facecolor='white', edgecolor='#333333', hatch='///',
                            label='Known lower bound; total usage unknown')], loc='upper center', bbox_to_anchor=(.5,.875), frameon=False)
    fig.text(.075, .08, 'All 12 planned slots remain visible. × means unmeasured usage, not zero. Failure and unevaluated outcomes remain separate.\n'
             'Costs include all known actor + focus input/output, including cached input and failed or rejected summaries.\n'
             'Four known development tasks; one model seed (57). No general quality, novelty or competitive-ratio claim.', fontsize=10, linespacing=1.5)
    for ext in ('png','pdf'):
        fig.savefig(output/f'whole_job_cost.{ext}', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    fig.subplots_adjust(left=.06, right=.97, bottom=.27, top=.82, hspace=.45)
    for ax, comp in zip(axes, data['comparisons'], strict=True):
        pairs = {p['task_id']: p for p in comp['pairs']}
        body = [[labels[t], delta_text(pairs[t]['candidate_minus_baseline_tokens']), transition(pairs[t])]
                for t in data['task_order']]
        ax.axis('off')
        ax.set_title(('PRIMARY: ' if comp['baseline']=='rolling_separate' else 'TIMING CONTROL: ')
                     +'Exposure − '+LABELS[comp['baseline']], loc='left', fontweight='bold', pad=10)
        table = ax.table(cellText=body, colLabels=['Paired task', 'Δ logical tokens', 'Official outcome transition'],
                         colWidths=[.22,.33,.45], loc='upper center', cellLoc='center')
        table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1, 1.7)
        ax.text(0, -.15, f"All-task Δ: {delta_text(comp['all_task_token_difference'])}   |   "
                f"Common successes: {len(comp['common_success_tasks'])}/4   |   "
                f"Common-success Δ: {delta_text(comp['common_success_token_difference'])}   |   "
                f"Fixed comparison gate: {comp['comparison_gate_met']}", transform=ax.transAxes, fontsize=10)
    fig.suptitle(prefix+'P138 — Paired comparisons and fixed decisions', y=.98, fontsize=16)
    fig.text(.06,.87,f"Primary utility gate: {data['primary_utility_gate_met']}    |    "
             f"Both-control development gate: {data['both_control_development_gate_met']}",fontsize=12)
    fig.text(.06,.07,'Fixed report values are displayed unchanged; the plotter does not recompute gates or estimate missing effects.\n'
             'Not estimable includes null aggregates under the fixed completeness rule, even when some component costs are known.\n'
             'Common-success costs describe a selected subset. Both-failed cost differences are not evidence of preserved quality.\n'
             'Dispatched predicate differences do not decompose the causal effect on whole-job cost. Prior cohorts are not pooled.',
             fontsize=10,linespacing=1.6)
    for ext in ('png','pdf'):
        fig.savefig(output/f'paired_comparisons.{ext}', dpi=180)
    plt.close(fig)
    (output/'figure_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    files={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    manifest=dict(phase='P138',synthetic=synthetic,renderer_source_sha256=sha(__file__),
                  input_summary_sha256=input_sha256,artifact_sha256=files,
                  matplotlib_version=matplotlib.__version__,gates_recomputed=False,
                  closed_source_verification_performed=False,actual_results_read_by_this_synthetic_run=False if synthetic else None,
                  additional_model_API_evaluation_tokenizer_calls=0,saved_generated_program_execution=0)
    (output/'output_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-fixture',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    fixture=json.loads(args.synthetic_fixture.read_text())
    require(fixture.get('synthetic') is True and fixture.get('warning')=='HANDWRITTEN SYNTHETIC ONLY — NOT P138 RESULTS',
            'CLI is restricted to a labelled handwritten synthetic fixture')
    manifest=render_summary(fixture['summary'],args.output_dir,synthetic=True,input_sha256=sha(args.synthetic_fixture))
    print(json.dumps({'synthetic':True,'output_dir':str(args.output_dir),'artifacts':list(manifest['artifact_sha256'])}))


if __name__=='__main__': main()

"""Data-only compact presentation of already-validated P140 figure_data.

Explicit input SHA is required. This does not run or replace a closure audit,
checker, original renderer, experiment, or gate calculation. No default paths.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

MODES = ('threshold_recursive', 'exposure_delta', 'exposure_delta_object')
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
SHORT = ('T/R', 'E/D', 'E/DO')
COLORS = ('#64748b', '#7b70ac', '#278b7d')
GATES = ('primary_utility_gate_met', 'unchanged_delta_control_gate_met', 'both_control_development_gate_met')
SIZE_INCHES = (7.0, 3.8)
DPI = 300


def require(condition, label):
    if not condition:
        raise ValueError(label)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def nni(value):
    return type(value) is int and value >= 0


def validate_data(data, synthetic):
    require(type(data) is dict and data.get('phase') == 'P140', 'P140_data_required')
    require(type(synthetic) is bool and data.get('synthetic') is synthetic, 'synthetic_label_must_match')
    require(type(data.get('model_seed')) is int and data['model_seed'] == 57 and
            type(data.get('independent_tasks')) is int and data['independent_tasks'] == 4, 'fixed_scope_required')
    require(data.get('modes') == list(MODES) and data.get('task_order') == list(TASKS), 'fixed_mode_task_order_required')
    require(data.get('all_model_roles_included') is True and data.get('cached_input_deducted') is False and
            data.get('prior_results_pooled') is False and data.get('unknown_usage_imputed') is False, 'cost_convention_differs')
    require(all(k in data and (data[k] is None or type(data[k]) is bool) for k in GATES), 'saved_gate_values_required')
    rows = data.get('conditions')
    require(type(rows) is list and len(rows) == 12, 'all_twelve_cells_required')
    expected = [(f'BOC_P140_{n:02d}_{MODES[(n-1+k)%3].upper()}', TASKS[n-1], MODES[(n-1+k)%3])
                for n in range(1, 5) for k in range(3)]
    require(all(type(r) is dict for r in rows) and
            [(r.get('run_id'),r.get('task_id'),r.get('checkpoint_representation_mode')) for r in rows] == expected,
            'all_ordered_identities_required')
    shown = []
    for row in rows:
        require(row.get('record_status') in ('evaluated','unevaluated','not_run','incomplete_worker','audit_error'), 'record_status_required')
        require('success' in row and (row['success'] is None or type(row['success']) is bool), 'outcome_bool_or_null')
        require((row['record_status'] == 'evaluated') == (type(row['success']) is bool), 'outcome_status_mismatch')
        for key in ('known_total_tokens','unknown_usage_calls'):
            require(key in row and (row[key] is None or nni(row[key])), 'token_count_or_null_required')
        known, unknown = row['known_total_tokens'], row['unknown_usage_calls']
        kind = 'missing' if known is None else ('known_exact' if unknown == 0 else 'known_lower_bound')
        shown.append({k: deepcopy(row[k]) for k in ('run_id','task_id','checkpoint_representation_mode',
                     'record_status','success','known_total_tokens','unknown_usage_calls')} |
                     {'cost_display_kind': kind, 'bar_drawn': known is not None,
                      'outcome_marker': 'o' if row['success'] is True else 'x' if row['success'] is False else 'D'})
    return dict(conditions=shown, saved_gates={key: data[key] for key in GATES}, synthetic=synthetic,
                all_model_roles_included=True, cached_input_deducted=False,
                arithmetic_or_gates_recomputed=False, closure_reaudited=False, prior_results_pooled=False)


def render(data, output_dir, *, original_data_sha256, synthetic):
    require(type(original_data_sha256) is str and len(original_data_sha256) == 64 and
            set(original_data_sha256) <= set('0123456789abcdef'), 'data_SHA256_required')
    display = validate_data(data, synthetic)
    out = Path(output_dir)
    require(not out.exists(), 'exclusive_new_output_directory_required')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.text import Text
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':8.5, 'pdf.fonttype':42,
                         'axes.titlesize':9, 'axes.labelsize':8.5, 'xtick.labelsize':8.5, 'ytick.labelsize':8})
    fig, axes = plt.subplots(1, 4, figsize=SIZE_INCHES, sharey=True)
    fig.subplots_adjust(left=.095, right=.99, bottom=.31, top=.715, wspace=.10)
    lookup = {(r['task_id'],r['checkpoint_representation_mode']):r for r in display['conditions']}
    ceiling = max([1] + [r['known_total_tokens'] for r in display['conditions'] if r['bar_drawn']])
    for number, (ax, task) in enumerate(zip(axes, TASKS), 1):
        for x, mode in enumerate(MODES):
            row = lookup[task, mode]; value = row['known_total_tokens']
            if value is None:
                ax.plot(x, .025, marker=row['outcome_marker'], markerfacecolor='none', color='#111111', markersize=5,
                        transform=ax.get_xaxis_transform(), clip_on=False)
                ax.text(x, .10, 'missing', ha='center', va='bottom', rotation=90,
                        transform=ax.get_xaxis_transform(), fontsize=8)
                continue
            bar = ax.bar(x, value, width=.65, color=COLORS[x], edgecolor='#333333', linewidth=.5)[0]
            if row['cost_display_kind'] == 'known_lower_bound':
                bar.set_hatch('///')
                label = 'U?' if row['unknown_usage_calls'] is None else f"U{row['unknown_usage_calls']}"
                if value == 0: label = '≥0; '+label
                ax.text(x, value+ceiling*.10, label, ha='center', va='bottom', fontsize=8)
            ax.plot(x, value+ceiling*.035, marker=row['outcome_marker'], color='#111111',
                    markersize=5, markerfacecolor='none', linestyle='none')
        ax.set_title(f'Task {number}', fontweight='bold', pad=5)
        ax.set_xticks([0,1,2], SHORT); ax.set_xlim(-.65,2.65); ax.set_ylim(0,ceiling*1.30)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value/1000:g}k'))
        ax.grid(axis='y', color='#dddddd', linewidth=.6); ax.set_axisbelow(True)
        ax.spines[['top','right']].set_visible(False)
    axes[0].set_ylabel('Known logical I/O tokens')
    if synthetic:
        fig.text(.5,.97,'SYNTHETIC — NOT EXPERIMENT RESULTS',ha='center',va='top',fontsize=11,color='#a52222',fontweight='bold')
    fig.text(.5,.885,'P140 · all 12 planned cells',ha='center',fontsize=10,fontweight='bold')
    labels = ('T/R: threshold / recursive', 'E/D: exposure / delta', 'E/DO: exposure / object delta')
    fig.legend(handles=[Patch(facecolor=color,label=label) for color,label in zip(COLORS,labels)],
               loc='upper center',bbox_to_anchor=(.54,.845),ncol=3,frameon=False,fontsize=8,columnspacing=1.0,handlelength=1.1)
    fig.text(.095,.215,'○ success   × failure   ◇ unevaluated     Hatch: lower bound; U: unknown calls.',fontsize=8)
    fig.text(.095,.164,'Missing usage has no bar. Actor + focus; cached input included, not deducted.',fontsize=8)
    def gate(value): return 'null' if value is None else str(value).lower()
    g = display['saved_gates']
    fig.text(.095,.104,f"Saved gates: primary {gate(g[GATES[0]])}  |  unchanged-delta {gate(g[GATES[1]])}  |  both {gate(g[GATES[2]])}",fontsize=8.5,fontweight='bold')
    fig.text(.095,.045,'Four known tasks, seed 57; no prior pooling. Data-only derivative; gates unchanged.',fontsize=8)
    fig.canvas.draw()
    fonts = [t.get_fontsize() for t in fig.findobj(Text) if t.get_text()]
    require(min(fonts) >= 8, 'minimum_print_font_not_met')
    out.mkdir(parents=True, exist_ok=False)
    for ext in ('png','pdf'):
        fig.savefig(out/f'compact_cost.{ext}',dpi=DPI)
    plt.close(fig)
    display.update(original_figure_data_sha256=original_data_sha256)
    (out/'compact_display_metadata.json').write_text(json.dumps(display,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    manifest = dict(kind='P140_compact_cost_presentation_derivative', synthetic=synthetic,
        original_figure_data_sha256=original_data_sha256, renderer_source_sha256=sha(Path(__file__).read_bytes()),
        figure_inches=list(SIZE_INCHES), dpi=DPI, png_pixels=[int(x*DPI) for x in SIZE_INCHES],
        minimum_nonempty_text_pt=min(fonts), matplotlib_version=matplotlib.__version__,
        artifact_sha256={p.name:sha(p.read_bytes()) for p in sorted(out.iterdir())},
        original_renderer_checker_executions=0, additional_model_API_native_evaluator_calls=0,
        gates_recomputed_or_relaxed=False, closure_or_prefix_reaudited=False,
        limitation='Source data hash must come from the already-validated original figure publication. A self-supplied hash alone is not closure or scientific validation.')
    (out/'output_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figure-data',type=Path,required=True)
    parser.add_argument('--expected-data-sha256',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--synthetic',action='store_true')
    args = parser.parse_args()
    raw = args.figure_data.read_bytes()
    require(sha(raw) == args.expected_data_sha256, 'input_hash_mismatch')
    data = json.loads(raw)
    result = render(data,args.output_dir,original_data_sha256=sha(raw),synthetic=args.synthetic)
    print(json.dumps({'synthetic':result['synthetic'],'artifact_sha256':result['artifact_sha256']}))

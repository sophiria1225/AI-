"""Small data-only P143 plotter; actual execution requires closed-input approval.

This is a renderer, not a replacement for the fixed audit/independent checker.
The caller must authenticate closure and supply the approved manifest and
summary hashes. Import is pure; this file contains no runtime/result defaults.
Cached input remains included in logical input; unknown amounts are not zero.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re

TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
LABELS = ('Photo', 'Settlement', 'Refund', 'CSV')
MODES = ('threshold_recursive', 'threshold_delta_object')
SOURCE_HEAD = '85a8d3b6f5e676fe3ab6a94118a9f87c0d11e0c3'
INPUTS = ('summary.json', 'conditions.csv', 'model_calls.csv')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    return type(value) is int and value >= 0


def csv_number(value):
    if value == '':
        return None
    require(bool(re.fullmatch(r'0|[1-9][0-9]*', value)), 'invalid_numeric_metadata')
    return int(value)


def csv_value(value):
    return '' if value is None else str(value)


def prepare_rows(summary, conditions, calls):
    """Cross-check only public scalar metadata; never inspect task/model text."""
    require(summary.get('phase') == 'P143' and summary.get('planned_rows') == 8
            and summary.get('model_seed') == 157, 'fixed_eight_rows_required')
    require(summary.get('all_model_roles_included') is True
            and summary.get('cached_input_deducted') is False, 'logical_cost_contract')
    source_rows = summary.get('conditions')
    require(type(source_rows) is list and len(source_rows) == len(conditions) == 8,
            'all_eight_conditions_required')
    identities = [(r.get('task_id'), r.get('object_timing_mode')) for r in source_rows]
    require(len(set(identities)) == 8 and set(identities) == {(t,m) for t in TASKS for m in MODES},
            'all_task_mode_pairs_required')
    run_ids = [r.get('run_id') for r in source_rows]
    require(len(set(run_ids)) == 8 and all(type(r) is str and r.startswith('BOC_P143_') for r in run_ids),
            'unique_P143_runs_required')
    for original, saved in zip(source_rows, conditions):
        require(set(original) == set(saved) and all(csv_value(original[k]) == saved[k] for k in saved),
                'summary_conditions_csv_mismatch')
    by_run = {r: [] for r in run_ids}
    for call in calls:
        require(call.get('run_id') in by_run, 'unexpected_call_run')
        by_run[call['run_id']].append(call)
    data = []
    for task, label in zip(TASKS, LABELS):
        for mode in MODES:
            row = source_rows[identities.index((task,mode))]
            require(type(row.get('model_seed')) is int and row['model_seed'] == 157
                    and row.get('checkpoint_representation_mode') == mode, 'row_scope_mismatch')
            require(row.get('success') is None or type(row['success']) is bool, 'invalid_success')
            subtotal, unknown = row.get('known_total_tokens'), row.get('unknown_usage_calls')
            require(subtotal is None or number(subtotal), 'invalid_known_subtotal')
            require(unknown is None or number(unknown), 'invalid_unknown_count')
            recorded = by_run[row['run_id']]
            amounts = {'agent': 0, 'focus': 0}
            inputs = outputs = unknown_calls = 0
            for n, call in enumerate(recorded, 1):
                require(call.get('call_id') == f'call_{n:03d}' and call.get('role') in amounts
                        and call.get('task_id') == task and call.get('object_timing_mode') == mode
                        and call.get('checkpoint_representation_mode') == mode
                        and call.get('model_seed') == '157', 'call_identity_mismatch')
                i, o = csv_number(call['input_tokens']), csv_number(call['output_tokens'])
                cache = csv_number(call['cached_input_tokens'])
                if call.get('status') == 'ok':
                    require(number(i) and number(o), 'known_call_usage_missing')
                    inputs += i; outputs += o
                    amounts[call['role']] += i + o  # cached input is deliberately NOT subtracted
                else:
                    require(i is None and o is None and cache is None, 'unknown_call_not_null')
                    unknown_calls += 1
            if subtotal is None:
                require(not recorded and unknown is None, 'unmeasured_row_has_call_totals')
                amounts = {k: None for k in amounts}
            else:
                require(number(row.get('model_calls')) and row['model_calls'] == len(recorded)
                        and inputs + outputs == subtotal and unknown_calls == unknown
                        and inputs == row.get('input_tokens') and outputs == row.get('output_tokens'),
                        'call_totals_do_not_match_condition')
            status = row.get('record_status')
            require(type(status) is str and bool(status), 'record_status_required')
            outcome = ('Success' if row['success'] else 'Failed') if type(row['success']) is bool else 'Unevaluated'
            exact = subtotal if status == 'evaluated' and unknown == 0 else None
            data.append(dict(task=label, mode='TR' if mode == MODES[0] else 'TDO',
                record_status=status, outcome=outcome, known_subtotal=subtotal,
                exact_total=exact, unknown_calls=unknown, actor_tokens=amounts['agent'],
                focus_tokens=amounts['focus'],
                delta_known_actor_calls=row.get('actual_delta_known_actor_calls')))
    return data


def load_closed(directory, manifest_sha256, summary_sha256, approved):
    require(approved is True, 'closed_inputs_not_approved')
    require(type(SOURCE_HEAD) is str and re.fullmatch('[0-9a-f]{40}', SOURCE_HEAD), 'P143_source_not_frozen')
    require(all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
                for v in (manifest_sha256, summary_sha256)), 'approved_hashes_required')
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'ordinary_input_directory_required')
    def read(name):
        p = directory / name
        require(p.is_file() and not p.is_symlink(), 'ordinary_input_file_required')
        return p.read_bytes()
    manifest_bytes = read('build_manifest.json')
    require(sha(manifest_bytes) == manifest_sha256, 'manifest_digest_mismatch')
    manifest = json.loads(manifest_bytes)
    require(manifest.get('phase') == 'P143' and manifest.get('status') == 'complete'
            and all(type(manifest.get(k)) is int and manifest[k] == 0 for k in
                    ('additional_model_calls', 'additional_API_requests', 'additional_evaluations')),
            'completed_data_only_manifest_required')
    original = {name: read(name) for name in INPUTS}
    for name, value in original.items():
        require(manifest.get('artifact_sha256', {}).get(name) == sha(value), 'artifact_digest_mismatch')
    require(sha(original['summary.json']) == summary_sha256, 'summary_digest_mismatch')
    summary = json.loads(original['summary.json'])
    require(summary.get('source_sha256') == manifest.get('source_sha256'), 'source_bindings_mismatch')
    conditions = list(csv.DictReader(io.StringIO(original['conditions.csv'].decode())))
    calls = list(csv.DictReader(io.StringIO(original['model_calls.csv'].decode())))
    rows = prepare_rows(summary, conditions, calls)
    return rows, {name: sha(value) for name, value in original.items()} | {'build_manifest.json': sha(manifest_bytes)}, summary


def render(rows, output, inputs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':7,
        'pdf.fonttype':42, 'ps.fonttype':42, 'svg.fonttype':'none'})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    fig, ax = plt.subplots(figsize=(130/25.4,64/25.4))
    fig.subplots_adjust(left=.13,right=.99,bottom=.25,top=.82)
    measured = [r['known_subtotal'] for r in rows if r['known_subtotal'] is not None]
    scale = max(measured+[1])/1000
    positions = []
    for task_index, task in enumerate(LABELS):
        selected = [r for r in rows if r['task'] == task]
        for mode_index, r in enumerate(selected):
            x = task_index*3 + mode_index
            positions.append(x)
            subtotal = r['known_subtotal']
            if subtotal is None:
                ax.text(x, .2*scale, 'Not\nmeasured', ha='center', va='center', fontsize=7)
                ax.plot([x-.18,x+.18],[0,0],color='black',lw=.6)
                label = {'Success':'S','Failed':'F','Unevaluated':'?'}[r['outcome']]
            else:
                a, f = r['actor_tokens']/1000, r['focus_tokens']/1000
                lower_bound = r['exact_total'] is None
                hatch = '///' if lower_bound else None
                ax.bar(x,a,.62,color='.72',edgecolor='black',linewidth=.5,hatch=hatch)
                ax.bar(x,f,.62,bottom=a,color='white',edgecolor='black',linewidth=.5,hatch=hatch)
                amount = ('≥' if lower_bound else '') + f'{subtotal:,}'
                outcome_symbol = {'Success':'S','Failed':'F','Unevaluated':'?'}[r['outcome']]
                label = outcome_symbol + '\n' + amount
                if r['unknown_calls']:
                    label += "*"
                elif lower_bound:
                    label += '\nIncomplete'
            y = (subtotal or 0)/1000
            ax.text(x,y+.035*scale,label,ha='center',va='bottom',fontsize=7,linespacing=1.1)
        ax.text(task_index*3+.5,-.16,task,transform=ax.get_xaxis_transform(),
                ha='center',va='top',fontsize=8)
    ax.set_xticks(positions,['TR','TDO']*4);ax.set_xlim(-.7,10.7)
    ax.set_ylim(0,scale*1.6);ax.set_ylabel('Logical input + output (k tokens)',fontsize=7)
    ax.tick_params(labelsize=7);ax.spines[['top','right']].set_visible(False)
    for spine in ax.spines.values():spine.set_linewidth(.5)
    fig.legend(handles=[Patch(facecolor='.72',edgecolor='black',label='Actor'),
        Patch(facecolor='white',edgecolor='black',label='Focus'),
        Patch(facecolor='white',edgecolor='black',hatch='///',label='Known lower bound')],
        loc='upper center',ncol=3,frameon=False,fontsize=7,bbox_to_anchor=(.5,1))
    fig.text(.5,.055,'S: success; F: failure; *: unknown usage (see table).',
        ha='center',fontsize=7)
    fig.text(.5,.015,'All eight conditions and both roles; cached input included.',ha='center',fontsize=7)
    outputs = {}
    for extension in ('pdf','svg','png','eps'):
        path = output / ('p143_cost.'+extension)
        fig.savefig(path,dpi=600,facecolor='white')
        outputs[path.name] = sha(path.read_bytes())
    plt.close(fig)
    data = dict(phase='P143', rows=rows, all_roles_counted=True, cached_input_deducted=False,
                source_head=SOURCE_HEAD, additional_experiment_calls=0)
    path = output/'figure_data.json'
    with path.open('x') as handle:json.dump(data,handle,indent=2,allow_nan=False);handle.write('\n')
    outputs[path.name] = sha(path.read_bytes())
    manifest = dict(phase='P143_cost_figure', status='complete', inputs=inputs, artifacts=outputs,
        renderer_sha256=sha(Path(__file__).read_bytes()), width_mm=130,height_mm=64,minimum_font_pt=7,
        closure_authenticated_by_caller=True, renderer_recertifies_scientific_audit=False)
    with (output/'figure_manifest.json').open('x') as handle:
        json.dump(manifest,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({'status':'complete','conditions':len(rows),'artifacts':len(outputs)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--summary-sha256', required=True)
    parser.add_argument('--closed-inputs-approved', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    rows, inputs, _ = load_closed(args.input_dir,args.manifest_sha256,args.summary_sha256,args.closed_inputs_approved)
    render(rows,args.output_dir,inputs)


if __name__ == '__main__':
    main()

"""Separate logical, uncached-input, output, and elapsed measures for P80/P81.

Read only published, closed aggregates. Unknown terminal usage stays unknown;
known subsets are lower bounds, not estimates of complete usage or GPU work.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
POLICIES = ('measured', 'not_exposed')
SUM_FIELDS = ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'input_tokens',
              'cached_input_tokens', 'output_tokens', 'api_requests', 'wall_seconds',
              'full_wall_seconds', 'setup_wall_seconds', 'cleanup_wall_seconds')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def aggregate(rows):
    result = {key: sum(row[key] for row in rows) for key in SUM_FIELDS}
    result.update(conditions=len(rows), successes=sum(row['success'] for row in rows),
                  known_uncached_input_tokens=result['input_tokens'] - result['cached_input_tokens'],
                  terminal_usage_complete=result['unknown_usage_calls'] == 0)
    # Deliberately do not combine prefill and decoding tokens into a compute cost.
    return result


def analyze(root):
    started = time.monotonic()
    ledgers = ('reports/P81_P83_results_provenance_20261024.json',
               'reports/P81_usage_interval_provenance_20261024.json')
    sources = set(ledgers)
    for name in ledgers:
        for path, expected in read(root / name)['source_sha256'].items():
            if sha(root / path) != expected:
                raise ValueError('closed_source_changed: ' + path)
            sources.add(path)
    intervals = read(root / 'reports/P81_usage_intervals_20261024.json')
    for path, expected in intervals['source_sha256'].items():
        if sha(root / path) != expected:
            raise ValueError('interval_dependency_changed: ' + path)
        sources.add(path)
    audit = read(root / 'reports/P81_repetitions.json')
    if audit['audit_errors'] or len(audit['anchor_rows']) != 8 or len(audit['rows']) != 16:
        raise ValueError('closed_all_24_required')
    rows, by_id, keys = [], {}, set()
    for original in audit['anchor_rows'] + audit['rows']:
        repetition = original.get('repetition', 1)
        key = (repetition, original['task_id'], original['time_visibility'])
        if key in keys or original['run_id'] in by_id:
            raise ValueError('duplicate_condition')
        if original['record_status'] != 'evaluated' or type(original['success']) is not bool:
            raise ValueError('all_outcomes_required')
        for field in SUM_FIELDS:
            value = original[field]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid_nonnegative_measure')
        if original['cached_input_tokens'] > original['input_tokens']:
            raise ValueError('cache_exceeds_known_input')
        if original['input_tokens'] + original['output_tokens'] != original['known_total_tokens']:
            raise ValueError('known_usage_disagrees')
        calls = [r for r in intervals['rows'] if r['run_id'] == original['run_id']]
        checks = original['request_checks']
        if (len(calls) != original['model_calls'] or len(checks) != len(calls)
                or len({r['call_id'] for r in calls}) != len(calls)
                or sum(not r['complete_usage'] for r in calls) != original['unknown_usage_calls']
                or sum(r['logical_tokens_lower_bound'] for r in calls if r['complete_usage'])
                != original['known_total_tokens']):
            raise ValueError('all_saved_attempts_required')
        for call, check in zip(calls, checks, strict=True):
            # A persisted terminal record may explicitly contain UNKNOWN usage.
            # Its presence must not be mistaken for complete numeric counters.
            if (call['call_id'] != check['call_id']
                    or call['saved_request_sha256'] != check['request_sha256']
                    or call['status'] != check['status']
                    or check['terminal_usage_recorded'] is not True):
                raise ValueError('saved_attempt_identity_disagrees')
        row = {field: original[field] for field in ('run_id', 'task_id', 'time_visibility',
                                                   'success', 'stop_reason', *SUM_FIELDS)}
        row.update(repetition=repetition,
                   known_uncached_input_tokens=row['input_tokens']-row['cached_input_tokens'])
        rows.append(row); by_id[row['run_id']] = row; keys.add(key)
    if keys != {(rep, task, policy) for rep in (1, 2, 3) for task in TASKS for policy in POLICIES}:
        raise ValueError('fixed_24_condition_grid_required')
    if sum(r['model_calls'] for r in rows) != len(intervals['rows']) or len(intervals['rows']) != 429:
        raise ValueError('all_429_attempts_required')
    for row in rows:
        pair = [r for r in rows if (r['repetition'], r['task_id']) == (row['repetition'], row['task_id'])]
        row['outcome_partition'] = ('both_success' if all(r['success'] for r in pair) else
                                    'both_failure' if all(not r['success'] for r in pair) else 'discordant')
    partitions = []
    for rep in ('1', '2', '3', 'combined'):
        for category in ('total', 'both_success', 'both_failure', 'discordant'):
            for policy in POLICIES:
                selected = [r for r in rows if (rep == 'combined' or r['repetition'] == int(rep))
                            and (category == 'total' or r['outcome_partition'] == category)
                            and r['time_visibility'] == policy]
                partitions.append(dict(repetition=rep, category=category, time_visibility=policy,
                                       **aggregate(selected)))
    total = {p: aggregate([r for r in rows if r['time_visibility'] == p]) for p in POLICIES}
    m, h = total['measured'], total['not_exposed']
    if not m['terminal_usage_complete'] or h['unknown_usage_calls'] != 2:
        raise ValueError('expected_closed_unknown_pattern_changed')
    differences = {}
    for key in ('known_uncached_input_tokens', 'output_tokens', 'wall_seconds', 'full_wall_seconds'):
        delta = h[key] - m[key]
        differences[key] = dict(H_minus_M=delta, H_minus_M_percent=100*delta/m[key],
                                interpretation='known_subset_lower_bound' if 'tokens' in key else
                                'observed_elapsed_difference_not_a_causal_speed_estimate')
    sessions = {phase: read(root / f'reports/{phase}_server_session.json') for phase in ('P80', 'P81')}
    if not math.isclose(sum(r['full_wall_seconds'] for r in rows),
                        sum(s['cell_full_wall_seconds'] for s in sessions.values()), abs_tol=1e-6):
        raise ValueError('cell_and_session_time_disagree')
    shared = {key: sum(s[key] for s in sessions.values()) for key in (
        'wall_seconds', 'load_wall_seconds', 'pipeline_wall_seconds', 'evaluation_wall_seconds',
        'cell_full_wall_seconds', 'batch_other_wall_seconds')}
    return dict(phase='P81_resource_accounting', posthoc=True, rows=rows, partitions=partitions,
                totals=total, differences=differences,
                conditional_logical_interval=intervals['combined']['total'],
                shared_session_measures=shared,
                session_note='P80 and P81 are separate sessions; their corresponding durations are summed. '
                             'Load, evaluation, cell and server durations overlap and are not added together. '
                             'Shared overhead is not allocated to M or H.',
                terminal_unknowns_retained=2, known_receipts=427, saved_attempts=429,
                source_sha256={path: sha(root / path) for path in sorted(sources)},
                analysis_wall_seconds=time.monotonic()-started,
                additional_generations=0, additional_input_count_requests=0,
                additional_api_requests=0, additional_evaluations=0,
                raw_histories_read=False, private_reasoning_read=False,
                gpu_flops_or_energy_measured=False, novel_method_claim=False,
                causal_wall_time_claim=False, missing_usage_imputed=False)


def write_csv(path, rows):
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def figure(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, ax = plt.subplots(figsize=(10.8, 5.6), layout='constrained')
    fig.get_layout_engine().set(h_pad=.14, w_pad=.10)
    total = report['conditional_logical_interval']
    lo, hi = [100 * value / total['measured'][0] for value in total['H_minus_M']]
    center = (lo+hi)/2
    ax.errorbar(center, 3, xerr=[[center-lo], [hi-center]], capsize=7, color='#336b87', lw=2)
    ax.annotate(f'{lo:+.2f} ～ {hi:+.2f}%（条件付き区間）', (hi, 3), xytext=(12, 0),
                textcoords='offset points', va='center', color='#336b87')
    for y, key in ((2, 'known_uncached_input_tokens'), (1, 'output_tokens'), (0, 'wall_seconds')):
        value = report['differences'][key]['H_minus_M_percent']
        lower = y > 0
        ax.plot(value, y, marker='>' if lower else 'o', color='#b85f2a', markersize=8)
        label = f'少なくとも +{value:.2f}%' if lower else f'+{value:.2f}%（実測）'
        ax.annotate(label, (value, y), xytext=(12, 0), textcoords='offset points', va='center')
    ax.set(yticks=[0, 1, 2, 3], yticklabels=['作業時間の合計', '出力token',
            'cacheを除く入力token', '全論理入力＋出力token'], xlim=(-6, 67), ylim=(-.6, 3.6),
            xlabel='H − M の比率（Mに対する％）　負：Hが少ない／正：Hが多い')
    ax.axvline(0, color='#888888', lw=.8, ls='--'); ax.grid(axis='x', alpha=.15)
    fig.suptitle('残時間非表示Hと表示M：指標によって差の方向が異なる', fontsize=14)
    fig.supxlabel('既知４課題×３反復の全24条件. 両側とも各反復3/4成功. 不明な終端２生成を保持.\n'
                  '三角は既知分からの下限で, 欠測を０に補完していない. 区間は統計的信頼区間ではない.\n'
                  '入力処理と出力生成は異なる計算であり, token数をFLOPs・電力量・料金へ換算していない.',
                  fontsize=9)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(output / f'resource_measures.{extension}', dpi=190)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'materials/20261024_p81_resource_accounting')
    parser.add_argument('--figure', action='store_true')
    args = parser.parse_args()
    report = analyze(ROOT)
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'resource_accounting.json').open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    write_csv(args.output / 'all_24_conditions.csv', report['rows'])
    write_csv(args.output / 'all_partitions.csv', report['partitions'])
    if args.figure:
        figure(report, args.output)
    print(json.dumps({'conditions': len(report['rows']), 'saved_attempts': report['saved_attempts'],
                      'differences': report['differences'], 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()

"""Create manuscript tables directly from the closed twelve-cell P55 audit."""
import json
from pathlib import Path

from build_inventory_report import TASKS, outcome, cost
from inventory_display import ARMS
from run_handoff_factors import ROOT, read, sha


def build():
    paths = ('reports/P55_comparison.json', 'reports/P55_prefix_checks.json',
             'reports/P55_full_control_variation.json', 'reports/P55_initial_inventory_visibility.json',
             'configs/P55_inventory_comparison_v01.json')
    report, pre, variation, _, _ = [read(ROOT / path) for path in paths]
    if not report['all_planned_cells_accounted'] or report['audit_errors'] or len(report['rows']) != 12:
        raise ValueError('complete accounting of all scheduled cells required')
    lines = ['% Generated from closed P55 evidence; no model or task execution.']
    lines += [r'\newcommand{\InventoryAllCells}{%',
              r'\begin{tabular}{llrr}\hline 課題 & 条件・成否 & 仕事全体token & 生成\\\hline']
    for task, label in TASKS:
        for index, arm in enumerate(ARMS):
            row = next(r for r in report['rows'] if r['task_id'] == task and r['arm'] == arm)
            value = cost(row).replace('＋不明', r'$+?$')
            calls = str(row['model_calls']) if row['record_status'] != 'not_run_after_stop' else '---'
            lines.append(f'{label if index == 0 else ""} & {"FDB"[index]}・{outcome(row)} & {value} & {calls}' + r'\\')
    lines += [r'\hline\end{tabular}}', r'\newcommand{\InventoryTotals}{%',
              r'\begin{tabular}{lrrr}\hline 指標 & F & D & B\\\hline']
    totals = [report['totals'][arm] for arm in ARMS]
    values = [('成功／評価済み', [f"{v['successes']}/{v['evaluated_trials']}" for v in totals])]
    for label, key in [('仕事全体・既知token', 'logical_task_known_total_tokens'),
                       ('継続・既知token', 'known_total_tokens'), ('使用量不明生成', 'unknown_usage_calls'),
                       ('生成', 'model_calls'), ('継続API', 'api_requests'), ('復元API', 'setup_api_requests')]:
        values.append((label, [f'{v[key]:,}' for v in totals]))
    values.append(('継続時間（秒）', [f"{v['continuation_wall_seconds']:,.1f}" for v in totals]))
    lines += [label + ' & ' + ' & '.join(v) + r'\\' for label, v in values]
    lines += [r'\hline\end{tabular}}', r'\newcommand{\InventoryFirstInputs}{%',
              r'\begin{tabular}{lrrr}\hline 課題 & F & D & B\\\hline']
    for (_, label), row in zip(TASKS, pre['rows'], strict=True):
        lines.append(label + ' & ' + ' & '.join(f"{row['conditions'][arm]['input_tokens']:,}" for arm in ARMS) + r'\\')
    lines += [r'\hline\end{tabular}}']
    c = report['record_status_counts']
    known = sum(v['known_total_tokens'] for v in totals)
    unknown = sum(v['unknown_usage_calls'] for v in totals)
    summary = (f"全12予定条件のうち{c.get('evaluated', 0)}件を評価し，"
        f"{c.get('attempted_unevaluated', 0)}件が未評価，{c.get('not_run_after_stop', 0)}件が未実行だった．"
        f"継続費用は既知{known:,} token，使用量不明は{unknown}生成だった．")
    if report['development_gate_met']:
        summary += '詳細省略Dは既知課題に対する固定の採用基準を満たした．独立した確認群での性能維持や一般的な省費用を示すものではない．'
    else:
        summary += '詳細省略Dは固定の採用基準を満たさず，品質を保った総費用削減として採用しない．'
    lines.append(r'\newcommand{\InventoryResultSummary}{' + summary + '}')
    contrast = []
    for arm, label in ((ARMS[0], '全表示F'), (ARMS[2], '一覧も省くB')):
        d = report['contrasts'][arm]
        if d['candidate_minus_control_work_tokens'] is None:
            contrast.append(label + 'に対する全４課題の確定費用差は算出しない．')
        else:
            diff = d['candidate_minus_control_work_tokens']
            contrast.append(f"Dは{label}より仕事全体で{abs(diff):,} token" + ('少なく' if diff < 0 else '多く' if diff > 0 else 'の差で') +
                f"，対ごとの成功喪失は{d['paired_success_losses']}件だった．")
    lines.append(r'\newcommand{\InventoryContrasts}{' + ''.join(contrast) + '}')
    changed = [r for r in variation['rows'] if r.get('independent_success') and
               all(isinstance(x, bool) for x in r['independent_success']) and
               r['independent_success'][0] != r['independent_success'][1]]
    lines.append(r'\newcommand{\InventoryVariation}{' +
        f'過去P47と今回P55の全表示条件について，両方を評価できた比較のうち{len(changed)}課題で成否が異なった．' +
        'これは事前に反復数を割り付けた追試ではなく，変更の原因や分散の推定には用いない．}')
    out = ROOT / 'papers/202610_letter'
    target = out / 'inventory_tables.tex'; target.write_text('\n'.join(lines) + '\n')
    manifest = {'sources': {path: sha(ROOT / path) for path in paths},
        'table_sha256': sha(target), 'builder_sha256': sha(Path(__file__)),
        'all_scheduled_cells': 12, 'official_class_used': False, 'submission_ready': False,
        'rendering_up_to_date': False, 'new_model_calls': 0, 'new_api_requests': 0}
    (out / 'inventory_draft_source_map.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('P55 manuscript tables generated from the closed audit.')


if __name__ == '__main__': build()

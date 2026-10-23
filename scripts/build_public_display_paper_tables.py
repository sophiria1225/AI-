"""Build complete P55/P71 tables from both closed audits, without inference."""
import json
from pathlib import Path

from build_inventory_report import TASKS
from public_display import ARMS, validate_plan
from run_handoff_factors import ROOT, read, sha

LABELS = ('写真', '精算', '返金', '書出')


def value(row):
    if row['record_status'] == 'not_run_after_stop':
        return '未実行'
    status = ('成功' if row['success'] else '未達') if row['record_status'] == 'evaluated' else '未評価'
    unknown = r'$+?$' if row['logical_task_unknown_usage_calls'] else ''
    return status + ' ' + f"{row['logical_task_known_total_tokens']:,}" + unknown


def validated(root):
    plan = read(root / 'configs/P71_public_display_v01.json')
    validate_plan(plan)
    reports = [read(root / f'reports/{phase}_comparison.json') for phase in ('P55', 'P71')]
    expected = {(tid, arm) for tid, _ in TASKS for arm in ARMS}
    for phase, report in zip(('P55', 'P71'), reports, strict=True):
        if (report['phase'] != phase or report['audit_errors'] or not report['all_planned_cells_accounted']
                or len(report['rows']) != 12
                or {(r['task_id'], r['arm']) for r in report['rows']} != expected
                or report['batch_status'] not in ('complete', 'stopped')):
            raise ValueError('closed complete accounting of each fixed cohort required')
        for row in report['rows']:
            if row['record_status'] == 'evaluated' and type(row['success']) is not bool:
                raise ValueError('evaluated row requires the recorded Boolean outcome')
            if (row['record_status'] != 'not_run_after_stop'
                    and row['logical_task_known_total_tokens'] != row['prefix_known_total_tokens'] + row['known_total_tokens']):
                raise ValueError('whole-work accounting differs')
    if reports[1]['catalog_policy'] != 'public_names':
        raise ValueError('P71 requires common public-name admission')
    return reports


def build(root=ROOT):
    reports = validated(root)
    paths = ('reports/P55_comparison.json', 'reports/P71_comparison.json',
             'reports/P55_prefix_checks.json', 'reports/P71_prefix_checks.json',
             'configs/P71_public_display_v01.json')
    preflights = [read(root / f'reports/{phase}_prefix_checks.json') for phase in ('P55', 'P71')]
    if any(p['status'] != 'complete' or len(p['rows']) != 4 for p in preflights):
        raise ValueError('all initial inputs must be counted')
    for phase, report in zip(('P55', 'P71'), reports, strict=True):
        if report['source_sha256']['preflight'] != sha(root / f'reports/{phase}_prefix_checks.json'):
            raise ValueError('input-count source differs from the audited run')
    lines = [r'% P55/P71 all 24 planned display cells. Four distinct known tasks.',
             r'\newcommand{\PublicDisplayAllCells}{%',
             r'{\setlength{\tabcolsep}{2.5pt}',
             r'\begin{tabular}{llrrr}\hline 接続 & 課題 & F & D & B\\\hline']
    for label, report in zip(('G', 'N'), reports, strict=True):
        for number, ((tid, _), short) in enumerate(zip(TASKS, LABELS, strict=True)):
            cells = [next(r for r in report['rows'] if r['task_id'] == tid and r['arm'] == a) for a in ARMS]
            lines.append(f'{label if number == 0 else ""} & {short} & ' + ' & '.join(map(value, cells)) + r'\\')
        lines.append(r'\hline')
    lines += [r'\end{tabular}}}', r'\newcommand{\PublicDisplayTotals}{%',
              r'\begin{tabular}{lrrr}\hline 指標 & F & D & B\\\hline']
    for label, report in zip(('文書取得必須（P55）', '公開名（P71）'), reports, strict=True):
        totals = [report['totals'][a] for a in ARMS]
        lines.append(r'\multicolumn{4}{l}{' + label + r'}\\')
        rows = [('成功／評価', [f"{t['successes']}/{t['evaluated_trials']}" for t in totals]),
                ('仕事・既知token', [f"{t['logical_task_known_total_tokens']:,}" +
                 (r'$+?$' if t['logical_task_unknown_usage_calls'] else '') for t in totals]),
                ('継続・既知token', [f"{t['known_total_tokens']:,}" +
                 (r'$+?$' if t['unknown_usage_calls'] else '') for t in totals]),
                ('継続生成／不明', [f"{t['model_calls']}/{t['unknown_usage_calls']}" for t in totals]),
                ('継続／復元API', [f"{t['api_requests']}/{t['setup_api_requests']}" for t in totals])]
        lines.extend(label + ' & ' + ' & '.join(cells) + r'\\' for label, cells in rows)
        lines.append(r'\hline')
    lines += [r'\end{tabular}}', r'\newcommand{\PublicDisplayInitialSavings}{%',
              r'\begin{tabular}{lrrrr}\hline 接続 & 写真 & 精算 & 返金 & 曲書出し\\\hline']
    for label, pre in zip(('文書必須', '公開名'), preflights, strict=True):
        if [r['source_run'] for r in pre['rows']] != [f'P29_{n:02d}_CODE' for n in range(1, 5)]:
            raise ValueError('preflight task order changed')
        savings = [r['conditions'][ARMS[0]]['input_tokens'] - r['conditions'][ARMS[1]]['input_tokens']
                   for r in pre['rows']]
        if savings != pre['detail_control_allocation_gate']['removed_tokens']:
            raise ValueError('initial savings differ from counted inputs')
        lines.append(label + ' & ' + ' & '.join(f'{n:,}' for n in savings) + r'\\')
    lines += [r'\hline\end{tabular}}']
    current = reports[1]; counts = current['record_status_counts']
    totals = [current['totals'][a] for a in ARMS]
    summary = (f"公開名接続では全12予定条件のうち{counts.get('evaluated', 0)}件を評価，"
               f"{counts.get('attempted_unevaluated', 0)}件が未評価，{counts.get('not_run_after_stop', 0)}件が未実行だった．"
               f"継続費用は既知{sum(t['known_total_tokens'] for t in totals):,} token，"
               f"使用量不明は{sum(t['unknown_usage_calls'] for t in totals)}生成だった．")
    lines.append(r'\newcommand{\PublicDisplaySummary}{' + summary + '}')
    contrast = []
    for arm, label in ((ARMS[0], 'F'), (ARMS[2], 'B')):
        item = current['contrasts'][arm]; delta = item['candidate_minus_control_work_tokens']
        if delta is None:
            contrast.append(f'Dと{label}の全４課題の確定費用差は算出しない．')
        else:
            phrase = (f'Dは{label}より{abs(delta):,} token' + ('少なく' if delta < 0 else '多く')) if delta else f'Dと{label}は同額で'
            contrast.append(f"{phrase}，対ごとの成功喪失は{item['paired_success_losses']}件だった．")
    contrast.append('固定した開発上の採用条件は' + ('満たした' if current['development_gate_met'] else '満たさなかった') + '．')
    lines.append(r'\newcommand{\PublicDisplayContrasts}{' + ''.join(contrast) + '}')
    target = root / 'papers/202610_letter/public_display_tables.tex'
    target.write_text('\n'.join(lines) + '\n')
    manifest = {'sources': {p: sha(root / p) for p in paths}, 'table_sha256': sha(target),
        'builder_sha256': sha(Path(__file__)), 'planned_display_cells': 24, 'distinct_known_tasks': 4,
        'cohort_labels': {'G': 'P55_documentation_required', 'N': 'P71_public_names_for_continuation'},
        'cohorts_are_independent': False, 'historical_access_difference_is_causal': False,
        'new_model_calls': 0, 'new_api_requests': 0, 'rendering_up_to_date': False}
    (target.parent / 'public_display_table_sources.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print({'planned_cells': 24, 'distinct_tasks': 4, 'table_sha256': manifest['table_sha256']})


if __name__ == '__main__': build()

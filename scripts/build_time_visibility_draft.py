"""Populate a separate working manuscript from all closed P80 conditions."""
from datetime import datetime, timezone
from pathlib import Path

from build_budget_visibility_report import TASKS, cost, outcome, totals, validated
from budget_observation import POLICIES
from budget_visibility_comparison import cell_id
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def build():
    _, report, _, session = validated()
    local = read(ROOT / 'reports/P79_clock_notice_replay.json')
    if (not local['all_twelve_audited'] or local['audit_errors']
            or local['model_calls_attempted'] != 12 or local['known_total_tokens'] != 99966
            or any(local[k] for k in ('unknown_usage_calls', 'environment_api_requests',
                                      'generated_programs_executed', 'evaluations'))):
        raise ValueError('closed_local_calibration_differs_from_draft')
    folder = ROOT / 'papers/202610_letter/time_visibility_focus'
    target = folder / 'results.tex'
    if target.exists():
        raise FileExistsError('preserve the first full-cohort draft; revise explicitly')
    table = [r'\begin{table}[tb]', r'\centering\small\setlength{\tabcolsep}{4pt}',
        r'\caption{既知４課題の全８条件．M：実測残時間表示，H：非表示．費用は全論理入出力token．}',
        r'\begin{tabular}{llrrr}',
        r'課題・条件 & 成否 & 費用 & 生成 & API \\ \hline']
    for n, task in enumerate(TASKS, 1):
        for policy, label in zip(POLICIES, ('M', 'H'), strict=True):
            row = next(r for r in report['rows'] if r['run_id'] == cell_id(n, policy))
            table.append(' & '.join((('写真', '精算', '返金', '書出し')[n-1] + ' ' + label, outcome(row), cost(row),
                str(row.get('model_calls', '---')), str(row.get('api_requests', '---')))) + r' \\')
    table += [r'\hline', r'\end{tabular}', r'\end{table}']
    a, b = [totals(report['rows'], policy) for policy in POLICIES]
    table.append(f'Mは{a["evaluated"]}条件中{a["successes"]}成功，'
                 f'Hは{b["evaluated"]}条件中{b["successes"]}成功だった．'
                 f'全論理入出力はMが{cost(a)}，Hが{cost(b)}である．')
    delta = report['not_exposed_minus_measured_whole_task_tokens']
    if delta is not None:
        table.append(f'H−Mの合計差は{delta:+,} tokenであり，'
                     f'成功喪失{report["paired_success_losses"]}課題，'
                     f'成功獲得{report["paired_success_gains"]}課題，'
                     f'両条件成功{report["paired_successful_tasks"]}課題だった．')
    else:
        table.append('未評価または使用量不明を含むため，全費用差は確定しない．')
    table.append('事前の開発上の採用基準は' +
                 ('満たした' if report['development_gate_met'] else '満たさなかった') +
                 '．単一実行の合計差を平均的改善や一般的な品質維持とは解釈しない．')
    table.append(f'作業時間の合計はMが{a["wall_seconds"]:,.1f}秒，'
                 f'Hが{b["wall_seconds"]:,.1f}秒であり，論理tokenとは別に報告する．')
    table.append(f'全条件合計は{a["model_calls"] + b["model_calls"]}生成，'
                 f'{a["api_requests"] + b["api_requests"]} API，'
                 f'{a["invocation_exceptions"] + b["invocation_exceptions"]} API例外である．'
                 f'所有推論器の滞在時間は{session["wall_seconds"]:,.1f}秒，'
                 f'この内に含まれる独立評価の時間は{session["evaluation_wall_seconds"]:.2f}秒だった．')
    table.append('表示説明文の差により，Hの初回入力は全課題でMより12 token多い．'
                 '従って入力文の単純な短縮を評価した比較ではない．'
                 '各条件の入出力，cache入力，準備・作業・後片付け時間は全件表に保存する．')
    target.write_text('\n'.join(table) + '\n')
    sources = ('reports/P80_comparison.json', 'reports/P80_server_session.json',
        'reports/P80_initial_checks.json', 'reports/P79_clock_notice_replay.json',
        'reports/P73_stop_diagnosis.json',
        'configs/P80_budget_visibility_v01.json',
        'papers/202610_letter/time_visibility_focus/draft.tex')
    manifest = {'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {name: sha(ROOT / name) for name in sources},
        'builder_sha256': sha(Path(__file__)), 'results_sha256': sha(target),
        'all_eight_conditions_included': True, 'primary_manuscript_replaced': False,
        'professor_brief_changed': False, 'authors_confirmed': False,
        'novel_method_claim': False, 'submission_ready': False, 'visual_reviewed': False}
    write_json(folder / 'build_manifest.json', manifest)
    print({'rows': 8, 'development_gate_met': report['development_gate_met'],
           'primary_manuscript_replaced': False})


if __name__ == '__main__':
    build()

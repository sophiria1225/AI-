"""Build all P76 result rows only after the fixed batch and owned server close."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from build_reasoning_history_report import save
from audit_reasoning_history_comparison import development_gate
from reasoning_comparison import ARMS, validate_plan
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_reasoning_comparison_20261023'
FILES = ('configs/P76_reasoning_history_v01.json', 'reports/P76_comparison.json',
         'reports/P76_prefix_checks.json', 'reports/P76_server_session.json')
LABELS = ('公開履歴のみ', '推論も保持')
TASKS = ('写真整理', '精算', '返金', '曲情報の書出し')


def validated():
    plan, report, preflight, session = [read(ROOT / p) for p in FILES]
    validate_plan(plan)
    if (report['phase'] != 'P76' or report['batch_status'] not in ('complete', 'stopped')
            or report['audit_errors'] or not report['all_planned_cells_accounted']
            or len(report['rows']) != 8 or session['status'] != 'stopped'
            or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(ROOT / FILES[1])
            or report['source_sha256']['plan'] != sha(ROOT / FILES[0])
            or report['source_sha256']['preflight'] != sha(ROOT / FILES[2])
            or preflight['git_commit'] != '902d9d9ec00fb121507581342464b9eb746c38b1'
            or preflight['status'] != 'complete' or not preflight['all_eight_inputs_checked']):
        raise ValueError('closed_audited_P76_batch_and_server_required')
    for key, value in development_gate(report['rows']).items():
        if report[key] != value: raise ValueError('fixed_development_decision_disagrees')
    original = read(ROOT / plan['source_plan'])
    tasks = [row[0] for row in original['run_order']]
    expected = [(f'P76_{n:02d}_{arm.upper()}', task, arm)
                for n, task in enumerate(tasks, 1) for arm in ARMS]
    if [(r['run_id'], r['task_id'], r['arm']) for r in report['rows']] != expected:
        raise ValueError('all_eight_planned_cells_must_be_retained')
    for arm in ARMS:
        rows = [r for r in report['rows'] if r['arm'] == arm]; total = report['totals'][arm]
        if (total['successes'] != sum(r['success'] is True for r in rows)
                or total['evaluated_trials'] != sum(r['record_status'] == 'evaluated' for r in rows)):
            raise ValueError('whole_cohort_quality_totals_disagree')
        for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                    'setup_api_requests', 'logical_task_known_total_tokens', 'logical_task_unknown_usage_calls'):
            if total[key] != sum(r[key] for r in rows):
                raise ValueError('whole_cohort_cost_totals_disagree')
    return report, preflight, session, {p: sha(ROOT / p) for p in FILES}


def cost(known, unknown):
    return f'{known:,}' + (f'＋不明{unknown}' if unknown else '')


def outcome(row):
    if row['record_status'] != 'evaluated':
        return '未実行' if row['record_status'] == 'not_run_after_stop' else '未評価'
    return '成功' if row['success'] else '未達'


def paired_differences(report):
    return '／'.join(task + (' 未確定' if row['candidate_minus_control_work_tokens'] is None
        else f' {row["candidate_minus_control_work_tokens"]:+,}')
        for task, row in zip(('写真', '精算', '返金', '書出し'), report['paired_results'], strict=True))


def paper_component(report, preflight, session):
    """Render the complete fixed cohort; this function invents no missing result."""
    rows = report['rows']; totals = [report['totals'][arm] for arm in ARMS]
    def cell(row):
        if row['record_status'] == 'not_run_after_stop': return '未実行 ---'
        value = f'{row["logical_task_known_total_tokens"]:,}'
        if row['logical_task_unknown_usage_calls']: value += r'$+?$'
        return outcome(row) + ' ' + value
    lines = [
        '% All eight P76 conditions; generated only from the closed audited batch.',
        r'\section{推論履歴を保持する通常対照}',
        '同じ既知４課題の８応答後から，公開履歴のみ（P）と返却推論も全て保持（R）を各１回比較した．',
        '両条件は公開履歴・持続Python・公開名接続・予算を共通にし，過去と以後の推論の投入だけを変えた．',
        '各16生成・120,000 token・480秒で，最初の生成はcacheを使わない．',
        '共通前半は推論を再投入せず生成しており，最初からの方針比較ではない．',
        r'\begin{center}\begin{minipage}{\columnwidth}\centering',
        r'\small 推論保持比較の全８条件：成否・仕事token\par\smallskip',
        r'\begin{tabular}{lrr}\hline 課題 & P：公開履歴のみ & R：推論も保持\\\hline',
    ]
    for index, task in enumerate(('写真', '精算', '返金', '書出')):
        lines.append(task + ' & ' + cell(rows[index * 2]) + ' & ' + cell(rows[index * 2 + 1]) + r'\\')
    lines += [r'\hline', '成功／評価 & ' + ' & '.join(f'{t["successes"]}/{t["evaluated_trials"]}' for t in totals) + r'\\',
              '既知token合計 & ' + ' & '.join(f'{t["logical_task_known_total_tokens"]:,}'
                  + (r'$+?$' if t['logical_task_unknown_usage_calls'] else '') for t in totals) + r'\\',
              r'\hline\end{tabular}', r'\end{minipage}\end{center}']
    deltas = '・'.join(f'{r["reasoning_minus_public_first_input_tokens"]:,}' for r in preflight['rows'])
    lines.append('Rの初回入力は課題順に' + deltas + ' token増えた．')
    if report['all_eight_complete_with_known_usage']:
        delta = report['candidate_minus_control_work_tokens']
        lines.append(f'全条件の使用量は既知で，R−Pの仕事token合計は{delta:+,}だった．'
                     f'対応する成功喪失は{report["paired_success_losses"]}課題，成功増加は{report["paired_success_gains"]}課題だった．')
    else:
        unknown = sum(t['logical_task_unknown_usage_calls'] for t in totals)
        evaluated = sum(t['evaluated_trials'] for t in totals)
        lines.append(f'全８予定条件のうち{evaluated}条件を評価し，使用量不明は{unknown}生成だった．'
                     '欠測を補完せず，採用判定に用いる確定費用差は求めない．')
    lines.append('課題別のR−Pの仕事token差は，' + paired_differences(report) + 'だった．')
    gate = '満たした' if report['development_gate_met'] else '満たさなかった'
    lines.append('全８評価・全使用量既知・少なくとも１対成功・成功喪失０・全体費用減少という局所採用条件は' + gate + '．')
    calls = sum(t['model_calls'] for t in totals); tokens = sum(t['known_total_tokens'] for t in totals)
    unknown = sum(t['unknown_usage_calls'] for t in totals)
    extra = f'＋使用量不明{unknown}生成' if unknown else '，使用量不明０'
    lines.append(f'新規継続は{calls}生成・既知{tokens:,} token{extra}，'
                 f'継続{sum(t["api_requests"] for t in totals)}・復元{sum(t["setup_api_requests"] for t in totals)} APIだった．')
    lines.append(f'推論器全稼働{session["wall_seconds"]:,.3f}秒に復元・評価も含め，重複加算しない．')
    lines.append('保持は通常の比較条件であり，新規手法や一般的な非劣性の実証とはしない．表2・3の過去条件は変更しない．')
    return '\n'.join(lines) + '\n'


def build(output):
    report, preflight, session, sources = validated()
    output.mkdir(parents=True, exist_ok=True)
    fields = ('run_id', 'task_id', 'arm', 'record_status', 'success', 'stop_reason', 'model_calls',
              'known_total_tokens', 'unknown_usage_calls', 'logical_task_known_total_tokens',
              'logical_task_unknown_usage_calls', 'api_requests', 'prefix_api_requests', 'setup_api_requests',
              'continuation_wall_seconds', 'setup_wall_seconds', 'evaluation_wall_seconds')
    with (output / 'all_reasoning_conditions.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(report['rows'])
    slides = [dict(title='推論過程を保持すると<br>仕事全体の費用はどう変わるか', cover=True)]
    def add(title, body, takeaway, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, notes=notes, cover=False))
    initial = ''.join(f'<tr><td>{task}</td><td>{row["conditions"][ARMS[0]]["input_tokens"]:,}</td>'
        f'<td>{row["conditions"][ARMS[1]]["input_tokens"]:,}</td><td>+{row["reasoning_minus_public_first_input_tokens"]:,}</td></tr>'
        for task, row in zip(TASKS, preflight['rows'], strict=True))
    add('同じ公開履歴・Python状態・予算から全８条件',
        '<p class="body">既知４課題の８応答後から各１回。保持側は過去と以後の推論を全て保持。</p>'
        '<table><tr><th>課題</th><th>公開履歴のみ</th><th>推論も保持</th><th>初回入力の増加</th></tr>' + initial + '</table>'
        '<p class="body">各16生成・12万token・480秒、API上限と残予算通知も共通。</p>',
        '初回の入力増加だけでは、全体費用や最終品質の優劣は決まらない。',
        '共通前半は推論を再投入せず生成されたもの。途中から保持する比較であり、課題の最初からの保持方針ではない。保留12課題は未閲覧。')
    body = []
    for index, row in enumerate(report['rows']):
        attempted = row['record_status'] != 'not_run_after_stop'
        value = cost(row['logical_task_known_total_tokens'], row['logical_task_unknown_usage_calls']) if attempted else '—'
        body.append(f'<tr><td>{TASKS[index // 2]}</td><td>{LABELS[index % 2]}</td><td>{outcome(row)}</td>'
                    f'<td>{value}</td><td>{row["model_calls"] if attempted else "—"}</td>'
                    f'<td>{row["api_requests"] if attempted else "—"}</td></tr>')
    add('全８予定条件：失敗・不明費用もそのまま示す',
        '<table class="results"><tr><th>課題</th><th>条件</th><th>評価</th><th>仕事token</th><th>生成</th><th>継続API</th></tr>'
        + ''.join(body) + '</table>',
        '仕事tokenは共通前半＋継続の全入力・出力。cached inputも含む。',
        '前半は各条件の仕事費用へ一度加算するが、新しく生成した実験費用ではない。使用量不明を０や上限で埋めず、未実行・未評価を成功率の分母へ混ぜない。')
    totals = [report['totals'][arm] for arm in ARMS]
    total_rows = ''.join(f'<tr><td>{label}</td><td>{t["successes"]}/{t["evaluated_trials"]}</td>'
        f'<td>{cost(t["logical_task_known_total_tokens"], t["logical_task_unknown_usage_calls"])}</td>'
        f'<td>{t["model_calls"]}</td><td>{t["api_requests"]}</td></tr>' for label, t in zip(LABELS, totals, strict=True))
    delta = report['candidate_minus_control_work_tokens']
    difference = f'保持あり−公開履歴の仕事token合計：{delta:+,}。' if delta is not None else '不明・欠測があるため、正確な仕事token合計差は未確定。'
    decision = ('既知群の局所採用基準を満たした。一般的な品質維持の証明ではない。'
                if report['development_gate_met'] else '今回の局所採用基準は未達。元の比較条件と全結果を残す。')
    add('品質と仕事全体の費用を一緒に判定する',
        '<table><tr><th>条件</th><th>成功／評価</th><th>仕事token合計</th><th>生成</th><th>継続API</th></tr>' + total_rows + '</table>'
        f'<p class="lead">{difference}</p>'
        f'<p class="body">課題別の保持あり−なし：{paired_differences(report)} token。</p>'
        '<p class="body">全８評価・全使用量既知・少なくとも１対成功・成功喪失０・全体費用減少を要求。</p>',
        decision,
        '別課題の成功増加で成功喪失を相殺しない。全失敗で安く終わる場合も採用しない。失敗を含む全条件の合計を報告し、有利な課題だけを選ばない。')
    new_calls = sum(t['model_calls'] for t in totals)
    known = sum(t['known_total_tokens'] for t in totals); unknown = sum(t['unknown_usage_calls'] for t in totals)
    apis = sum(t['api_requests'] for t in totals); restores = sum(t['setup_api_requests'] for t in totals)
    evaluation = session['evaluation_wall_seconds']
    evaluation_text = f'{evaluation:.3f}秒' if evaluation is not None else '未確定'
    add('保持の費用・失敗・復元まで記録して比較を閉じる',
        f'<p class="body">新しい生成 {new_calls}回、継続 {cost(known, unknown)} token。<br>'
        f'継続 {apis}＋復元 {restores}＝{apis + restores} API。</p>'
        f'<p class="body">専有推論器 {session["wall_seconds"]:.3f}秒、ロード {session["load_wall_seconds"]:.3f}秒。<br>'
        f'評価subprocessの実測合計 {evaluation_text}。推論器の停止とプロセス不在を確認。</p>'
        '<ul><li>４つの既知課題・各１回。統計的非劣性の検証ではない。</li>'
        '<li>推論保持は通常対照の条件で、新提案手法ではない。</li></ul>',
        '新提案の中核は未確立。次の主張は、この比較で支えられる範囲に限る。',
        '構成・通知・入力計数・フィードバックは継続時間の内側、評価は全batch時間の内側。重複する時間を足さない。P55/P71/P66/P68の結果は書き換えない。')
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 通常の推論保持比較 / {number-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P76_findings.md">全結果と限界</a></span>'
                f'<span>{number}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:31px}table{font-size:18px}td{padding:9px 12px}.results td,.results th{font-size:17px;padding:6px 10px}li{font-size:23px;margin:13px 0}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P76 推論保持の通常対照</title><style>' + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    save(output / 'slides.json', slides)
    component = ROOT / 'papers/202610_letter/reasoning_comparison_component.tex'
    component.write_text(paper_component(report, preflight, session))
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'builder_sha256': sha(Path(__file__)), 'source_sha256': sources, 'visual_reviewed': False,
        'component_sha256': sha(component),
        'csv_sha256': sha(output / 'all_reasoning_conditions.csv'), 'claims': {
            'evaluated': [t['evaluated_trials'] for t in totals], 'successes': [t['successes'] for t in totals],
            'whole_work_known_tokens': [t['logical_task_known_total_tokens'] for t in totals],
            'unknown_usage_calls': [t['logical_task_unknown_usage_calls'] for t in totals],
            'development_gate_met': report['development_gate_met'], 'new_model_calls': new_calls,
            'known_continuation_tokens': known, 'continuation_api_requests': apis, 'restoration_api_requests': restores,
            'novel_method_claim': False, 'general_quality_preservation_claim': False},
        'shared_rendering_sha256': {p: sha(ROOT / 'scripts' / p) for p in ('build_morning_report.py', 'build_budget_report.py')}}
    save(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p76')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    result = build(args.output); print({k: result[k] for k in ('pages', 'claims')})
    if args.pdf: build_budget_report.STEM = STEM; build_budget_report.export(args.output)

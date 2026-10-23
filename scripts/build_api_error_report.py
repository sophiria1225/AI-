"""Publish all eight closed P78 cells without changing the frozen experiment."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from api_error_comparison import ARMS, cell_id, run_order, validate_plan
from audit_api_error_comparison import development_gate
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_api_error_comparison_20261023'
TASKS = ('写真整理', '精算', '返金', '曲情報の書出し')
LABELS = ('エラーを文字列で返す', 'Python例外として通知')
FILES = ('configs/P78_api_error_v01.json', 'reports/P78_comparison.json',
         'reports/P78_initial_checks.json', 'reports/P78_server_session.json')


def validated():
    plan, report, pre, session = [read(ROOT / name) for name in FILES]
    validate_plan(plan)
    expected = [(cell_id(n, arm), plan['known_tasks'][n - 1]['task_id'], arm) for n, arm in run_order()]
    if ([(r['run_id'], r['task_id'], r['arm']) for r in report['rows']] != expected
            or report['audit_errors'] or report['batch_status'] not in ('complete', 'stopped')
            or pre['status'] != 'complete' or not pre['all_eight_inputs_checked']
            or pre['git_commit'] != '5971a0d2db71034329eafd91fc69161d16c1d91e'
            or report['plan_sha256'] != sha(ROOT / FILES[0])
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(ROOT / FILES[1])):
        raise ValueError('closed_audited_P78_cohort_and_stopped_owned_server_required')
    for key, value in development_gate(report['rows'], report['audit_errors']).items():
        if report[key] != value:
            raise ValueError('frozen_development_gate_disagrees')
    for row in pre['rows']:
        a, b = [row['conditions'][arm] for arm in ARMS]
        if a['model_messages_sha256'] != b['model_messages_sha256'] or a['input_tokens'] != b['input_tokens']:
            raise ValueError('initial_inputs_not_matched')
    return plan, report, pre, session, {name: sha(ROOT / name) for name in FILES}


def cost(row):
    value, unknown = row.get('known_total_tokens'), row.get('unknown_usage_calls')
    if value is None:
        return '未計測'
    missing = row.get('planned', 0) - row.get('measured', 0)
    return (f'{value:,}' + (f'＋不明{unknown}' if unknown else '')
            + (f'＋未計測{missing}条件' if missing else ''))


def outcome(row):
    if row['record_status'] != 'evaluated':
        return '未実行' if row['record_status'] == 'not_run' else '未評価'
    return '成功' if row['success'] else '未達'


def totals(rows, arm):
    cells = [r for r in rows if r['arm'] == arm]
    measured = [r for r in cells if r.get('known_total_tokens') is not None]
    return {'arm': arm, 'planned': len(cells), 'measured': len(measured),
        'evaluated': sum(r['record_status'] == 'evaluated' for r in cells),
        'successes': sum(r['success'] is True for r in cells),
        **{key: sum(r.get(key, 0) for r in measured) for key in
           ('known_total_tokens', 'unknown_usage_calls', 'model_calls', 'api_requests', 'invocation_exceptions')}}


def figures(output, plan, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    folder = output / 'figures'; folder.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 3.5), layout='constrained', facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    for n, item in enumerate(plan['known_tasks']):
        cells = {r['arm']: r for r in report['rows'] if r['task_id'] == item['task_id']}
        for j, arm in enumerate(ARMS):
            row = cells[arm]; color = ('#7d8892', '#177b79')[j]
            y = 3 - n + (-.13 if j == 0 else .13)
            if row.get('known_total_tokens') is None:
                ax.text(.02, y, LABELS[j] + '：未計測', transform=ax.get_yaxis_transform(), va='center')
                continue
            value = row['known_total_tokens'] / 1000
            marker = '>' if row['unknown_usage_calls'] else ('o', 'D')[j]
            ax.scatter(value, y, marker=marker, s=75, edgecolor=color,
                       facecolor=color if row['success'] is True else '#f6f4ed', lw=1.8)
            text = f'{value:.1f}' + ('＋不明' if row['unknown_usage_calls'] else '')
            ax.annotate(text, (value, y), xytext=(7, 0), textcoords='offset points', va='center', color=color)
    ax.set_yticks(range(4), TASKS[::-1]); ax.set_ylim(-.6, 3.6)
    ax.set_xlim(left=0); ax.margins(x=.25); ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    ax.set_xlabel('課題開始からの論理入力＋出力トークン（千）／塗り：成功、白抜き：未達・未評価')
    for j, label in enumerate(LABELS):
        ax.plot([], [], color=('#7d8892', '#177b79')[j], marker=('o', 'D')[j], linestyle='', label=label)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.2), ncol=2, frameon=False)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(folder / ('P78_whole_task_costs.' + ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)


def build(output):
    plan, report, pre, session, sources = validated()
    output.mkdir(parents=True, exist_ok=True)
    fields = ('run_id', 'task_id', 'arm', 'record_status', 'success', 'stop_reason', 'model_calls',
              'known_total_tokens', 'unknown_usage_calls', 'input_tokens', 'cached_input_tokens',
              'output_tokens', 'api_requests', 'invocation_exceptions', 'setup_wall_seconds',
              'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
    with (output / 'all_error_presentation_conditions.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(report['rows'])
    with (output / 'all_paired_results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report['paired_results'][0]))
        writer.writeheader(); writer.writerows(report['paired_results'])
    figures(output, plan, report)
    slides = [{'title': '状態保持型エージェントにおける<br>API失敗通知の比較',
               'cover': True, 'body': '', 'takeaway': '',
               'notes': '既知４課題の固定比較。表紙は題名のみ。'}]
    def add(title, body, takeaway, notes):
        slides.append({'title': title, 'body': body, 'takeaway': takeaway, 'notes': notes})
    initial = ''.join(f'<tr><td>{task}</td><td>{row["conditions"][ARMS[0]]["input_tokens"]:,}</td>'
                      '<td>両条件で一致</td></tr>' for task, row in zip(TASKS, pre['rows'], strict=True))
    add('失敗の伝え方を、仕事全体の成否と費用で比べる',
        '<p class="body">成功時の型付き値は共通。実際のAPI例外だけを、通常の文字列またはPython例外として返す。</p>'
        '<table><tr><th>既知課題</th><th>事前検査入力token</th><th>入力照合</th></tr>' + initial + '</table>'
        '<p class="body">最初から推論履歴を保持。持続Python、公開API名、予算も共通。</p>',
        '必要な処理と最終品質を保ち、失敗と再取得を含む総費用を減らすための診断。',
        '４課題×２条件を各１回。入力照合は経過０秒での事前検査。実行時は実測した残時間を毎回通知する。旧P29/P76の完全再現ではなく、例外通知自体を新規手法としない。')
    body = []
    for number, task in enumerate(TASKS, 1):
        for j, arm in enumerate(ARMS):
            row = next(r for r in report['rows'] if r['run_id'] == cell_id(number, arm))
            body.append('<tr>' + ''.join('<td>' + html.escape(str(v)) + '</td>' for v in
                (task, ('文字列', '例外')[j], outcome(row), cost(row), row.get('model_calls', '—'),
                 row.get('api_requests', '—'), row.get('invocation_exceptions', '—'))) + '</tr>')
    add('全８予定条件を、未達と欠測も含めて示す',
        '<table class="results"><tr><th>課題</th><th>条件</th><th>成否</th><th>全仕事token</th><th>生成</th><th>API</th><th>API例外</th></tr>'
        + ''.join(body) + '</table>', '課題開始からの全入力・出力を計上。制御、推論、失敗、回復も含む。',
        '不明は０で補完しない。API例外は型付き記録で確認した実際の呼出し例外で、業務上のfalse戻り値や書式拒否とは分ける。')
    add('小さな入力や短い失敗だけでは、効率化と判定しない',
        '<img class="cost-figure" src="figures/P78_whole_task_costs.svg" alt="全４課題の条件別費用と成否">',
        '同じ課題の品質と全費用を併せて読む。既知部分の減少だけでは合計差は確定しない。',
        '矢印マーカーは使用量不明を含む既知部分。塗りは公式成功。横軸はキャッシュ入力を含む論理tokenで、金額・時間の削減率ではない。')
    ts = [totals(report['rows'], arm) for arm in ARMS]
    total_rows = ''.join(f'<tr><td>{label}</td><td>{t["successes"]}/{t["evaluated"]}</td>'
        f'<td>{cost(t)}</td><td>{t["invocation_exceptions"]}</td></tr>' for label, t in zip(LABELS, ts, strict=True))
    delta = report['exception_minus_value_whole_task_tokens']
    difference = f'例外−文字列の全費用差：{delta:+,} token。' if delta is not None else '欠測があるため全費用合計の正確な差は求めない。'
    decision = '既知群での局所採用基準を満たした。' if report['development_gate_met'] else '既知群での局所採用基準は満たさなかった。'
    add('固定した品質と費用の基準で判定する',
        '<table><tr><th>条件</th><th>成功／評価</th><th>全仕事token合計</th><th>実API例外</th></tr>' + total_rows + '</table>'
        '<p class="lead">' + difference + '</p>'
        '<p class="body">全８評価・使用量既知・実API例外あり・双方成功の課題あり・成功喪失なし・全体費用減少を要求。</p>',
        decision + ' 一般的な品質維持や新規性の証明とは区別する。',
        '実例外がない条件では通知方法の違いが使われていない。事前検査の入力一致と、実行中の入力一致は別。計算の非決定性と実測残時間の差も残る。')
    add('記録を閉じ、主張できる範囲を残す',
        f'<p class="body">モデル生成 {sum(t["model_calls"] for t in ts)}回、API {sum(t["api_requests"] for t in ts)}回。<br>'
        f'専有推論器 {session["wall_seconds"]:,.3f}秒、ロード {session["load_wall_seconds"]:.3f}秒。<br>'
        f'独立評価の実測合計 {session["evaluation_wall_seconds"]:.3f}秒。</p>'
        '<ul><li>全条件の入力、予算、使用量、例外記録、独立評価を監査。</li>'
        '<li>所有サーバー停止とプロセス不在を確認。</li>'
        '<li>既知４課題・各１回。未開封12課題は使用しない。</li></ul>',
        '通常の実行設計を測った結果として、情報保持と実行制御の研究へつなぐ。',
        '準備、実作業、後始末、評価はサーバー滞在時間と重なる。重複加算しない。過去の成否と費用を修正後の結果で上書きしない。')
    sections = []
    for n, slide in enumerate(slides, 1):
        if slide.get('cover'):
            sections.append(f'<section class="slide dark cover"><h1>{slide["title"]}</h1>'
                            f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
            continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 API失敗通知の比較 / {n:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
            f'<div class="footer"><span>既知４課題・固定８条件</span><span>{n}/{len(slides)}</span></div>'
            f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:31px}table{font-size:18px}td{padding:9px 12px}.results td,.results th{font-size:16px;padding:6px 9px}.cost-figure{width:100%;height:350px;object-fit:contain}li{font-size:23px;margin:13px 0}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P78 API失敗通知の比較</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    write_json(output / 'slides.json', slides)
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'builder_sha256': sha(Path(__file__)), 'source_sha256': sources, 'visual_reviewed': False,
        'csv_sha256': sha(output / 'all_error_presentation_conditions.csv'),
        'paired_csv_sha256': sha(output / 'all_paired_results.csv'), 'totals': ts,
        'development_gate_met': report['development_gate_met'], 'novel_method_claim': False,
        'general_quality_preservation_claim': False}
    write_json(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p78')
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args()
    result = build(args.output)
    print({k: result[k] for k in ('pages', 'totals', 'development_gate_met')})
    if args.pdf:
        build_budget_report.STEM = STEM
        build_budget_report.export(args.output)

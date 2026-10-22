"""P40 report: explain the question before the method, using closed results only."""
import argparse
import csv
import datetime as dt
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile

from build_morning_report import STYLE, SCRIPT, svg, txt, line, circle, scope_diagram
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_budget_20261022'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'
ARMS = ('plain_keep', 'budget_keep')
LABELS = ('通知なし', '残予算を毎回通知')
TASKS = ('写真整理', '電気代の分担請求', '返金', '曲情報の書出')


def architecture():
    s = txt(20, 35, '同じ課題・同じ作業状態・同じ上限', 28, weight=700)
    for x, label, sub, color in ((95, 'AI', '次の処理を選ぶ', '#d9e7e2'),
                                 (490, 'ハーネス', '実行・記録・検査', '#f1d8c6'),
                                 (985, 'ツール', '検索・読取・変更', '#dce4ef')):
        s += circle(x, 150, 61, color)
        s += txt(x, 156, label, 27, weight=700, anchor='middle')
        s += txt(x, 238, sub, 22, anchor='middle')
    s += line(160, 150, 422, 150, arrow=True) + txt(290, 126, 'Pythonの処理を要求', 20, anchor='middle')
    s += line(558, 150, 915, 150, arrow=True) + txt(740, 126, '上限内でAPIを実行', 20, anchor='middle')
    s += '<path d="M985 214 V305 H20 V150 H32" fill="none" stroke="#177b79" stroke-width="3" marker-end="url(#arrow)"/>'
    s += txt(815, 289, '処理結果・利用したAPIの記録', 22, anchor='middle')
    s += '<path d="M548 170 H625 V365 H8 V180 H38" fill="none" stroke="#c66a38" stroke-width="4" marker-end="url(#arrow)"/>'
    s += txt(480, 395, '通知ありだけ：残API・token・呼出し・時間', 20, weight=700)
    return svg(s, h=410, label='ハーネスが実行費用を記録し、通知条件では次のAI判断へ残り予算を渡す')


def comparison_flow():
    s = circle(118, 190, 72, '#e3e9e2')
    s += txt(118, 185, '同じ', 26, weight=700, anchor='middle')
    s += txt(118, 219, '途中状態', 26, weight=700, anchor='middle')
    s += txt(118, 294, '会話・Python・アプリ', 20, anchor='middle')
    for y, label, sub, color in ((100, '通知なし', '元の入力で継続', '#7d8892'),
                                  (280, '毎回通知', '元の入力＋その時点の残予算', '#177b79')):
        s += f'<path d="M195 190 H260 V{y} H350" fill="none" stroke="{color}" stroke-width="3" marker-end="url(#arrow)"/>'
        s += txt(520, y - 14, label, 30, color=color, weight=700, anchor='middle')
        s += txt(520, y + 25, sub, 21, anchor='middle')
        s += line(735, y, 920, y, arrow=True)
        s += circle(985, y, 49, '#dce4ef')
        s += txt(985, y + 9, '評価', 26, weight=700, anchor='middle')
    s += txt(830, 195, 'それぞれの最終状態を', 21, anchor='middle')
    s += txt(830, 225, '同じ基準で判定', 21, anchor='middle')
    return svg(s, h=355, label='同じ会話、Python、アプリ状態から二条件へ分岐し、各最終状態を独立評価する')


def figures(output, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})
    folder = output / 'figures'; folder.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11.1, 3.45), layout='constrained', facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    for n in range(4):
        a, b = report['rows'][n * 2:n * 2 + 2]
        if any(r.get('record_status', 'evaluated') != 'evaluated' for r in (a, b)):
            ax.text(.03, 3 - n, '通知なし：未実行 ／ 通知あり：時間上限・使用量不明１回',
                    transform=ax.get_yaxis_transform(), fontsize=10, color='#596c79', va='center')
            continue
        vals = [r['known_total_tokens'] / 1000 for r in (a, b)]
        ax.plot(vals, [3 - n] * 2, color='#d3cbbb', lw=3, zorder=1)
        for j, (r, value) in enumerate(zip((a, b), vals)):
            color = ('#7d8892', '#177b79')[j]
            ax.scatter(value, 3 - n, s=100, marker=('o', 'D')[j], edgecolor=color,
                       facecolor=color if r['success'] else '#f6f4ed', lw=2, zorder=3,
                       label=LABELS[j] if n == 0 else None)
            ax.annotate(f'{value:.1f}', (value, 3 - n), xytext=(0, 12 if j else -20),
                        textcoords='offset points', ha='center', color=color, fontsize=9)
    ax.set_yticks(range(4), TASKS[::-1]); ax.set_ylim(-.65, 3.65)
    ax.set_xlabel('継続全体の入出力トークン（千・キャッシュ分を含む）'); ax.set_xlim(left=0)
    ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.21), ncol=2, frameon=False)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(folder / ('p40_paired_costs.' + ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)
    with (folder / 'p40_results.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=['run_id', 'task_id', 'arm', 'record_status', 'success',
            'known_total_tokens', 'unknown_usage_calls', 'model_calls', 'api_requests',
            'continuation_wall_seconds', 'stop_reason'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(report['rows'])


def build(root, output, terminated=False):
    results_ref = 'reports/P40_termination.json' if terminated else 'reports/P40_comparison.json'
    paths = (results_ref, 'reports/P40_prefix_checks.json',
             'reports/P40_budget_visibility.json', 'reports/P39_calibration_audit.json')
    report, prepared, visibility, calibration = [read(root / p) for p in paths]
    valid = (report.get('all_planned_cells_accounted') and report['status'] == 'stopped') if terminated else (
        report.get('all_eight_reviewed') and not any(r['unknown_usage_calls'] for r in report['rows']))
    if not valid or report['audit_errors'] or not calibration['all_six_validated']:
        raise ValueError('explicitly scoped audited evidence is required')
    if terminated:
        report['totals'] = {}
        for arm in ARMS:
            selected = [r for r in report['rows'] if r['arm'] == arm and r['record_status'] == 'evaluated']
            report['totals'][arm] = {k: sum(r[k] for r in selected) for k in
                ('known_total_tokens', 'model_calls', 'api_requests', 'continuation_wall_seconds')}
            report['totals'][arm].update(successes=sum(r['success'] for r in selected), trials=len(selected))
        report['paired_results'] = report['paired_observations_only']
    expected = [f'P40_{n:02d}_{a.upper()}' for n in range(1, 5) for a in ARMS]
    if [r['run_id'] for r in report['rows']] != expected:
        raise ValueError('all eight original cells must appear in the report')
    output.mkdir(parents=True, exist_ok=True); figures(output, report)
    slides = []
    def add(title, body='', take='', notes='', refs=(), cover=False):
        slides.append(dict(title=title, body=body, take=take, notes=notes, refs=list(refs), cover=cover))
    add('AIハーネスの実行予算制御と<br>総費用評価', cover=True)
    add('仕事の品質を保ち、不要な処理を減らす',
        '<p class="lead">AIに任せる仕事には、調査・判断・実行・確認が含まれる。</p>'
        '<div class="diagram tight">' + scope_diagram().replace('viewBox="0 0 1120 360"', 'viewBox="0 80 1120 250"') + '</div>'
        '<p class="body">ハーネスは、渡す情報・ツール実行・状態・検証・停止を制御する。<br>減らしたいのは、不要な取得・共有・追加生成・やり直しの総費用。</p>',
        notes='社会的な課題は複雑な仕事を利用可能な費用で完了すること。現在は単一作業役の基礎制御を検証中で、複数AIの通信削減を実証した段階ではない。',
        refs=(('研究目的', 'docs/research_objective_20261022.md'),))
    add('上限で止めても、仕事の完了は保証できない',
        '<div class="two"><div class="col"><h3>実行器がしていたこと</h3><p class="body">API・token・時間の上限を監視。<br>上限に届いたら処理を止める。</p></div>'
        '<div class="col"><h3>AIに伝えていなかったこと</h3><p class="body">あと何回APIを使えるか。<br>あとどれだけ生成・実行できるか。</p></div></div>'
        f'<p class="body">過去{visibility["cells_reviewed"]}条件・{visibility["calls_reviewed"]}入力を点検し、明示的な残予算通知がないことを確認。</p>',
        '仮説：残量を知れば、取得・実行・確認の配分が変わる可能性がある。',
        notes='通知がなかった事実だけで過去の失敗原因とは断定しない。Budget Tracker等の既存研究があるため、通知を追加すること自体は新提案ではない。',
        refs=(('入力監査', 'reports/P40_budget_visibility.json'), ('先行研究', 'docs/budget_control_overlap_20261022.md')))
    add('今回の実装：実行記録から残予算を毎回知らせる',
        '<div class="diagram">' + architecture() + '</div>',
        notes='通知は追加のAIを呼ばず、実測カウンターから作る。通知の文字や処理も費用へ含む。予測器は使わず、残量は必要量の予測や成功保証ではない。',
        refs=(('実装', 'scripts/budget_signal.py'), ('計画', 'docs/experiments/P40_budget_notification.md')))
    add('実験の前提：同じ途中状態から、通知だけを変える',
        '<p class="lead">AppWorldの模擬アプリ：写真整理／電気代の分担請求／返金／曲情報の書出。</p>'
        '<table><thead><tr><th>条件</th><th>AIが受け取る入力</th></tr></thead><tbody>'
        '<tr><td>通知なし</td><td>全履歴・現在の実行結果</td></tr>'
        '<tr><td>毎回通知</td><td>同じ情報 ＋ その時点の残予算</td></tr></tbody></table>'
        '<p class="body">８応答後の会話・Python・アプリ状態を復元。<br>各条件：16生成・12万token・480秒。APIは元の上限で前半も計上。</p>'
        '<p class="small">MiniMax M3 IQ4_XS。４課題×２条件×各１回。token・API・時間は別の費用として記録。</p>',
        notes='新たに初回だけ推論キャッシュの再利用を無効化し、実処理を確認した。同じ原状態での追加通知以外に、ツールや成功判定を変えない。確認用12シナリオは未閲覧。',
        refs=(('事前設定', 'configs/P40_budget_notification_v01.json'), ('入力照合', 'reports/P40_prefix_checks.json')))
    add('手順：開始状態をそろえ、継続後の成否と費用を測る',
        '<div class="diagram">' + comparison_flow() + '</div>'
        '<p class="body">８応答後の状態を各条件へ復元。評価結果は実行中のAIに返さない。</p>',
        notes='開始状態は同じだが、その後の行動や取得情報は方式に応じて変わり得る。元の記録を復元した準備費用と、続きの実行費用を分けて残す。途中で正解した成果物を後から選び直さず、実行終了時の成果物を判定する。',
        refs=(('復元と独立評価', 'scripts/run_handoff_factors.py'), ('比較計画', 'docs/experiments/P40_budget_notification.md')))
    if terminated:
        add('終了状況：評価済み６件、途中終了１件、未実行１件',
            '<div class="three"><div class="col"><div class="n">6</div><h3>最終評価まで終了</h3><p class="body">３課題の２条件。<br>使用量も確定。</p></div>'
            '<div class="col"><div class="n">1</div><h3>時間上限で終了</h3><p class="body">書出・通知あり。<br>最終生成の使用量不明。</p></div>'
            '<div class="col"><div class="n">1</div><h3>規則により未実行</h3><p class="body">書出・通知なし。<br>置換試行はしない。</p></div></div>',
            '予定した４課題の比較は未完遂。欠測を失敗０点や使用量０に置き換えない。',
            notes='13:31に事前の不明使用量停止規則が発動した。44生成、既知579759 tokenと不明１回、後続253 API、実験用復元84 API。六件の公式評価で成功３件だが、方式ごとの４課題成功率は出さない。',
            refs=(('全８条件の状態', results_ref),))
    summary = '<table class="compact"><thead><tr><th>条件</th><th>成功</th><th>継続token</th><th>AI呼出し</th><th>後続API</th><th>継続秒</th></tr></thead><tbody>'
    for arm, label in zip(ARMS, LABELS):
        t = report['totals'][arm]
        summary += f'<tr><td>{label}</td><td>{t["successes"]}/{t.get("trials", 4)}</td><td>{t["known_total_tokens"]:,}</td><td>{t["model_calls"]}</td><td>{t["api_requests"]}</td><td>{t["continuation_wall_seconds"]:.1f}</td></tr>'
    summary += '</tbody></table>'
    add('評価済み３課題：成否と費用を対応させる' if terminated else '結果：費用だけでなく、完了できた仕事を対応させる',
        '<div class="diagram"><img src="figures/p40_paired_costs.svg" style="width:100%;height:265px" alt="４課題それぞれの通知なし／ありの総トークン。塗りは成功、白抜きは未達"></div><p class="small">塗り：成功／白抜き：未達。共通前半・実験用の復元は別計上。未達の安さは効率化としない。</p>' + summary,
        notes='塗りつぶしは成功、白抜きは未達。未達の低費用は、仕事を終えるための節約とは扱わない。費用は継続全体の入出力、実験用の復元は別記。各１回なので優越性や非劣性を証明しない。',
        refs=(('全条件の状態・使用量', results_ref),))
    table = '<table><thead><tr><th>課題</th><th>通知なし</th><th>毎回通知</th><th>通知あり−なしのtoken</th></tr></thead><tbody>'
    for name, p in zip(TASKS, report['paired_results']):
        table += f'<tr><td>{name}</td><td>{"成功" if p["plain_success"] else "未達"}</td><td>{"成功" if p["notified_success"] else "未達"}</td><td>{p["notified_minus_plain_tokens"]:+,}</td></tr>'
    if terminated:
        table += '<tr><td>曲情報の書出</td><td>未実行</td><td>途中終了・未評価</td><td>比較不可</td></tr>'
    table += '</tbody></table>'
    add('課題ごとの対応：成功と打切りを混ぜて評価しない', table,
        '同じ成功件数だけでは、同じ課題を解けたことや一般的な品質維持を示せない。',
        notes='減少は負、増加は正。成功が入れ替わった場合も全行を示す。小標本の結果からモデル一般や別領域へ広げない。',
        refs=(('対応結果', results_ref), ('少数評価の限界', 'docs/letter_evaluation_scope_20261021.md')))
    if terminated:
        admission_path = 'reports/P40_admission_stopped.json'
        admission = read(root / admission_path)
        if admission['status'] != 'complete' or admission['completion_requests']:
            raise ValueError('input-only admission audit required')
        paths = paths + (admission_path,)
        labels = {'P40_01_PLAIN_KEEP': '写真整理・通知なし', 'P40_02_PLAIN_KEEP': '分担請求・通知なし',
                  'P40_02_BUDGET_KEEP': '分担請求・毎回通知'}
        content = '<p class="lead">実行器は「次の入力＋最大4,096出力token」を予約していた。</p>'
        content += '<table><thead><tr><th>予約上限で停止した条件</th><th>残token</th><th>次の入力</th><th>出力に残せる量</th></tr></thead><tbody>'
        for r in admission['rows']:
            content += f'<tr><td>{labels[r["run_id"]]}</td><td>{r["remaining_tokens"]:,}</td><td>{r["next_input_tokens"]:,}</td><td>{r["positive_output_capacity"]:,}</td></tr>'
        content += '</tbody></table><p class="body">終了後に入力長だけを再計数。生成・環境操作は追加していない。</p>'
        add('考察：残予算と、呼出しを止める規則を分ける', content,
            '２条件には短い出力枠が残る。ただし、それで仕事を完了できるかは未検証。',
            notes='総予算は増やさず、出力予約の仕方によって生成開始の可否が変わる場合がある。残量に合わせた出力上限も通常の制御候補であり、その実装だけを新規性にはしない。P40の比較条件は後から変更していない。',
            refs=(('入力計数と限界', admission_path), ('分析規則', 'docs/P40_analysis_plan.md')))
    else:
        a, b = calibration['groups']['cold'], calibration['groups']['warm']
        add('比較を整えた点：前の実験の入力キャッシュを使わない',
            '<p class="lead">直前の校正では、同じ入力・seedでも再利用の有無で生成が異なった。</p>'
            '<table><thead><tr><th>短い校正生成</th><th>入力の実処理/回</th><th>平均時間</th></tr></thead><tbody>'
            f'<tr><td>再利用なし３回</td><td>13,552 token</td><td>{a["mean_wall_seconds"]:.2f}秒</td></tr>'
            f'<tr><td>再利用あり３回</td><td>1 token</td><td>{b["mean_wall_seconds"]:.2f}秒</td></tr></tbody></table>'
            '<p class="body">P40では両条件の初回を再利用なしに統一。<br>課題内の継続は通常の再利用を認め、実量を記録する。</p>',
            notes='校正は１入力・最大256生成tokenで、タスク成功率を比較していない。既知の実装挙動を確認したもので、新規性ではない。古いP33/P38を今回の直接の対照にしない。',
            refs=(('校正と失敗記録', 'docs/P39_findings.md'),))
    add('新規性の現在地：今回整えたのは、比較の土台',
        '<table><thead><tr><th>候補・部品</th><th>現在の判断</th></tr></thead><tbody>'
        '<tr><td>一律の履歴省略</td><td>過去の比較で総tokenが増え、採用を見送った。</td></tr>'
        '<tr><td>必要項目のキャッシュ</td><td>実際の利用確認で再利用０。拡大を見送った。</td></tr>'
        '<tr><td>残予算の通知</td><td>Budget Tracker等と重なる既存の対照方式。</td></tr>'
        '<tr><td>独自方式と性能維持</td><td>現在の証拠だけでは確立していない。</td></tr></tbody></table>',
        notes='新しい名前を付けて貢献にしない。部品が動くこと、少数課題で差が出ること、既存方式を超える貢献は分ける。',
        refs=(('主張の現在地', 'docs/contribution_status_20261022.md'), ('原典との照合', 'docs/budget_control_overlap_20261022.md')))
    add('次に必要なこと：通常の対処を超える改善を絞る',
        '<div class="two"><div class="col"><h3>研究として確かめる</h3><p class="body">どの取得・反復が増えているか。<br>予算通知と停止規則の効果を分ける。<br>残る失敗に必要な制御を絞る。</p></div>'
        '<div class="col"><h3>レターへ向けた現状</h3><p class="body">10月31日の投稿が目標。<br>中心となる独自の主張が不足。<br>４課題の結果を一般化しない。</p></div></div>',
        '目標は変わらない：必要な仕事を完了し、不要な取得・共有・実行を減らす。',
        notes='確認用課題は方式と主比較を固定するまで開かない。結果に合わせて予算を増やし続けたり、成功例だけを残したりしない。あらましへ未確認の改善率を書かない。',
        refs=(('今の状態', 'docs/current_status.md'), ('進行中の記録', 'docs/task_board.md')))
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>'); continue
        refs = ' / '.join(f'<a href="{LINK + path}">{html.escape(label)}</a>' for label, path in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">実行予算と費用 / {i - 1:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}' +
            (f'<div class="takeaway">{slide["take"]}</div>' if slide['take'] else '') +
            f'<div class="footer"><span class="sources">{refs}</span><span>{i}/{len(slides)}</span></div>'
            f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>AIハーネスの性能と総費用</title><style>' + STYLE + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': len(slides), 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'source_sha256': {p: sha(root / p) for p in paths}, 'builder_sha256': sha(Path(__file__)),
                'all_planned_cells_included': True, 'terminated_batch': terminated, 'complete_four_task_comparison': not terminated, 'visual_reviewed': False}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def export(output):
    with tempfile.TemporaryDirectory(prefix='p40-report-') as profile:
        base = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--headless=new',
                '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
                '--disable-extensions', '--user-data-dir=' + profile, '--virtual-time-budget=4000',
                '--run-all-compositor-stages-before-draw']
        uri = (output / 'index.html').resolve().as_uri()
        result = subprocess.run(base + ['--dump-dom', uri], capture_output=True, text=True, timeout=60)
        if result.returncode: raise RuntimeError('layout measurement failed')
        match = re.search(r'<script id="layout-checks" type="application/json">(.*?)</script>', result.stdout, re.S)
        if not match: raise ValueError('layout measurement is missing')
        layout = json.loads(html.unescape(match.group(1)))
        (output / 'layout_checks.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
        if layout['errors']: raise ValueError(layout['errors'])
        result = subprocess.run(base + ['--no-pdf-header-footer', '--print-to-pdf=' + str((output / (STEM + '.pdf')).resolve()), uri],
                                capture_output=True, text=True, timeout=60)
        if result.returncode: raise RuntimeError('PDF export failed')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--repo-root', type=Path, default=ROOT)
    p.add_argument('--output', type=Path, default=ROOT / 'materials/20261022_p40'); p.add_argument('--pdf', action='store_true')
    p.add_argument('--terminated', action='store_true', help='Present the explicit termination audit, including missing cells')
    a = p.parse_args(); print(json.dumps(build(a.repo_root, a.output, a.terminated)))
    if a.pdf: export(a.output)

"""Evidence-linked P45 slides and figures; include every planned condition."""
import argparse
import csv
import datetime as dt
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from documentation_comparison import ARMS
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_documentation_cost_20261022'
TASKS = ('写真整理', '電気代の分担請求', '返金', '曲情報の書出')
LABELS = ('全表示', '仕様返却の選択表示')
COLORS = ('#798c9c', '#177b79')
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def outcome(row):
    if row['record_status'] == 'not_run_after_stop': return '未実行'
    if row['record_status'] != 'evaluated': return '未評価'
    return '成功' if row['success'] else '未達'


def token_label(row):
    if row['record_status'] == 'not_run_after_stop': return '—'
    return f'{row["known_total_tokens"]:,}' + (' ＋不明' if row['unknown_usage_calls'] else '')


def figures(output, report, preflight):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})
    folder = output / 'figures'; folder.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.7), layout='constrained', facecolor='#f6f4ed')
    for ax in axes:
        ax.set_facecolor('#f6f4ed'); ax.invert_yaxis(); ax.set_yticks(range(4), TASKS)
        ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    for arm_index, arm in enumerate(ARMS):
        offset = -.18 if arm_index == 0 else .18
        positions = [i + offset for i in range(4)]
        initial = [r['conditions'][arm]['input_tokens'] for r in preflight['rows']]
        axes[0].barh(positions, initial, height=.32, color=COLORS[arm_index], label=LABELS[arm_index])
        for position, value in zip(positions, initial):
            axes[0].text(value + 120, position, f'{value:,}', va='center', fontsize=8)
        cells = [r for r in report['rows'] if r['arm'] == arm]
        for position, row in zip(positions, cells, strict=True):
            value = row['known_total_tokens']
            if row['record_status'] != 'not_run_after_stop':
                axes[1].barh(position, value, height=.32, color=COLORS[arm_index],
                             hatch='///' if row['unknown_usage_calls'] else None)
            label = outcome(row) + (' / ' + token_label(row).replace(' ＋不明', '+?') if value else '')
            axes[1].text(value + 1200, position, label, va='center', fontsize=8)
    axes[0].set_title('生成前の固定入力（通知込み）', loc='left', pad=14)
    axes[1].set_title('継続の全入力＋出力と最終評価', loc='left', pad=14)
    axes[0].set_xlim(0, 20000); axes[1].set_xlim(0, max(140000, max(r['known_total_tokens'] for r in report['rows']) * 1.35))
    axes[0].set_xlabel('token / 初回入力'); axes[1].set_xlabel('token / 継続全体（不明分は別記）')
    for ax in axes:
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value / 1000:g}k'))
    axes[0].legend(loc='lower left', bbox_to_anchor=(-.05, 1.12), ncol=2, frameon=False, fontsize=10)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(folder / ('initial_and_continuation.' + ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)
    with (folder / 'all_conditions.csv').open('w') as stream:
        writer = csv.writer(stream)
        keys = ('run_id', 'task_id', 'arm', 'record_status', 'success', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests')
        writer.writerow(keys)
        for row in report['rows']: writer.writerow([row[k] for k in keys])


def build(root, output):
    paths = ('reports/P45_comparison.json', 'reports/P45_prefix_checks.json',
             'reports/P45_activation_v01.json', 'reports/P44_documentation_origin.json',
             'reports/P45_program_diagnostics.json')
    report, preflight, activation, prior, diagnostic = [read(root / path) for path in paths]
    if (not report['all_planned_cells_accounted'] or report['audit_errors'] or len(report['rows']) != 8
            or report['batch_status'] not in ('complete', 'stopped')
            or report['source_sha256']['preflight'] != sha(root / paths[1])
            or report['source_sha256']['activation'] != sha(root / paths[2])
            or activation['preflight_sha256'] != sha(root / paths[1])
            or diagnostic['source_sha256']['comparison'] != sha(root / paths[0])
            or not diagnostic['all_planned_cells_accounted']):
        raise ValueError('closed and audited eight-condition evidence required')
    output.mkdir(parents=True, exist_ok=True); figures(output, report, preflight)
    slides = []
    def add(title, body='', take='', notes='', refs=(), cover=False):
        slides.append(dict(title=title, body=body, take=take, notes=notes, refs=list(refs), cover=cover))
    add('AIハーネスの仕様表示と<br>仕事を終えるまでの費用', cover=True)
    add('目的：最終品質を保ちながら、不要な処理を減らす',
        '<p class="lead">入力を短くするだけでは、仕事全体が安くなるとは限らない。</p>'
        '<div class="two"><div class="col"><h3>これまで</h3><p class="body">一律の出力省略では<br>初回入力は短くても総tokenが増加。<br>省略した情報の扱いを見直した。</p></div>'
        '<div class="col"><h3>今回</h3><p class="body">作業データと見出しを残し、<br>照合できたAPI仕様返却だけを省略。<br>最終結果と全継続費用を比較する。</p></div></div>',
        '通常の選択的省略を評価する対照実験。独自方式の成立は主張しない。',
        notes='P44は初回入力の８計数のみで品質評価はしていない。P45はその不足を同じ４既知課題で確認する。P33の過去の値を今回の直接対照には使わない。',
        refs=(('研究目的', 'docs/research_objective_20261022.md'), ('P44結果', 'docs/P44_findings.md')))
    add('条件：同じ途中状態から、全４課題を各１回ずつ',
        '<table><thead><tr><th>比較する差</th><th>両条件で共通のもの</th></tr></thead><tbody>'
        '<tr><td>全表示</td><td rowspan="2">４既知課題・８応答後の環境とPython状態<br>残予算通知・残量に応じた出力枠<br>初回cacheなしを実測照合、以後は再利用可</td></tr>'
        '<tr><td>仕様返却の選択表示</td></tr>'
        '<tr><td>保持する情報</td><td>操作・作業データ・見出し・最新出力・原文への参照</td></tr>'
        '<tr><td>各条件の上限</td><td>16生成／120,000 token／480秒／元課題のAPI枠</td></tr></tbody></table>',
        '未知使用量・復元不一致・実行や評価の故障で停止。置換試行や上限延長をしない。',
        notes='表示構築、通知、計数、道具と生成は継続費用へ含む。復元は別集計。４課題すべてを残し、順序を交互に固定。保留12シナリオは未閲覧。',
        refs=(('生成前の固定計画', 'docs/experiments/P45_documentation_comparison.md'), ('固定記録', paths[2])))
    add('初回入力と、終了までの費用を分けて読む',
        '<div class="diagram"><img src="figures/initial_and_continuation.svg" style="width:100%;height:350px" alt="全４課題の固定初回入力と全継続token"></div>'
        '<p class="small">k＝1,000 token。左右の横軸の範囲は異なる。右側は失敗を含む全継続費用。不明分は別記。</p>',
        notes='左は生成前の全８入力計数。実通知にはその時点の残時間が入り、実入力は各回再計数。右は実測値と最終評価。早期の失敗や未実行の少費用を成功の効率としない。',
        refs=(('全８入力の計数', paths[1]), ('全予定条件の監査', paths[0])))
    table = '<table class="compact"><thead><tr><th>課題</th><th>条件</th><th>最終</th><th>継続token</th><th>AI</th><th>API</th></tr></thead><tbody>'
    for number, task in enumerate(TASKS):
        for arm_index, arm in enumerate(ARMS):
            row = report['rows'][number * 2 + arm_index]
            if row['arm'] != arm: raise ValueError('report condition order differs')
            table += (f'<tr><td>{task}</td><td>{LABELS[arm_index]}</td><td>{outcome(row)}</td>'
                      f'<td>{token_label(row)}</td><td>{row["model_calls"]}</td><td>{row["api_requests"]}</td></tr>')
    table += '</tbody></table>'
    counts = report['record_status_counts']
    add('全予定条件を残し、未評価と未実行も示す', table,
        f'評価済 {counts.get("evaluated", 0)}/8、実行済み未評価 {counts.get("attempted_unevaluated", 0)}、未実行 {counts.get("not_run_after_stop", 0)}。',
        notes='APIは継続の実要求数。復元と前半は次頁で分離。公式評価の成功と、モデルの完了宣言を区別する。未知使用量は０に換算しない。',
        refs=(('全件の結果と採否', 'docs/P45_findings.md'), ('監査済み集計', paths[0])))
    cost = '<table class="compact"><thead><tr><th>費用・観測</th><th>全表示</th><th>選択表示</th></tr></thead><tbody>'
    metrics = (('継続の既知token', 'known_total_tokens', 'int'), ('使用量不明の呼出し', 'unknown_usage_calls', 'int'),
               ('継続の経過秒', 'continuation_wall_seconds', 'float'), ('表示構築の秒', 'display_construction_seconds', 'float'),
               ('入力計数の秒', 'input_count_seconds', 'float'), ('原文再読／参照選択', None, 'refs'),
               ('復元API／復元秒', None, 'setup'))
    for label, key, kind in metrics:
        values = []
        for arm in ARMS:
            total = report['totals'][arm]
            if kind == 'refs': value = f'{total["archive_read_calls"]} / {total["selected_prior_receipts"]}'
            elif kind == 'setup': value = f'{total["setup_api_requests"]} / {total["setup_wall_seconds"]:.2f}'
            elif kind == 'float': value = f'{total[key]:.3f}'
            else: value = f'{total[key]:,}'
            values.append(value)
        cost += f'<tr><td>{label}</td><td>{values[0]}</td><td>{values[1]}</td></tr>'
    missing_timings = sum(r.get('input_counts_without_timing', 0) for r in diagnostic['rows'])
    cost += '</tbody></table><p class="small">表示構築と計数は継続秒の内数。計数秒は既知分の和、時間不明'+str(missing_timings)+'件。未完遂バッチの合計を優劣の比較に使わない。</p>'
    add('制御や復元の費用も記録する', cost,
        notes='論理tokenにはキャッシュされた入力も含む。実再処理・再利用、通知文字数、出力枠の縮小回数と全実行時間は集計JSONへ記録した。文字数をtoken節約量へ換算しない。',
        refs=(('通知・出力枠・終端の全件照合', paths[0]),))
    task_cost = '<table><thead><tr><th>費用の区間</th><th>全表示</th><th>選択表示</th></tr></thead><tbody>'
    for label, key in (('共通前半（各条件に１回加算）', 'prefix_cost'),
                       ('今回の継続', 'continuation_cost'), ('前半＋継続の論理的な全仕事', 'logical_task_cost')):
        values = []
        for arm in ARMS:
            value = diagnostic['totals'][arm][key]
            values.append(f'{value["known_total_tokens"]:,}' + (f' ＋不明{value["unknown_usage_calls"]}回' if value['unknown_usage_calls'] else ''))
        task_cost += f'<tr><td>{label}</td><td>{values[0]}</td><td>{values[1]}</td></tr>'
    task_cost += '</tbody></table><p class="body">元の前半を各条件へ１回ずつ加える。<br>新しい全体実行を行った値ではない。<br>実験用の復元とモデルロードは別の実測費用として残す。</p>'
    add('局所比較を、仕事全体の費用と混同しない', task_cost,
        '途中状態からの比較では、共通前半・復元・継続を分けて示す。',
        notes='両条件を実行できた場合は同じ共通前半を加えるため絶対差は不変だが、削減率の分母は異なる。未実行の論理的な仕事費用は推計せず、実行済み条件の既知分だけを集計する。',
        refs=(('全件診断と共通前半の計数', paths[4]), ('費用の定義', 'docs/research_objective_20261022.md')))
    if not report['all_eight_complete_with_known_usage']:
        decision = '比較は未完遂で採用条件に届かない。'
        if any(p['success_lost'] is True for p in report['paired_results']):
            decision += '評価済みの対に成功喪失もあり、この形の省略を採用しない。'
        next_step = '既公開の仕様と送信前の拒否を照合し、<br>修復に必要な再取得・AI呼出しを絞る。'
    elif report['development_gate_met']:
        decision = 'この既知４課題では開発基準を通過。一般的な品質維持は未証明。'
        next_step = '既知課題への適合と近接方式の重複を点検し、<br>次の比較を結果を見る前に設計する。'
    else:
        decision = '事前の開発基準を満たさず、この形の選択表示を採用しない。'
        next_step = '成功課題の喪失と全費用を根拠に、<br>次に解く必要のある原因を絞る。'
    add('判断と、まだ主張できないこと',
        '<div class="two"><div class="col"><h3>今回の判断</h3><p class="body">'+decision+'</p><p class="small">基準：全８件・既知使用量・監査合格、<br>成功課題の喪失０、継続総token減少。</p></div>'
        '<div class="col"><h3>次に進める作業</h3><p class="body">'+next_step+'</p><p class="small">４既知課題・１seed。<br>多担当の通信費や再編効果は未測定。<br>新規性と投稿の中心的主張は未確立。</p></div></div>',
        '失敗や欠測を残し、入力の短さを最終品質・総費用へ置き換えない。',
        notes='この資料はP45の全予定条件を対象とする。通常の選択省略と残予算制御を独自方式とはしない。評価群の要求文を見て方式を調整することはしていない。',
        refs=(('固定した採否', 'docs/experiments/P45_documentation_comparison.md'), ('結果と判断', 'docs/P45_findings.md')))
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
            continue
        refs = ' / '.join(f'<a href="{LINK + path}">{html.escape(label)}</a>' for label, path in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">仕様表示と継続費用 / {number - 1:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}'
            + (f'<div class="takeaway">{slide["take"]}</div>' if slide['take'] else '')
            + f'<div class="footer"><span class="sources">{refs}</span><span>{number}/{len(slides)}</span></div>'
            + f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    extra = '.compact{font-size:19px}.compact td,.compact th{padding:6px 12px;font-size:18px}.small{font-size:17px;line-height:1.45}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>AIハーネスの仕様表示と継続費用</title><style>' + STYLE + extra + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': len(slides), 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'source_sha256': {p: sha(root / p) for p in paths}, 'builder_sha256': sha(Path(__file__)),
                'visual_reviewed': False, 'all_planned_conditions_included': True,
                'complete_four_task_comparison': report['all_eight_complete_with_known_usage']}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261022_p45')
    parser.add_argument('--pdf', action='store_true'); args = parser.parse_args()
    print(json.dumps(build(args.repo_root, args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)

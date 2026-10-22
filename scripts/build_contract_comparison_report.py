"""Render closed P47 evidence; all twelve conditions and unknown usage remain."""
import argparse
import csv
import datetime as dt
import html
import json
from pathlib import Path

import build_budget_report
from build_documentation_comparison_report import outcome, token_label
from build_morning_report import STYLE, SCRIPT
from contract_comparison import ARMS
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_contract_feedback_20261022'
TASKS = ('写真整理', '電気代の分担請求', '返金', '曲情報の書出')
LABELS = ('全表示＋契約', '選択＋引数名', '選択＋契約')
COLORS = ('#798c9c', '#b18a35', '#177b79')
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def figures(output, report, preflight):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})
    folder = output / 'figures'; folder.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.8), layout='constrained', facecolor='#f6f4ed')
    for ax in axes:
        ax.set_facecolor('#f6f4ed'); ax.invert_yaxis(); ax.set_yticks(range(4), TASKS)
        ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    for index, arm in enumerate(ARMS):
        positions = [n + (index - 1) * .25 for n in range(4)]
        initial = [r['conditions'][arm]['input_tokens'] for r in preflight['rows']]
        axes[0].barh(positions, initial, height=.21, color=COLORS[index], label=LABELS[index])
        for position, value in zip(positions, initial):
            axes[0].text(value + 120, position, f'{value:,}', va='center', fontsize=7)
        for position, row in zip(positions, [r for r in report['rows'] if r['arm'] == arm], strict=True):
            value = row['known_total_tokens']
            if row['record_status'] != 'not_run_after_stop':
                axes[1].barh(position, value, height=.21, color=COLORS[index],
                             hatch='///' if row['unknown_usage_calls'] else None)
            text = outcome(row) + (' / ' + token_label(row).replace(' ＋不明', '+?') if value else '')
            axes[1].text(value + 1000, position, text, va='center', fontsize=7)
    axes[0].set_title('通知付きの固定初回入力', loc='left', pad=12)
    axes[1].set_title('継続の全入力＋出力と最終評価', loc='left', pad=12)
    axes[0].set_xlim(0, 20500)
    axes[1].set_xlim(0, max(145000, max(r['known_total_tokens'] for r in report['rows']) * 1.35))
    for ax in axes:
        ax.set_xlabel('token（k＝1,000）')
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value / 1000:g}k'))
    axes[0].legend(loc='lower left', bbox_to_anchor=(-.12, 1.10), ncol=3, frameon=False, fontsize=8)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(folder / ('initial_and_continuation.' + ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)
    with (folder / 'all_conditions.csv').open('w') as stream:
        writer = csv.writer(stream)
        keys = ('run_id', 'task_id', 'arm', 'record_status', 'success', 'model_calls', 'known_total_tokens',
                'unknown_usage_calls', 'api_requests', 'feedback_count', 'logical_task_known_total_tokens',
                'logical_task_unknown_usage_calls')
        writer.writerow(keys)
        for row in report['rows']: writer.writerow([row.get(k) for k in keys])


def table(headers, rows):
    return '<table class="compact"><thead><tr>' + ''.join('<th>' + h + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join('<td>' + str(value) + '</td>' for value in row) + '</tr>' for row in rows) + '</tbody></table>'


def build(root, output):
    paths = ('reports/P47_comparison.json', 'reports/P47_prefix_checks.json', 'reports/P47_activation_v01.json',
             'reports/P47_runtime_checks.json', 'reports/P46_contract_feedback.json')
    report, pre, activation, runtime, probe = [read(root / name) for name in paths]
    if (not report['all_planned_cells_accounted'] or report['audit_errors'] or len(report['rows']) != 12
            or report['batch_status'] not in ('complete', 'stopped')
            or any(report['source_sha256'][key] != sha(root / path) for key, path in
                   (('preflight', paths[1]), ('activation', paths[2]), ('runtime_checks', paths[3])))
            or activation['preflight_sha256'] != sha(root / paths[1]) or not runtime['all_checks_passed']):
        raise ValueError('closed and audited twelve-cell evidence required')
    output.mkdir(parents=True, exist_ok=True); figures(output, report, pre)
    slides = []
    def add(title, body='', take='', notes='', refs=(), cover=False):
        slides.append(dict(title=title, body=body, take=take, notes=notes, refs=list(refs), cover=cover))
    add('仕様の表示を減らした後に<br>API契約を返す効果と費用', cover=True)
    add('目的：必要な処理を残し、仕事全体の費用を減らす',
        '<p class="lead">仕様が手元に残っていても、AIが正しく使えるとは限らない。</p>'
        '<div class="two"><div class="col"><h3>前の比較から</h3><p class="body">P45の選択表示は採用見送り。<br>P46では７拒否中４件・３課題に<br>既公開契約を返せると照合した。</p></div>'
        '<div class="col"><h3>今回の問い</h3><p class="body">同じ詳しい返信があっても<br>表示を減らすことは有効か。<br>引数名だけの返信でも足りるか。</p></div></div>',
        '最終品質と、制御・修復・再取得を含む全費用で判断する。',
        notes='P46は保存記録の実装照合で、節約実績ではない。詳細エラーと省略は通常の方法であり、組合せだけで独自性とはしない。',
        refs=(('最終目標', 'docs/research_objective_20261022.md'), ('P46結果', 'docs/P46_findings.md')))
    add('比較：全表示にも同じ契約返信を与える',
        table(('条件', '境界での表示', '未知引数の拒否時'), [
            (LABELS[0], '全表示', '公開済みの原契約'), (LABELS[1], '由来を照合した仕様部分を省略', '許される引数名'),
            (LABELS[2], '上と同じ省略', '公開済みの原契約')]) +
        '<p class="body">４既知課題・８応答後の同じ環境とPython状態。各１回、計12件。<br>16生成／120,000 token／480秒。元のAPI枠、通知・出力枠も共通。</p>',
        '未送信・既公開の拒否だけが対象。推測修正・自動再送・新しいAPIの公開はしない。',
        notes='seed50から呼出しごとに増加。初回cacheなしを実測、以後再利用可。16,000文字を超える返信は引数名、さらに大きければ元の拒否へ戻す。P45との差を同時対照とはしない。',
        refs=(('生成前の固定条件', 'docs/experiments/P47_contract_comparison.md'), ('activation', paths[2])))
    add('初回入力と、終了までの費用を分ける',
        '<div class="diagram"><img src="figures/initial_and_continuation.svg" style="width:100%;height:355px" alt="全４課題・３条件の入力と継続費用"></div>'
        '<p class="small">左右の横軸の範囲は異なる。右は失敗も含む全継続費用。斜線と＋?は既知分に加わる不明使用量。</p>',
        notes='左は事前計数、右は実測。初回の実通知には経過時間が入るため毎回実入力を再計数。少ない費用で未達になった条件を成功の効率とは数えない。',
        refs=(('全入力事前計数', paths[1]), ('全件監査', paths[0])))
    rows = []
    for number, task in enumerate(TASKS):
        values = [task]
        for index, arm in enumerate(ARMS):
            row = report['rows'][number * 3 + index]
            if row['arm'] != arm: raise ValueError('planned row order differs')
            values.append(f'<b>{outcome(row)}</b><br>{token_label(row)} token<br>AI {row["model_calls"]} / API {row["api_requests"]}')
        rows.append(values)
    counts = report['record_status_counts']
    add('全12条件を残し、成功・未達・欠測を分ける', table(('課題', *LABELS), rows),
        f'評価済 {counts.get("evaluated", 0)}/12、実行済み未評価 {counts.get("attempted_unevaluated", 0)}、未実行 {counts.get("not_run_after_stop", 0)}。',
        notes='AIはモデル呼出し、APIは継続中の実要求。公式評価の成功とAIの完了宣言を区別する。未知tokenを０にしない。全条件CSVをfiguresに保存。',
        refs=(('結果と採否', 'docs/P47_findings.md'), ('全予定条件', paths[0])))
    feedback_rows = []
    for arm, label in zip(ARMS, LABELS):
        cells = [r for r in report['rows'] if r['arm'] == arm]
        events = [e for r in cells for e in r.get('feedback_audit', {}).get('feedback_events', [])]
        visible = sum(e['canonical_feedback_in_immediate_next_input'] is True for e in events)
        following = sum(e['next_call_id'] is not None for e in events)
        characters = sum(e['characters'] for e in events)
        feedback_rows.append((label, len(events), f'{visible} / {following}', characters,
                              f'{report["totals"][arm]["feedback_control_seconds"]:.4f}'))
    add('返信の適用と、実際の入力への対応を照合する',
        table(('条件', '付加件数', '次入力に存在／次生成あり', '付加文字数', '構成秒'), feedback_rows) +
        '<p class="body">全プログラム開始時の公開範囲、RPC要求、返却を再構成。<br>元の契約を変えていないか、送信済み要求へ付加していないかを確認。</p>',
        '付加件数・文字数は節約量ではない。後続の生成・API・品質まで含めて評価する。',
        notes='存在は次入力中の正規化された返信文字列の照合。実送信の判定は凍結コードと保存記録による推定であり、別のネットワーク計測ではない。返信構成秒は継続秒の内数。',
        refs=(('返信監査器', 'scripts/audit_contract_feedback.py'), ('監査済み全結果', paths[0])))
    cost_rows = []
    for label, key, unknown in (
        ('共通前半の既知token', 'prefix_known_total_tokens', 'prefix_unknown_usage_calls'),
        ('継続の既知token', 'known_total_tokens', 'unknown_usage_calls'),
        ('前半＋継続の論理全仕事', 'logical_task_known_total_tokens', 'logical_task_unknown_usage_calls')):
        cost_rows.append((label, *[f'{report["totals"][a][key]:,}' + (f' ＋不明{report["totals"][a][unknown]}' if report['totals'][a][unknown] else '') for a in ARMS]))
    for label, key in (('継続の経過秒', 'continuation_wall_seconds'), ('表示・返信・入力計数の秒', None), ('実験用復元 API／秒', 'setup')):
        vals = []
        for arm in ARMS:
            t = report['totals'][arm]
            vals.append(f'{t["setup_api_requests"]} / {t["setup_wall_seconds"]:.2f}' if key == 'setup' else
                f'{sum(t[k] for k in ("display_construction_seconds", "feedback_control_seconds", "input_count_seconds")):.3f}' if key is None else f'{t[key]:.2f}')
        cost_rows.append((label, *vals))
    add('仕事全体と、実験用の復元を区別する', table(('費用の区間', *LABELS), cost_rows),
        '前半は実行済み条件へ１回ずつ加算。新しい全体実行を測った値ではない。',
        notes='表示・返信・入力計数は継続時間の内数。tokenには再利用された入力も含む。実再処理・再利用、原文再読、ロード・サーバー費用は集計と結果文へ別記。未完遂の合計を方式の優劣に使わない。',
        refs=(('全費用の監査', paths[0]), ('費用の定義', 'docs/research_objective_20261022.md')))
    if report['development_gate_met']:
        decision = '既知４課題の開発基準を通過。<br>一般的な品質維持・独自性は未証明。'
    elif not report['all_twelve_complete_with_known_usage']:
        decision = '全12件の評価と既知使用量がそろわず、<br>事前の採用条件に届かない。'
    else:
        decision = '両対照への品質・総費用の基準を満たさず、<br>この形の処理を主方式へ採用しない。'
    contrast_rows = []
    for arm, label in zip(ARMS[:2], LABELS[:2]):
        c = report['contrasts'][arm]
        contrast_rows.append((label, c['paired_success_losses'] if c['paired_success_losses'] is not None else '未判定',
            f'{c["candidate_minus_control_total_tokens"]:+,}' if c['candidate_minus_control_total_tokens'] is not None else '未判定'))
    add('採否：両対照に追加価値があるか',
        '<p class="lead">'+decision+'</p>'+table(('選択＋契約の比較相手', '成功喪失', '継続token差'), contrast_rows) +
        '<p class="small">４既知課題・１seed。成功件数の一致だけでは通過させない。<br>12保留シナリオは未閲覧。複数担当の通信削減と方式の新規性は未確立。</p>',
        '10月23日の主張・主要結果・あらましへ、実証した範囲だけを反映する。',
        notes='全12件・既知使用量・監査合格に加え、両対照への課題別成功喪失０と総token減が条件。欠測を完了した対で補わない。確認群は具体的な主規則と比較・評価条件を固定するまで使わない。',
        refs=(('固定した採否', 'docs/experiments/P47_contract_comparison.md'), ('金曜までの決定表', 'docs/letter_friday_decisions_20261022.md')))
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>'); continue
        refs = ' / '.join(f'<a href="{LINK + path}">{html.escape(label)}</a>' for label, path in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">仕様表示と契約返信 / {number - 1:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}'
            + (f'<div class="takeaway">{slide["take"]}</div>' if slide['take'] else '')
            + f'<div class="footer"><span class="sources">{refs}</span><span>{number}/{len(slides)}</span></div>'
            + f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    extra = '.compact{font-size:18px}.compact td,.compact th{padding:7px 10px;font-size:17px;line-height:1.5}.small{font-size:17px;line-height:1.45}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>仕様表示と契約返信</title><style>'+STYLE+extra+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2)+'\n')
    manifest = {'pages': len(slides), 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'source_sha256': {p: sha(root / p) for p in paths}, 'builder_sha256': sha(Path(__file__)),
                'visual_reviewed': False, 'all_planned_conditions_included': True,
                'complete_four_task_comparison': report['all_twelve_complete_with_known_usage']}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261022_p47')
    parser.add_argument('--pdf', action='store_true'); args = parser.parse_args()
    print(json.dumps(build(args.repo_root, args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)

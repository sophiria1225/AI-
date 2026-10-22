"""Build an evidence-linked P43 report and standalone scientific figures."""
import argparse
import csv
import datetime as dt
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_input_cost_20261022'
TASKS = ('写真整理', '電気代の分担請求', '返金', '曲情報の書出')
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'
GROUPS = (
    ('指示・課題・枠', ('envelope', 'tools', 'system', 'task'), '#6f8597'),
    ('AIの説明・コード', ('assistant_text', 'assistant_actions'), '#b3c0cc'),
    ('実行記録', ('receipt_metadata',), '#cba67a'),
    ('仕様API群のstdout', ('stdout_documentation_only',), '#177b79'),
    ('他API群のstdout', ('stdout_other',), '#dd946e'),
    ('混合・不確定', ('stdout_mixed', 'stdout_uncertain'), '#ada6b7'),
)


def figures(output, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none'})
    folder = output / 'figures'; folder.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11.2, 4.2), layout='constrained', facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    left = [0] * 4
    for label, keys, color in GROUPS:
        values = [sum(row['ordered_token_increments'][k] for k in keys) for row in report['rows']]
        ax.barh(range(4), values, left=left, height=.55, color=color, label=label)
        left = [a + b for a, b in zip(left, values)]
    for i, total in enumerate(left):
        ax.text(total + 170, i, f'{total:,}', va='center', fontsize=10)
    ax.set_yticks(range(4), TASKS); ax.invert_yaxis(); ax.set_xlim(0, 17500)
    ax.set_xlabel('同じ８応答後の１入力に含まれるtoken（順序付きの差分）')
    ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    ax.legend(loc='lower left', bbox_to_anchor=(-.15, 1.01), ncol=3, frameon=False, fontsize=9)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(folder / ('input_components.' + ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)
    with (folder / 'input_components.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source_run', 'component', 'ordered_token_increment'])
        for row in report['rows']:
            writer.writerows((row['source_run'], key, value) for key, value in row['ordered_token_increments'].items())


def build(root, output):
    paths = ('reports/P43_input_exposure_tokens.json', 'reports/P43_input_exposure_structure.json',
             'reports/P43_input_exposure_integrity.json', 'reports/P42_documentation_exposure.json')
    result, structure, integrity, prior = [read(root / p) for p in paths]
    if (result['status'] != 'complete' or result['input_count_requests'] != 44
            or result['model_generations'] or integrity['errors']
            or [r['source_run'] for r in result['rows']] != [f'P29_{i:02d}_CODE' for i in range(1, 5)]):
        raise ValueError('complete audited four-task evidence required')
    for item in integrity['checked']:
        if item['report_sha256'] != sha(root / f'reports/P43_input_exposure_{item["mode"]}.json'):
            raise ValueError('integrity report is stale')
    output.mkdir(parents=True, exist_ok=True); figures(output, result)
    slides = []
    def add(title, body='', take='', notes='', refs=(), cover=False):
        slides.append(dict(title=title, body=body, take=take, notes=notes, refs=list(refs), cover=cover))
    add('AIハーネスの入力費用と<br>取得情報の扱い', cover=True)
    add('目的：仕事の品質を保ち、不要な処理を減らす',
        '<p class="lead">AIへ渡す情報・取得・実行・検証を、ハーネスで制御する。</p>'
        '<div class="two"><div class="col"><h3>分かっていること</h3><p class="body">P33では一律に出力を省くと、<br>初回入力は短くても総tokenは増えた。</p></div>'
        '<div class="col"><h3>今回確かめること</h3><p class="body">仕様説明と作業データの費用は<br>どこに、どれだけ含まれるか。</p></div></div>',
        '入力が短いことと、必要な仕事を安く完了できることを区別する。',
        notes='研究目的は不要な情報処理・実行の削減と最終品質の維持。P43はその準備となる保存入力の計測で、性能比較ではない。',
        refs=(('研究目的', 'docs/research_objective_20261022.md'), ('P33結果', 'docs/P33_findings.md')))
    add('前提：同じ４課題・８応答後の入力を計数する',
        '<table><thead><tr><th>項目</th><th>固定した内容</th></tr></thead><tbody>'
        '<tr><td>対象</td><td>写真整理／電気代の分担請求／返金／曲情報の書出</td></tr>'
        '<tr><td>状態</td><td>過去のP29から同じ８応答境界。32応答を保持。</td></tr>'
        '<tr><td>測定</td><td>入力の各部分を順に戻し、４課題×11入力を計数。</td></tr>'
        '<tr><td>照合</td><td>最後の全入力がP42の保存入力とtoken数に一致。</td></tr></tbody></table>'
        '<p class="body">追加の生成・API実行・環境再生・最終評価はすべて０。</p>',
        notes='MiniMax M3 IQ4_XSと同じllama.cpp形式。11段階は独立した試行ではなく、記述的な内訳のための入力。保留12シナリオは未閲覧。',
        refs=(('事前計画', 'docs/experiments/P43_input_exposure_accounting.md'), ('全計数', paths[0])))
    add('結果：入力費用の所在は課題ごとに異なる',
        '<div class="diagram"><img src="figures/input_components.svg" style="width:100%;height:325px" alt="４課題の入力token内訳"></div>'
        '<p class="small">仕様API群は「呼んだAPIが仕様APIのみ」の分類。出力全文が仕様だけという意味ではない。<br>差分は復元順序に依存する。図の大きさを、そのまま安全に削除できる量とは解釈しない。</p>',
        notes='全入力合計48485 token。仕様API群のstdoutは9832、他API群は17954。最新応答も含む内訳であり、P42の古い出力に対する省略量とは異なる。',
        refs=(('全４課題の内訳', paths[0]), ('結果と限界', 'docs/P43_findings.md')))
    table = '<table class="compact"><thead><tr><th>課題・出力</th><th>全体の文字数</th><th>仕様返却との一致</th><th>残り</th></tr></thead><tbody>'
    for label, row in zip(TASKS, result['rows']):
        for out in row['outputs']:
            if out['p42_reason'] == 'stdout_not_exact_documentation':
                table += f'<tr><td>{label}・{out["span_id"]}</td><td>{out["stdout_characters"]:,}</td><td>{out["covered_characters"]:,}</td><td>{out["unattributed_characters"]:,}</td></tr>'
    table += '</tbody></table>'
    add('出力全体の不一致を、作業データと決めつけない', table,
        '見出しや区切り文字がある。文字列の一致だけでは、削除の安全性を証明できない。',
        notes='P42で全体一致しなかった７出力を全て表示。合計27343文字のうち27077文字が仕様返却の全文表示と一意に一致し、残り266文字。これは文字数であってtoken数ではない。出力の由来や将来の必要性は別問題。',
        refs=(('P42の見送り', 'docs/P42_findings.md'), ('文字列対応の監査', paths[1])))
    add('現在の判断：効果の主張を増やす段階ではない',
        '<div class="two"><div class="col"><h3>今回確かめたこと</h3><p class="body">費用の内訳と、全体一致規則が<br>扱えなかった出力の対応。</p><p class="small">44計数、保存入力88件の再構成、<br>不一致０。サーバーは計数後に正常停止。</p></div>'
        '<div class="col"><h3>次に確かめること</h3><p class="body">作業情報を落とさず区別できるか。<br>既存の制御との差は何か。<br>最終品質と継続総費用はどう変わるか。</p></div></div>',
        'P42の見送りは維持。新規性・品質を保つ総費用削減は、まだ未確立。',
        notes='部分一致への規則緩和だけで新規性を作ったとはしない。次の制御候補には独立した計画と採否基準が必要。４既知課題の結果を未知課題へ一般化しない。',
        refs=(('研究上の主張', 'docs/contribution_status_20261022.md'), ('全件照合', paths[2])))
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
            continue
        refs = ' / '.join(f'<a href="{LINK + path}">{html.escape(label)}</a>' for label, path in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">入力費用と表示対応 / {number - 1:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}'
                        + (f'<div class="takeaway">{slide["take"]}</div>' if slide['take'] else '')
                        + f'<div class="footer"><span class="sources">{refs}</span><span>{number}/{len(slides)}</span></div>'
                        + f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>AIハーネスの入力費用</title><style>' + STYLE + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': len(slides), 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'source_sha256': {p: sha(root / p) for p in paths}, 'builder_sha256': sha(Path(__file__)),
                'visual_reviewed': False, 'model_generations': 0, 'all_four_tasks_included': True}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261022_p43')
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args(); print(json.dumps(build(args.repo_root, args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM
        build_budget_report.export(args.output)

"""Current goal and submission decisions, kept separate from experiment results."""
import argparse
import datetime as dt
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_goal_and_deadline_20261022'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def build(root, output):
    sources = ('docs/letter_friday_decisions_20261022.md', 'reports/goal_alignment_20261022.json',
               'docs/research_objective_20261022.md', 'docs/experiments/P45_documentation_comparison.md',
               'reports/P44_documentation_origin.json')
    alignment = read(root / sources[1])
    if (not alignment['local_blob_matches_github_main'] or alignment['pages_read'] != list(range(1, 29))
            or alignment['deadlines']['submission'] != '2026-10-31'):
        raise ValueError('goal and deadline source not checked')
    slides = [dict(title='性能維持と総費用削減のための<br>ハーネス制御', cover=True)]
    def add(title, body, takeaway, refs):
        slides.append(dict(title=title, body=body, takeaway=takeaway, refs=refs, cover=False))
    add('最終目標：必要な処理を残して、仕事全体を安くする',
        '<p class="lead">AIオーケストレーションの情報・実行を、ハーネスが制御する。</p>'
        '<div class="flow">'+''.join(f'<div><strong>{a}</strong><br><span>{b}</span></div>' for a,b in
        [('情報取得','検索・API'),('情報共有','履歴・担当間'),('AI呼出し','判断・依頼'),('実行','計算・操作'),('検証・停止','確認・修正')])+'</div>'
        '<div class="two"><div class="col"><h3>守る性能</h3><p class="body">要求を満たす完了率と、<br>最終成果物の正しさ。</p></div>'
        '<div class="col"><h3>測る費用</h3><p class="body">全AI入力＋出力。<br>制御・再取得・失敗も含める。</p></div></div>',
        '担当再編・状態再利用・入力制御を、この目標へ寄与する手段として評価する。',
        [('朝PDF 3・4・10頁', 'materials/20261022_morning/AI_harness_progress_20261022.pdf'), ('研究目的', sources[2])])
    add('今の局所比較を、主張を決める材料へつなげる',
        '<table><thead><tr><th>段階</th><th>確認すること</th><th>現在地</th></tr></thead><tbody>'
        '<tr><td>P43・P44</td><td>入力費用と仕様返却の表示対応</td><td>全入力計数・変更監査を完了</td></tr>'
        '<tr><td>P45</td><td>全表示／選択表示の最終品質と総費用</td><td>４既知課題・８条件を固定実行</td></tr>'
        '<tr><td>投稿の中核</td><td>具体的な不要処理を回避する規則と追加価値</td><td>独自の主張は未確定</td></tr>'
        '<tr><td>確認評価</td><td>未調整課題の品質・費用・適用範囲</td><td>12シナリオの要求文は未閲覧</td></tr></tbody></table>',
        'P45の全件監査と採否から、次に検証する規則・強い対照・反証条件を一つに絞る。',
        [('P44結果', 'docs/P44_findings.md'), ('P45固定計画', sources[3]), ('金曜の決定表', sources[0])])
    add('金曜にそろえるもの：主張・主要結果・あらまし',
        '<table><thead><tr><th>決めること</th><th>成果物</th></tr></thead><tbody>'
        '<tr><td>何を新しく示すか</td><td>具体的な不要処理、発生条件、回避する判断規則</td></tr>'
        '<tr><td>最も近い方式との差</td><td>入力・状態・判断時点・更新・出力・追加費用の比較</td></tr>'
        '<tr><td>何と比べ、何なら見送るか</td><td>強い単純対照、品質と総費用、有害条件、固定した採否</td></tr>'
        '<tr><td>主要結果とあらまし</td><td>全件の実測値・適用範囲を示す図表と新しい要旨</td></tr></tbody></table>',
        '通常方式の校正だけで独自性を確定せず、追加価値を直接検証する比較を優先する。',
        [('判断表と作業順', sources[0]), ('原稿の状態', 'papers/202610_letter/README.md')])
    add('10月31日の投稿へ、判断と原稿を進める',
        '<table><thead><tr><th>期限</th><th>完了させるもの</th></tr></thead><tbody>'
        '<tr><td>10月22日（今日）</td><td>固定比較を閉じ、全件監査と採否を主張の判断へ反映</td></tr>'
        '<tr><td>10月23日（金）</td><td>主張１つ・主要比較の結果・あらまし</td></tr>'
        '<tr><td>10月24〜25日</td><td>不足した対照・反例・未調整課題の確認</td></tr>'
        '<tr><td>10月29〜30日</td><td>２段組４ページの本文・図・引用・公式様式・著者情報</td></tr>'
        '<tr><td>10月31日</td><td>レター投稿完了</td></tr></tbody></table>',
        'Project #70＝主張、#71＝主要比較、#72＝原稿。判断のたびに資料と原稿入口も更新する。',
        [('期限と判断', sources[0]), ('朝PDF 22頁', 'materials/20261022_morning/AI_harness_progress_20261022.pdf')])
    output.mkdir(parents=True, exist_ok=True)
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            refs = ' / '.join(f'<a href="{LINK+p}">{html.escape(label)}</a>' for label,p in slide['refs'])
            sections.append(f'<section class="slide"><div class="eyebrow">研究目標と投稿までの判断 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                f'<div class="footer"><span class="sources">{refs}</span><span>{i}/{len(slides)}</span></div>'
                '<div class="notes">10月22日の意思決定資料。P45の効果を確定する結果資料ではない。研究の最終目標と局所検証を分け、主要結果と新規性の不足を明示する。</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    extra = '.flow{display:flex;gap:12px;margin:24px 0}.flow>div{flex:1;background:#e4eee7;border-top:3px solid #177b79;padding:14px 10px;text-align:center}.flow strong{font-size:21px}.flow span{font-size:16px}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>研究目標と投稿までの判断</title><style>'+STYLE+extra+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2)+'\n')
    manifest = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'pages': len(slides),
        'source_sha256': {p: sha(root/p) for p in sources}, 'builder_sha256': sha(Path(__file__)),
        'purpose': 'Research goal and Friday/month-end decisions; no interim effectiveness claim', 'visual_reviewed': False}
    (output/'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT/'materials/20261022_deadline')
    parser.add_argument('--pdf', action='store_true'); args=parser.parse_args()
    print(json.dumps(build(args.repo_root,args.output)))
    if args.pdf:
        build_budget_report.STEM=STEM; build_budget_report.export(args.output)

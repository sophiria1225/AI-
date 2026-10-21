"""Milestone report for P16's no-go decision and baseline contract correction."""
import argparse
import hashlib
import json
from pathlib import Path

from build_research_presentation import (
    SLIDES, slide, text, node, arrow, card, banner, table, picture, NAVY, TEAL, MUTED,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p16'
STEM = 'AI_harness_P16_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def build(review):
    SLIDES.clear()
    footer = '2026-10-21｜４開発課題・１ seed｜候補の追加価値を確認できず、主提案化を見送る'
    s = slide('RESEARCH CHECKPOINT / P16', '新規性につながるかを検証し、候補を見送った', source=footer)
    text(s, 40, 158, 880, 105, '未実行の要求を、完了した事実として\n記憶してしまう現象を検証した。', 30, NAVY, True)
    text(s, 40, 286, 880, 125, '24生成、形式適合17出力・160項目を照合。\n今回の元入力では、未支持の操作完了を確認できなかった。\n要求を隠す方式の優位性は、示せなかった。', 21)
    banner(s, '新規性はまだ未確定。採否基準に従い、この案を今月のレターの主提案にはしない。', size=15)

    s = slide('01 / 目的と狙った差', 'ハーネスが、記録の意味と使い道を制御する',
              'モデルの重みを変えず、記憶更新・修復へ渡す情報を操作する候補だった。', footer)
    card(s, 40, 175, 420, 255, '研究全体で目指すこと',
         '後の担当が必要な状態を受け取り、\n仕事全体を正しく完了できること。\n生成・検証・再取得を含む総費用も\n減らせる構成原理を明らかにする。', body_size=18)
    card(s, 500, 175, 420, 255, '今回、必要だった追加価値',
         '状態付き記憶や用途別可視性は既出。\n元入力や状態明記より誤完了が減り、\n修復に必要な情報は失わないという\n追加価値を測る必要があった。', body_size=18)
    banner(s, '機能を接続したことではなく、単純対照を超える効果と成立条件が必要。', size=17)

    s = slide('02 / 実験の構成', '同じ操作直前までの情報から、表示だけを比較',
              '正常な返却を残す対照と、通常の引数検査で送信前に拒否する条件を用意。', footer)
    picture(s, 'event_view_architecture', x=40, y=155, w=880, h=333)

    s = slide('03 / 人工拒否の全結果', '元入力でも、対象の誤完了は確認できなかった',
              '不適合出力を意味的な成功に数えない。４課題から低い発生率や同等性も保証しない。', footer)
    groups = [g for g in review['groups'] if g['condition'] == 'rejected_before_dispatch']
    names = {'raw': '元入力', 'execution_tag': '未送信の明記', 'quarantine': '要求の退避'}
    table(s, ['表示', '形式適合', '未支持操作完了', '曖昧なdone', '全生成トークン'],
          [[names[g['variant']], f"{g['schema_valid']}/4",
            f"{g['outputs_with_unsupported_done_action']}/{g['schema_valid']}",
            f"{g['outputs_with_unsupported_or_ambiguous_done']}/{g['schema_valid']}",
            f"{g['known_tokens']:,}"] for g in groups], [190, 120, 185, 170, 215],
          y=180, row_h=60, size=16)
    text(s, 45, 435, 870, 44, '曖昧な２項目は、同じ課題の列挙完了の推論。\n操作を実施したという捏造とは区別し、別集計に残した。', 16, MUTED)

    s = slide('04 / 正常対照と全費用', '全24出力を残す。正常対照は入力が同一',
              'ラベル固定後に方式名を開いて集計。助手１名の探索的判定、完全な盲検ではない。', footer)
    picture(s, 'event_view_probe', x=30, y=160, w=900, h=324)
    text(s, 45, 491, 870, 20, f"総費用 {review['known_total_tokens']:,} トークン／不明０／72.93分。修復・最終タスク成功は未測定。", 13, MUTED)

    s = slide('05 / 追加監査で見つかった不備', '台帳の宣言と受取側が一致していなかった',
              'こちらの基準実装の不備。モデルの新しい失敗機構や提案技術とは呼ばない。', footer)
    node(s, 40, 183, 260, 95, 'モデルへ渡す定義', '出典一覧は空でも適合')
    node(s, 350, 183, 260, 95, '生成された提出', '未完了作業に空の出典')
    node(s, 660, 183, 260, 95, '受取側の検査', '出典１件以上 → 全体を拒否')
    arrow(s, 300, 230, 348, 230); arrow(s, 610, 230, 658, 230)
    text(s, 45, 318, 870, 128, 'P14の３出力、P16の６出力に空出典の拒否が関係。\n入力の要求文を参照するIDも未登録だった。\n宣言と受取制約をそろえ、要求文の参照を定義する。\n旧結果を保存し、新しい版・seedで比較基準を校正する。', 20)
    banner(s, 'この修正だけを新規性にしない。旧結果から台帳一般の弱さを結論づけない。', size=16)

    s = slide('06 / 次の判断と根拠', '実際の失敗から、追加技術が必要な箇所を絞る',
              '10/23に主要結果とあらまし、10/31に投稿完了を目指す。成果の成立はまだ未確定。', footer)
    text(s, 45, 171, 870, 108, '１．不整合を除いた基準と強い単純対照を動かす。\n２．なお残る失敗の条件と原因を切り分ける。\n３．近接研究との差がある場合だけ、新しい機構を比較する。', 20)
    links = [('P16の全結果・採否理由', 'docs/P16_findings.md'),
             ('基準実装の不備・修正理由', 'docs/memory_contract_correction_20261021.md'),
             ('近接研究・読んだ範囲と限界', 'docs/letter_related_work_addendum_20261021.md'),
             ('判定ラベル・全費用の公開集計', 'reports/P16_semantic_review.json')]
    for i, (label, path) in enumerate(links):
        text(s, 48, 318 + 40 * i, 860, 29, label, 18, TEAL, True, url=REPO + path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args = p.parse_args()
    sources = ['reports/P16_semantic_review.json', 'reports/P16_structural_audit.json',
               'reports/P16_input_projection_check.json', 'reports/memory_contract_audit_20261021.json',
               'docs/P16_findings.md', 'docs/memory_contract_correction_20261021.md']
    review = json.loads((ROOT / sources[0]).read_text())
    if not review['review_complete']:
        raise ValueError('sealed semantic review required')
    build(review)
    render(SLIDES, OUTPUT, args.font, stem=STEM, title='P16の結果と基準実装の修正')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {'pages': len(SLIDES), 'scope': 'Feasibility no-go, not a new-method evaluation.',
                'source_sha256': {p: sha(ROOT / p) for p in sources},
                'builder_source_sha256': {p: sha(ROOT / p) for p in (
                    'scripts/build_p16_presentation.py', 'scripts/build_research_presentation.py',
                    'scripts/presentation_renderer.py', 'scripts/plot_event_view_probe.py')},
                'figures_sha256': {p.stem: sha(p) for p in (OUTPUT / 'figures').glob('*.png')},
                'font': str(args.font), 'font_file_redistributed': False}
    (OUTPUT / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    transcript = ['# P16の区切り：結果、見送り、比較基準の修正', '', manifest['scope'], '']
    for i, spec in enumerate(SLIDES, 1):
        transcript += [f"## {i}. {spec['title']}", '']
        transcript += [e['text'] + '\n' for e in spec['elements'] if e['kind'] == 'text']
    (OUTPUT / 'transcript.md').write_text('\n'.join(transcript) + '\n')
    print(json.dumps({'pages': len(SLIDES), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()

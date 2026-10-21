"""P17 calibration milestone; no claim of a novel method or task improvement."""
import argparse
import hashlib
import json
from pathlib import Path

from build_research_presentation import (
    SLIDES, slide, text, node, arrow, card, banner, table, picture, NAVY, TEAL, MUTED,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p17'
STEM = 'AI_harness_P17_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def build(review):
    SLIDES.clear()
    footer = '2026-10-21｜４開発入力 × ２定義 × ２seed｜台帳の校正。新規性・最終性能は未確定'
    s = slide('RESEARCH CHECKPOINT / P17', '比較基準を直し、形式と意味の限界を分けた', source=footer)
    text(s, 40, 167, 880, 100, '整合版は８／８出力が形式適合。\nただし、内容の正しさを保証する結果ではない。', 28, NAVY, True)
    text(s, 40, 296, 880, 115,
         f"全16生成、{review['known_total_tokens']:,}トークン、不明０。\n"
         '適合15出力の全140項目を、元の記録と照合した。\n曖昧な全体完了と、不十分な引用が残った。', 21)
    banner(s, 'この修正は自作基準の不備への対応。独自方式の発見や性能改善とは区別する。', size=16)

    s = slide('01 / 目的と実験アーキテクチャ', '情報・予算をそろえ、台帳の契約だけを校正',
              'モデルに許す形式と、実行器が受け取る形式を一致させる。', footer)
    node(s, 40, 175, 250, 100, '同じ４入力', '要求・操作結果・API仕様')
    node(s, 340, 165, 250, 80, '旧版', '空出典を宣言側で許可')
    node(s, 340, 275, 250, 80, '整合版', '出典登録・受取制約と一致')
    node(s, 645, 205, 275, 100, '同じM3モデル・２seed', '全16出力を保存')
    arrow(s, 290, 210, 338, 200); arrow(s, 290, 250, 338, 310)
    arrow(s, 590, 200, 643, 235); arrow(s, 590, 310, 643, 275)
    text(s, 45, 387, 870, 80,
         '終了後：原入力・費用の監査 → 方式名を伏せて全項目を照合\n'
         '→ ラベル固定 → 方式とseedを開いて集計。追加の環境操作は０。', 19)
    banner(s, '要求文は「何を頼まれたか」の根拠であり、「実行したか」の証拠にはならない。', size=16)

    s = slide('02 / 全結果', '形式不適合は減ったが、意味の優位性は示せない',
              '反復・台帳項目を独立した課題数に数えない。助手１名の探索的照合。', footer)
    groups = {g['variant']: g for g in review['groups']}
    a, b = groups['legacy'], groups['aligned']
    table(s, ['指標', '旧版', '整合版'], [
        ['形式適合', f"{a['schema_valid']} / 8", f"{b['schema_valid']} / 8"],
        ['未支持操作完了を検出した適合出力', '0 / 7', '0 / 8'],
        ['曖昧な完了を含む適合出力', '1 / 7', '2 / 8'],
        ['曖昧な完了項目', '1', '3'],
        ['不適合も含む全生成トークン', f"{a['known_tokens']:,}", f"{b['known_tokens']:,}"],
    ], [530, 175, 175], y=173, row_h=45, size=17)
    text(s, 45, 457, 870, 43, '旧版の１不適合は空出典。未支持０件は一般的な安全性の証明ではない。\n曖昧な項目を未支持側へ含めても、整合版の意味上の優位は示せない。', 15, MUTED)

    s = slide('03 / 全入力と費用', '16出力の成否・曖昧さ・費用をすべて残す',
              '成功した出力だけで比較しない。最終タスク成功は、この実験では測っていない。', footer)
    picture(s, 'ledger_contract', x=30, y=167, w=900, h=320)

    s = slide('04 / 内容確認と解釈', '個々の操作が成功しても、対象全体の確認は別', source=footer)
    card(s, 40, 167, 420, 250, '曖昧な全体完了：４項目',
         '調べたページは時刻の降順だった。\nしかしAPI説明に全体の順序保証がない。\n個別４件の操作成功は確認できても、\n対象を全て調べたことまでは\n証明したと扱わない。', body_size=17)
    card(s, 500, 167, 420, 250, '要求側だけの引用：３項目',
         'taskのみ２件、要求取得との併用１件。\nうち２件は引用外の同じ前半記録に\n実際の成功返却があった。\n引用不足と、前半全体にも根拠がない\n誤完了は分けて記録する。', body_size=17)
    banner(s, '形式の整合は保持する。意味上も安全な台帳としての採用条件は未達。', size=17)

    s = slide('05 / 何を目指し、次に何をするか', '一つの追加機構を、強い単純対照に対して検証する',
              '２段組４ページ。10/23に主要実験・あらまし、10/31に投稿完了が目標。', footer)
    text(s, 45, 165, 870, 119,
         '研究の目的：仕事の品質を保ちながら、状態共有・再取得を含む総費用を減らす。\n'
         '現在の成果：比較基盤、費用の観測、見送り判断、基準の修正。新規性は未確定。\n'
         '次の実行：P18の別４課題を同じ全履歴基準で実行し、自然な失敗を切り分ける。\n'
         '確認用12シナリオは未閲覧。機構と比較条件を固定するまで保留する。', 17)
    links = [('P17：全結果・採否・限界', 'docs/P17_findings.md'),
             ('P18：４課題の事前仕様', 'docs/experiments/P18_unseen_development.md'),
             ('４ページの原稿構成', 'docs/letter_four_page_update_20261021.md'),
             ('少数評価で主張できる範囲', 'docs/letter_evaluation_scope_20261021.md')]
    for i, (label, path) in enumerate(links):
        text(s, 48, 322 + 39*i, 860, 29, label, 17, TEAL, True, url=REPO+path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args = p.parse_args()
    sources = ['reports/P17_semantic_review.json', 'reports/P17_structural_audit.json',
               'reports/P17_supplementary_contract_diagnosis.json', 'docs/P17_findings.md',
               'docs/letter_four_page_update_20261021.md', 'docs/letter_evaluation_scope_20261021.md']
    review = json.loads((ROOT/sources[0]).read_text())
    audit = json.loads((ROOT/sources[1]).read_text())
    if not review['review_complete'] or audit['audit_errors']:
        raise ValueError('sealed review and passing audit required')
    build(review)
    render(SLIDES, OUTPUT, args.font, stem=STEM, title='P17：台帳の形式と意味を分ける校正')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {'pages': len(SLIDES), 'scope': 'Baseline calibration; no novel-method or task-success claim.',
                'source_sha256': {p: sha(ROOT/p) for p in sources},
                'builder_source_sha256': {p: sha(ROOT/p) for p in (
                    'scripts/build_p17_presentation.py', 'scripts/build_research_presentation.py',
                    'scripts/presentation_renderer.py', 'scripts/plot_ledger_contract_probe.py')},
                'figures_sha256': {p.stem: sha(p) for p in (OUTPUT/'figures').glob('*.png')},
                'font': str(args.font), 'font_file_redistributed': False}
    (OUTPUT/'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    transcript = ['# P17：比較基準の校正と、内容に残る限界', '', manifest['scope'], '']
    for i, spec in enumerate(SLIDES, 1):
        transcript += [f"## {i}. {spec['title']}", '']
        transcript += [e['text']+'\n' for e in spec['elements'] if e['kind']=='text']
    (OUTPUT/'transcript.md').write_text('\n'.join(transcript)+'\n')
    print(json.dumps({'pages': len(SLIDES), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()

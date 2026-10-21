"""P18 milestone: completed baseline, observed omission, and next diagnostic."""
import argparse
import hashlib
import json
from pathlib import Path

from build_research_presentation import (
    SLIDES, slide, text, node, arrow, card, banner, table, picture, NAVY, TEAL, MUTED,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p18'
STEM = 'AI_harness_P18_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def build(summary, diagnosis):
    SLIDES.clear()
    footer = '2026-10-21｜追加４開発課題・全履歴・各１seed｜新方式の効果・一般発生率は未確定'
    s = slide('RESEARCH CHECKPOINT / P18', '取得できても、成果物へ全件を反映できない例', source=footer)
    text(s, 40, 169, 880, 97, '72曲の情報は取得済み。\n書出は71曲で、読み返した後も完了と判断。', 28, NAVY, True)
    text(s, 40, 297, 880, 112,
         '全履歴基準は４課題中２件成功。\n49生成、1,017,215トークン、187 API、使用量不明０。\n別の１失敗はAPI上限で終了し、原因候補を分けた。', 21)
    banner(s, '自然な欠落は観測できた。ただし、新規性や改善効果を示す結果ではない。', size=17)

    s = slide('01 / 目的と実験アーキテクチャ', '固定した基準を、未使用の４開発課題へ適用',
              'P11と同じ条件。モデル・予算・方式を実行中に変更しない。', footer)
    node(s, 40, 180, 250, 100, '課題の事前選定', '要求を読む前にID順で固定')
    node(s, 345, 180, 250, 100, '同じ単一エージェント', '全履歴・64K・公開API')
    node(s, 650, 180, 270, 100, '模擬環境の最終状態', '全件終了後に独立評価')
    arrow(s, 290, 229, 343, 229); arrow(s, 595, 229, 648, 229)
    text(s, 45, 329, 870, 112,
         '各課題：45万トークン・80生成・80 API・30分。\n'
         '操作・観測・予算・成果物を保存し、送信と未送信を区別。\n'
         '終了後に公開観測から分析。隠し正解を次の方式へ渡さない。', 20)
    banner(s, '研究の目的：情報保持と実行の構成が、最終品質と総費用に与える効果を切り分ける。', size=16)

    s = slide('02 / 全４件の結果', '成功例と失敗例、全費用を残す',
              '課題が異なるP11との成功率差を、方式変更の効果とは呼ばない。', footer)
    table(s, ['課題', '結果・終了条件', '総トークン', '送信API'], [
        ['01：写真整理', '失敗・API上限', '294,726', '80'],
        ['02：割り勘の依頼', '成功・完了宣言', '297,442', '23'],
        ['03：誤請求の返金', '成功・完了宣言', '67,858', '8'],
        ['04：曲一覧の書出', '失敗・完了宣言', '357,189', '76'],
        ['合計', '2 / 4 成功', '1,017,215', '187'],
    ], [280, 270, 195, 135], y=173, row_h=45, size=17)
    text(s, 45, 457, 870, 43,
         '原要求・送信・使用量・保存境界の監査不一致０。\n'
         '完了宣言は最終成功ではない。部分合格を成功件数へ加算しない。', 16, MUTED)

    s = slide('03 / 資源使用量', '予算の上限と、実際に使った量を分ける',
              '入力・出力・調整を含む。破線は各課題の上限。', footer)
    picture(s, 'native_budget', x=30, y=167, w=900, h=320)

    s = slide('04 / 観測された失敗と限界', '操作予算の不足と、取得後の欠落は別の問題', source=footer)
    card(s, 40, 167, 420, 250, '01：個別処理の途中で上限',
         '42ファイルを読み、27件の移動を送信。\n'
         '42件の個別読取＋個別移動だけで84 API。\n'
         '今回は80 APIで停止した。\n'
         'ただし、別手順も含めた最小費用を\n'
         '証明したわけではない。', body_size=17)
    card(s, 500, 167, 420, 250, '04：元の情報とCSVを照合',
         '元の和集合は72 ID。必要な情報も72件。\n'
         'CSVは71行で、１件欠落・余分な行０。\n'
         'ファイルの再読後も模擬アカウントを終了。\n'
         '分析者の集合照合であり、自律的な\n'
         '新しい検証器の実績ではない。', body_size=17)
    banner(s, '全履歴でも残る現象。ただし１例から一般発生率や内部の判断原因までは決めない。', size=16)

    s = slide('05 / 次の比較と論文の目標', '通常の計算コードで解消するか、先に測る',
              '投稿原稿は２段組４ページ。10/23主要実験・あらまし、10/31投稿完了が目標。', footer)
    text(s, 45, 166, 870, 120,
         '次の比較：同じ取得済み情報から、直接CSVを書く／計算コードで書く。\n'
         '集合演算・変数・コード実行は既存技術。導入だけを独自性に数えない。\n'
         'その対照でも残る問題があれば、追加機構と検証できる差を定義する。\n'
         '現時点で新方式の新規性・有効性は未確定。確認用12シナリオは未閲覧。', 17)
    links = [('P18：全結果・次の比較・採らない案', 'docs/P18_findings.md'),
             ('公開観測だけによる集合照合', 'reports/P18_public_evidence_diagnosis.json'),
             ('４ページの原稿構成', 'docs/letter_four_page_update_20261021.md'),
             ('既存のコード処理を先に比べる理由', 'docs/P18_interpretation_plan.md')]
    for i, (label, path) in enumerate(links):
        text(s, 48, 322+39*i, 860, 29, label, 17, TEAL, True, url=REPO+path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    a = p.parse_args()
    sources = ['reports/P18_additional_baseline_summary.json', 'reports/P18_budget_diagnostics.json',
               'reports/P18_public_evidence_diagnosis.json', 'docs/P18_findings.md']
    summary, budget, diagnosis = [json.loads((ROOT/p).read_text()) for p in sources[:3]]
    if summary['pending'] or summary['audit_errors']:
        raise ValueError('completed and audited batch required')
    if not summary['plan_sha256'] == budget['plan_sha256'] == diagnosis['plan_sha256']:
        raise ValueError('source plans disagree')
    build(summary, diagnosis)
    render(SLIDES, OUTPUT, a.font, stem=STEM, title='P18：全履歴でも残る取得後の欠落')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {'pages': len(SLIDES), 'scope': 'Development baseline diagnosis; no novel method claim.',
                'source_sha256': {p: sha(ROOT/p) for p in sources},
                'builder_source_sha256': {p: sha(ROOT/p) for p in (
                    'scripts/build_p18_presentation.py', 'scripts/build_research_presentation.py',
                    'scripts/presentation_renderer.py', 'scripts/plot_native_budget.py')},
                'figures_sha256': {p.stem: sha(p) for p in (OUTPUT/'figures').glob('*.png')},
                'font': str(a.font), 'font_file_redistributed': False}
    (OUTPUT/'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    transcript = ['# P18：全履歴でも残る取得後の欠落', '', manifest['scope'], '']
    for i, spec in enumerate(SLIDES, 1):
        transcript += [f"## {i}. {spec['title']}", '']
        transcript += [e['text']+'\n' for e in spec['elements'] if e['kind']=='text']
    (OUTPUT/'transcript.md').write_text('\n'.join(transcript)+'\n')
    print(json.dumps({'pages': len(SLIDES), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()

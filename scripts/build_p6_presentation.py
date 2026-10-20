"""Build a completed-P6 milestone deck from public aggregates only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from build_research_presentation import (
    SLIDES, slide, text, box, arrow, node, card, banner, table, picture,
    NAVY, TEAL, MUTED, AMBER, WHITE, LIGHT, BLUE, WARM,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p6'
STEM = 'AI_harness_P6_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def build(measurements, runtime):
    SLIDES.clear()
    footer = '2026-10-21｜P6導入比較の区切り｜新規性・品質維持は未確定'
    s = slide('RESEARCH CHECKPOINT / P6', '品質を保って総トークンを減らすための検証',
              source=footer)
    text(s, 40, 145, 880, 110, '独自手法を決める前に、\n既存方式で起きた失敗の機構を確かめる。', 31, NAVY, True)
    text(s, 40, 282, 850, 100, '全履歴、先行研究に基づく保持方式、対象台帳を比較。\n完了率だけでなく、実行情報の誤記憶と\n保持判断・入力再処理の費用を分けて調べた。', 22)
    banner(s, '得られたのは失敗条件と次の比較。新しいアルゴリズムはまだ選んでいない。', size=16.5)

    s = slide('01 / 目的と現在の位置', '担当再編を前提にせず、必要な機構を選び直す',
              '目標：同じモデルで必要な品質を満たし、全入力＋出力トークンを減らす。', footer)
    card(s, 40, 174, 280, 250, '出発点', '大規模な仕事を分担し、\n途中で仕事・状態を\n引き継ぐ研究を検討。\n既存方式との重複を確認。', body_size=18)
    card(s, 340, 174, 280, 250, '見直した理由', '開発実験では担当間の\n変更衝突を確認できず、\n再編の固有利益を\n裏づけられなかった。', body_size=18)
    card(s, 640, 174, 280, 250, '現在の検証', '情報をどう保持・更新し、\n行動へ渡すかを比較。\n既存の単純方式で足りる\n可能性も検証する。', body_size=18)
    banner(s, 'モデルの外側にある情報・状態・実行制御が対象。ハーネス研究として継続する。', size=16)

    s = slide('02 / 実装した構成', '記憶の更新と、環境で実際に行った操作を分離する',
              '同じモデル・公開ツール・予算で、作業用の記憶だけを切り替える。', footer)
    node(s, 40, 175, 240, 90, '公開の要求・API文書', '正解・独立評価は渡さない')
    node(s, 340, 175, 280, 90, '作業役のLLM', '調査・判断・API要求')
    node(s, 680, 175, 240, 90, '模擬アプリ環境', '順序付きの実行と観測')
    arrow(s, 280, 220, 338, 220); arrow(s, 620, 220, 678, 220)
    node(s, 340, 325, 280, 100, '作業用の記憶', '全履歴／FOCUS再実装／台帳', fill=WARM, accent=AMBER)
    node(s, 680, 325, 240, 100, '変更しない原記録', '入力・操作・結果・費用')
    node(s, 40, 325, 240, 100, '終了後の独立評価', '最終状態の成否のみ集計')
    arrow(s, 800, 265, 800, 323); arrow(s, 680, 375, 622, 375)
    arrow(s, 480, 325, 480, 267)
    arrow(s, 920, 220, 940, 220, dashed=True, end=False)
    arrow(s, 940, 220, 940, 441, dashed=True, end=False)
    arrow(s, 940, 441, 160, 441, dashed=True, end=False)
    arrow(s, 160, 441, 160, 427, dashed=True)
    banner(s, '記憶の生成文、操作の実行、最終タスク成功は、それぞれ別の記録で確認する。', size=16.5)

    s = slide('03 / 実験条件', '少数の開発課題で、方式を校正する段階',
              'AppWorldの公開train入力から2課題を選択。各方式・各課題1回。', footer)
    table(s, ['条件', '固定した内容'], [
        ['モデル', 'MiniMax M3 IQ4_XS・64K・KV q8_0・同じ推論基盤'],
        ['全履歴', '原記録を全て作業用入力へ。過去の参照も可能'],
        ['FOCUS再実装', '将来計画の参照＋防御的保持。原著者の性能再現ではない'],
        ['対象台帳', '対象・条件・進捗・根拠IDを更新。意味の正しさは未保証'],
        ['共通上限', '80呼び出し・45万トークン・30分・出力4,096／回'],
    ], [170, 710], y=172, row_h=45, size=16)
    banner(s, '全担当・記憶生成・再読込を計上。大規模本実験や一般化の証明とは区別する。', size=16)

    s = slide('04 / 結果', '成功と費用を同時に見る',
              '費用不明の中断呼び出しは0とせず、「＋不明」として残す。', footer)
    labels = {'full': '全履歴', 'focus': 'FOCUS再実装', 'ledger': '対象台帳'}
    task_numbers = {task: index + 1 for index, task in enumerate(dict.fromkeys(
        row['task_id'] for row in measurements['trials']))}
    rows = []
    for row in measurements['trials']:
        unknown = '＋不明' if row['unknown_usage_calls'] else ''
        outcome = '成功' if row['evaluation']['official_success'] else '未達'
        stop = '完了宣言' if row['declared_complete'] else '時間上限'
        rows.append([str(task_numbers[row['task_id']]), labels[row['arm']],
                     str(row['model_calls']), f"{row['known_total_tokens']:,}{unknown}", outcome, stop])
    table(s, ['課題', '方式', '呼出', '既知トークン', '評価', '停止理由'], rows,
          [65, 190, 65, 220, 100, 240], y=168, row_h=38, size=15.5)
    banner(s, '少ないトークンで失敗した結果を「品質を保った削減」とは呼ばない。', y=454, size=17)

    s = slide('05 / 全役割の費用', '記憶を小さくする判断にも計算が必要',
              '記憶生成の費用を除かず、元の実行記録から集計。', footer)
    picture(s, 'p6_all_costs', x=40, y=167, w=880, h=313)

    focus_rows = [row for row in runtime['trials'] if row['arm'] == 'focus']
    removed = sum(bool(cycle.get('selection_removed_spans')) for row in focus_rows
                  for cycle in row['compression_audit'])
    attempts = sum(len(row['compression_audit']) for row in focus_rows)
    s = slide('06 / 解釈を分ける', '失敗したという事実だけでは、原因は決まらない',
              '推論文の自己説明を、そのまま原因の証明に使わない。', footer)
    card(s, 40, 177, 280, 252, '保持判断の負担',
         f'FOCUSの計{attempts}更新試行。\n履歴を除いた記録は{removed}回。\n形式不備・生成上限・費用を\n忘却の効果と混ぜない。', body_size=18)
    card(s, 340, 177, 280, 252, '台帳の誤った完了',
         '課題1では送信されなかった\n不正な操作を根拠に、\n更新をdoneとした。\nIDの存在だけでは不十分。', body_size=18)
    card(s, 640, 177, 280, 252, '比較基盤の負担',
         '課題2の全履歴では\n入力再処理に約20分。\n台帳更新には約18分半。\n同じ時間上限でも\n費用の内訳が異なる。', body_size=18)
    banner(s, 'いずれも少数例の観測。新機構の必要性は、単純な対照を超えるかで判断する。', size=16)

    s = slide('07 / 第2課題の詳細', '情報を捨てる前に、実行基盤の無駄を測る',
              '中央は入力列の一致の測定。変更後の実時間と品質はまだ測っていない。', footer)
    picture(s, 'p6_runtime', x=30, y=177, w=900, h=304)

    s = slide('08 / 次の比較', '異なる原因を、別の実験で切り分ける',
              'P6終了後に順番に実行。以下は計画であり、この資料の結果には含めない。', footer)
    table(s, ['実験', '変えるもの', '測るもの'], [
        ['P7：同じ記憶入力', '原入力／未実行部分の退避／未実行記録', '完了主張と公開の実行証拠'],
        ['P8：強いAPI基準', 'API別スキーマ・複数操作・公開探索', '最終状態・全費用・形式失敗'],
        ['P9：同じ隣接入力', '情報は保持し、入力配置だけ変更', '入力再処理量と実時間'],
    ], [200, 420, 260], y=179, row_h=65, size=16)
    banner(s, 'P7・P9は課題成功を測らない。P8は複数の変更を含み、単一要因の効果ではない。', size=16)

    s = slide('09 / 何を成果にしたいか', '既存方式をつないだだけで終えないための判定',
              '現在の成果と、研究の完成時に必要な成果を分ける。', footer)
    card(s, 40, 180, 420, 250, 'ここまでの成果',
         '再現可能な比較・全費用の記録。\n誤完了の記憶、保持判断の負担、\n入力再処理という原因候補の切り分け。\n選ばなかった案と失敗も公開記録へ。', body_size=18)
    card(s, 500, 180, 420, 250, 'これから必要な成果',
         '強い既存方式でも残る機構上の問題。\nその問題を扱う具体的な更新・制御規則。\n同じ予算で単純な対照を超える効果。\n別課題・別モデルでの成立条件と限界。', body_size=18)
    banner(s, '単純な対策で足りれば独自機構を追加しない。次の結果から研究の中核を絞る。', size=16.5)

    s = slide('10 / 出典と追跡先', '実験条件・結果・理由をGitHubからたどれる',
              'この資料の数値はP6終了時点の集計。完全な実行履歴・認証情報は公開しない。', footer)
    sources = [
        ('P6の条件と再実装の範囲', 'docs/experiments/P6_context_preservation.md'),
        ('全6試行の結果と次の判断', 'docs/P6_findings.md'),
        ('台帳の誤完了と公開操作の再生', 'docs/P6_ledger_diagnosis.md'),
        ('第2課題の費用・入力配置の診断', 'docs/P6_task2_runtime_diagnosis.md'),
        ('独自の技術的中核を選び直した理由', 'docs/technical_core_review_20261021.md'),
    ]
    for index, (label, path) in enumerate(sources):
        text(s, 45, 180 + 55*index, 870, 35, label, 21, TEAL, True, url=REPO + path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path,
                        default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args = parser.parse_args()
    sources = ['reports/P6_final_measurements.json', 'reports/P6_final_runtime_audit.json',
               'reports/P6_task2_cost_diagnosis.json', 'reports/P6_task2_memory_sizes.json']
    measurements = json.loads((ROOT / sources[0]).read_text())
    runtime = json.loads((ROOT / sources[1]).read_text())
    if (measurements['pending'] or len(measurements['trials']) != 6
            or any(row.get('evaluation') is None for row in measurements['trials'])):
        raise ValueError('the milestone deck requires all six completed, evaluated P6 runs')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'figures').mkdir(exist_ok=True)
    figures = {'p6_all_costs': ROOT / 'reports/P6_final_figures/cost_and_progress.png',
               'p6_runtime': ROOT / 'reports/P6_task2_runtime_figures/runtime_diagnosis.png'}
    for name, path in figures.items():
        shutil.copyfile(path, OUTPUT / 'figures' / (name + '.png'))
    build(measurements, runtime)
    render(SLIDES, OUTPUT, args.font, stem=STEM, title='AIハーネス研究 P6結果と次の検証 2026-10-21')
    manifest = {
        'pages': len(SLIDES), 'scope': 'Completed P6 development calibration, not new-method validation. '
                                       'P7/P8/P9 are future plans in this historical checkpoint.',
        'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
        'builder_source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
            'scripts/build_p6_presentation.py', 'scripts/build_research_presentation.py',
            'scripts/presentation_renderer.py')},
        'figures_sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in figures.items()},
        'regenerate': 'reporting-venv/bin/python scripts/build_p6_presentation.py',
        'font': str(args.font), 'font_file_redistributed': False,
    }
    (OUTPUT / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    transcript = ['# P6結果と次の検証（2026年10月21日）', '', manifest['scope'], '']
    for index, spec in enumerate(SLIDES, 1):
        transcript += [f"## {index}. {spec['title']}", '']
        transcript += [item['text'] + '\n' for item in spec['elements'] if item['kind'] == 'text']
    (OUTPUT / 'transcript.md').write_text('\n'.join(transcript) + '\n')
    print(json.dumps({'pages': len(SLIDES), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()

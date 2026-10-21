"""Render the complete P22 cohort and its separately reviewed interpretation."""
import argparse
import hashlib
import json
from pathlib import Path

from build_research_presentation import (
    SLIDES, slide, text, node, arrow, card, banner, table, picture, NAVY, TEAL, MUTED,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p22'
STEM = 'AI_harness_P22_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    paths = ['reports/P22_additional_baseline_summary.json',
             'reports/P22_budget_diagnostics.json', 'reports/P22_interpretation.json',
             'docs/P22_findings.md']
    summary, budget, interpretation = [json.loads((ROOT/p).read_text()) for p in paths[:3]]
    if (summary['pending'] or summary['audit_errors'] or len(summary['trials']) != 6
            or len(budget['trials']) != 6 or not interpretation['all_six_reviewed']):
        raise ValueError('all six completed and reviewed trials required')
    if not summary['plan_sha256'] == budget['plan_sha256'] == interpretation['plan_sha256']:
        raise ValueError('plan hashes differ')
    for name in paths[:2]:
        if interpretation['source_sha256'][name] != sha(ROOT/name):
            raise ValueError('interpretation source changed')
    for outcome, cost in zip(summary['trials'], budget['trials'], strict=True):
        if outcome['evaluation'] is None or any(outcome[k] != cost[k] for k in (
                'run_id', 'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'wall_seconds')):
            raise ValueError('outcome and cost differ')
        for suffix in ('execution_audit', 'boundary_audit'):
            name = f"reports/{outcome['run_id']}_{suffix}.json"
            audit = json.loads((ROOT/name).read_text())
            if any(audit.get(k) for k in ('audit_errors', 'dispatch_audit_errors', 'history_audit_errors')):
                raise ValueError('technical audit discrepancy')
            paths.append(name)
    if len(interpretation['task_labels']) != 6 or len(interpretation['findings']) != 2:
        raise ValueError('six task labels and two reviewed findings required')
    return summary, budget, interpretation, paths


def build(summary, budget, note):
    SLIDES.clear()
    footer = '2026-10-21｜追加６開発課題・各１seed｜探索的観察。新方式・確認実験の結果ではない'
    successes = sum(r['evaluation']['official_success'] for r in summary['trials'])
    apis = sum(r['api_requests'] for r in budget['trials'])
    s = slide('RESEARCH CHECKPOINT / P22', '追加６課題で、次に検証すべき問題を絞る', source=footer)
    text(s, 40, 170, 880, 100, note['headline'], 26, NAVY, True)
    text(s, 45, 294, 870, 98,
         f"全履歴基準：{successes}/6 成功。全６件を評価・監査。\n"
         f"{summary['total_model_calls']}生成、{summary['known_total_tokens']:,}既知トークン、{apis} API。\n"
         f"使用量不明 {summary['unknown_usage_calls']}件。失敗・打切りも費用に含める。", 21)
    banner(s, '到達点は基準の観察。既存対照を超える固有の機構と効果は、別の比較で示す。', size=16)

    s = slide('01 / 目的と研究上の位置', '仕事を正しく終えるための状態・実行制御を研究する', source=footer)
    card(s, 40, 170, 420, 245, '背景と目的',
         '情報が複数の取得・操作へ分散する仕事では、\n'
         '途中の正しさだけで最終完了は決まらない。\n'
         '同じモデル・情報・予算で、\n'
         'ハーネスのどの制御が品質と費用を\n'
         '変えるかを測る。', body_size=17)
    card(s, 500, 170, 420, 245, 'P22で確かめること',
         '強い単純対照でも問題が残るかを調べる前に、\n'
         '別の要求で全履歴基準の実行を観察する。\n'
         '集約・台帳・検査器はまだ追加しない。\n'
         'この６件は方式選定の開発用になり、\n'
         '未調整の確認群として再利用しない。', body_size=17)
    banner(s, '求める成果：具体的な失敗条件 → 状態・更新規則の変更 → 同予算の対照との効果と限界。', size=15)

    s = slide('02 / 実験アーキテクチャ', '凍結した実行器から、模擬アプリを操作する',
              'M3 IQ4_XS、64K、全履歴、同じ公開API。物理的な並列推論は行わない。', footer)
    node(s, 40, 181, 250, 100, '事前選定の６課題', '要求を見る前にID・順序を固定')
    node(s, 345, 181, 250, 100, '単一の実行ループ', 'モデル → 公開API → 観測')
    node(s, 650, 181, 270, 100, '模擬環境と成果物', '操作順・費用・境界状態を保存')
    arrow(s, 290, 230, 343, 230); arrow(s, 595, 230, 648, 230)
    text(s, 45, 322, 870, 125,
         '各課題：45万総トークン、80モデル呼出し、80 API、30分。\n'
         '独立評価は後続モデルへ返さず、全６件終了後に内容を分析する。\n'
         '80 APIは研究側の追加上限。公式の応答回数とは異なる。\n'
         '現基準は残予算を逐次提示しない。上限停止だけから新機構を正当化しない。', 18)

    s = slide('03 / 全６件の結果', '全結果を同じ表へ残す',
              '課題が違うP11・P18との成否差を、方式改善の効果とは扱わない。', footer)
    reasons = {'agent_declared_complete': '完了宣言', 'api_request_limit': 'API上限',
               'token_reservation_limit': 'トークン予約上限', 'context_limit': '入力上限',
               'wall_limit': '時間上限', 'wall_limit_during_model_call': '生成中の時間上限',
               'wall_limit_during_count': '入力計測中の時間上限'}
    rows = []
    for label, result, cost in zip(note['task_labels'], summary['trials'], budget['trials'], strict=True):
        status = '成功' if result['evaluation']['official_success'] else '未達'
        stop = reasons.get(result['stop_reason'], result['stop_reason'])
        rows.append([label, status+'・'+stop, f"{result['known_total_tokens']:,}", str(cost['api_requests'])])
    rows.append(['合計', f'{successes}/6 成功', f"{summary['known_total_tokens']:,}", str(apis)])
    table(s, ['課題', '結果・終了条件', '既知トークン', '送信API'], rows,
          [270, 300, 180, 130], y=163, row_h=39, size=16)
    text(s, 45, 483, 870, 25, f"使用量不明 {summary['unknown_usage_calls']}件。監査不一致０。完了宣言と独立評価を区別する。", 14, MUTED)

    s = slide('04 / 資源使用量', '成功・未達の両方にかかった量を示す',
              '破線は各課題の上限。既知トークンは使用量不明がある場合には下限。', footer)
    picture(s, 'native_budget', x=22, y=162, w=916, h=326)

    s = slide('05 / 公開観測からの考察', '観測事実と、まだ検証していない原因を分ける', source=footer)
    for x, finding in zip((40, 500), note['findings'], strict=True):
        card(s, x, 169, 420, 265, finding['title'], finding['text'], body_size=17)
    banner(s, note['interpretation_limit'], size=15)

    s = slide('06 / 次に何をするか', note['next_title'],
              '目標：２段組４ページ、10/23主要実験・あらまし、10/31投稿完了。', footer)
    text(s, 45, 164, 870, 140, note['next_text'], 17)
    links = [('P22：全結果・採否・代案', 'docs/P22_findings.md'),
             ('同じ予算での既存対照の位置づけ', 'docs/budget_and_evidence_review_20261021.md'),
             ('原稿と新規性の現在地', 'papers/202610_letter/README.md'),
             ('４ページで主張できる評価範囲', 'docs/letter_evaluation_scope_20261021.md')]
    for i, (label, path) in enumerate(links):
        text(s, 48, 325+38*i, 860, 28, label, 17, TEAL, True, url=REPO+path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args = parser.parse_args()
    summary, budget, note, paths = sources()
    build(summary, budget, note)
    render(SLIDES, OUTPUT, args.font, stem=STEM, title='P22：追加６開発課題の全結果と次の比較')
    manifest = {'pages': len(SLIDES), 'scope': 'All-six development baseline, not a new-method result.',
                'source_sha256': {p: sha(ROOT/p) for p in paths},
                'builder_source_sha256': {p: sha(ROOT/p) for p in (
                    'scripts/build_p22_presentation.py', 'scripts/build_research_presentation.py',
                    'scripts/presentation_renderer.py', 'scripts/plot_native_budget.py')},
                'figures_sha256': {p.stem: sha(p) for p in (OUTPUT/'figures').glob('*.png')},
                'font': str(args.font), 'font_file_redistributed': False}
    (OUTPUT/'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    transcript = ['# P22：追加６開発課題の全結果と次の比較', '', manifest['scope'], '']
    for i, spec in enumerate(SLIDES, 1):
        transcript += [f"## {i}. {spec['title']}", '']
        transcript += [e['text']+'\n' for e in spec['elements'] if e['kind'] == 'text']
    (OUTPUT/'transcript.md').write_text('\n'.join(transcript)+'\n')
    print(json.dumps({'pages': len(SLIDES), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()

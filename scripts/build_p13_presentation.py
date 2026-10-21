"""Build the P11-P13 milestone from audited aggregates, including unknown costs."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from build_research_presentation import (
    SLIDES, slide, text, arrow, node, card, banner, table, picture,
    NAVY, TEAL, MUTED, AMBER, LIGHT, WARM,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p13'
STEM = 'AI_harness_P11_P13_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'
LABELS = ['全履歴', '直近履歴', 'FOCUS適合版']


def totals(measured):
    trials = measured['trials']
    if measured['pending'] or measured['audit_errors'] or len(trials) != 4:
        raise ValueError('four completed audited tasks are required for this milestone')
    if any(t['evaluation'] is None or t['audit_errors'] for t in trials):
        raise ValueError('each task requires independent evaluation and accounting')
    memory = sum(r['input_tokens'] + r['output_tokens'] for t in trials
                 for role, r in t['usage_by_role'].items() if role != 'agent')
    return {'tokens': measured['known_total_tokens'], 'unknown': measured['unknown_usage_calls'],
            'successes': sum(t['evaluation']['official_success'] for t in trials),
            'calls': measured['total_model_calls'], 'memory_tokens': memory,
            'minutes': sum(t['wall_seconds'] for t in trials) / 60}


def figures(data):
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 14,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.5), layout='constrained')
    colors = ['#286b8a', '#bd732a', '#6c8d55']
    for i, row in enumerate(data):
        executor = (row['tokens'] - row['memory_tokens']) / 1000
        memory = row['memory_tokens'] / 1000
        axes[0].bar(i, executor, color=colors[i], width=.6)
        axes[0].bar(i, memory, bottom=executor, color=colors[i], hatch='//',
                    edgecolor='#333333', linewidth=.5, width=.6)
        prefix = '≥' if row['unknown'] else ''
        axes[0].text(i, row['tokens']/1000 + 12, f"{prefix}{row['tokens']:,}",
                     ha='center', fontsize=13, weight='bold')
        if row['unknown']:
            axes[0].plot(i, row['tokens']/1000, marker='^', color='#222222', markersize=7)
        axes[1].bar(i, row['minutes'], color=colors[i], width=.6)
        axes[1].text(i, row['minutes'] + .8, f"{row['minutes']:.1f}分", ha='center', fontsize=14)
    for ax in axes:
        ax.set_xticks(range(3), [f"{label}\n成功 {d['successes']}/4" for label, d in zip(LABELS, data)])
        ax.grid(axis='y', alpha=.18); ax.set_axisbelow(True)
    axes[0].set_ylim(0, max(d['tokens']/1000 for d in data)*1.25)
    axes[0].set_ylabel('既知の入力＋出力（千トークン）')
    axes[0].legend(handles=[Patch(facecolor='white', edgecolor='#333333', hatch='//',
                                 label='保持役の生成費用')], fontsize=11, loc='upper left', frameon=False)
    axes[1].set_ylim(0, max(d['minutes'] for d in data)*1.25)
    axes[1].set_ylabel('実行時間の合計（分）')
    axes[0].set_title('不明費用は下限として表示')
    axes[1].set_title('計数・保持更新・ツールを含む')
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(OUTPUT / 'figures' / ('cohort_totals.'+ext), dpi=180,
                    metadata={'Creator': 'build_p13_presentation.py'})
    plt.close(fig)


def build(measured, data, interruption, submissions):
    SLIDES.clear()
    footer = '2026-10-21｜P11〜P13 開発比較｜独自機構・品質維持は未確定'
    p13 = data[2]
    s = slide('RESEARCH CHECKPOINT / P11–P13', '情報を短くするだけで、仕事は安くなるか', source=footer)
    text(s, 40, 155, 880, 110, '同じモデルで品質を保ち、\n仕事全体の入力・出力を減らしたい。', 32, NAVY, True)
    text(s, 40, 290, 880, 112,
         '全履歴、直近履歴、先行研究に基づく保持を比較。\n再取得と保持生成の費用、形式不備、時間上限を調べた。\n新しい方式を提案する前に、強い比較対象を整える段階。', 21)
    banner(s, '成果は比較基盤と具体的な制約の観測。新規アルゴリズムの完成ではない。', size=16.5)

    s = slide('01 / 背景・目的', '短い入力の利益と、情報を失う負担を同時に測る',
              '複数工程の仕事では、過去の対象・条件・実行結果を後の判断でも使う。', footer)
    card(s, 40, 175, 280, 250, '全情報を保持',
         '必要な根拠を参照できる。\n一方で、入力が増えて\n費用や上限が問題になる。', body_size=18)
    card(s, 340, 175, 280, 250, '履歴を削る',
         '各回の入力を減らせる。\nただし再取得や再作業で\n全体費用が増える場合がある。', body_size=18)
    card(s, 640, 175, 280, 250, '保持をAIに選ばせる',
         '将来必要な情報を選ぶ。\n選択自体にも推論費用と\n誤り・形式不備が生じ得る。', body_size=18)
    banner(s, '目的：一定の品質条件の下で総入力＋出力を減らす。キャッシュの速度改善とは別。', size=15.5)

    s = slide('02 / 実装済みアーキテクチャ', '情報・操作・評価を分けるハーネス',
              '同じMiniMax M3を役割ごとに呼び出す。物理的には単一スロット。', footer)
    node(s, 40, 174, 240, 90, '公開の要求・API仕様', '正解・追加評価は渡さない')
    node(s, 340, 174, 280, 90, '実行役のLLM', '調査・操作・完了判断')
    node(s, 680, 174, 240, 90, '模擬アプリ環境', 'API操作と状態の変化')
    arrow(s, 280, 219, 338, 219); arrow(s, 620, 219, 678, 219)
    node(s, 340, 324, 280, 100, '作業用の情報', '全履歴／直近／FOCUS', fill=WARM, accent=AMBER)
    node(s, 680, 324, 240, 100, '原記録・保存点', '原文再読・費用・DB差分')
    node(s, 40, 324, 240, 100, '終了後の独立評価', '最終状態を別プロセスで検査')
    arrow(s, 800, 264, 800, 322); arrow(s, 680, 374, 622, 374)
    arrow(s, 480, 324, 480, 266); arrow(s, 340, 374, 282, 374, dashed=True)
    banner(s, 'モデルの重みではなく、渡す情報・ツール実行・保持・費用管理を設計している。', size=16)

    s = slide('03 / 比較した三条件', '基本接続・モデル・課題をそろえて保持だけを比較',
              '4開発課題、各条件1試行。独立した本評価や品質同等性の検定ではない。', footer)
    table(s, ['条件', '保持するもの', '追加の費用'], [
        ['P11 全履歴', '元の会話と原観測を保持', '履歴を毎回入力'],
        ['P12 直近履歴', '4Kを目安に元応答単位で保持', '原文の再読・必要情報の再取得'],
        ['P13 FOCUS適合版', '将来計画の引用＋防御的な救済', '草案生成も同じ総枠へ算入'],
    ], [170, 365, 345], y=175, row_h=66, size=16)
    banner(s, '各課題：45万総トークン、30分、80 LLM呼出・80 API要求。両予算の下で比較。', size=16)

    s = slide('04 / 全成否と費用', '不成功・不明費用も含めた4課題の比較',
              '中断した追加試行の支出は次頁で別記。未知費用を0と置かない。', footer)
    table(s, ['条件', '成功', '既知総トークン', 'LLM呼出', '費用不明'], [
        [label, f"{d['successes']}/4", ('≥' if d['unknown'] else '') + f"{d['tokens']:,}",
         str(d['calls']), str(d['unknown'])] for label, d in zip(LABELS, data)
    ], [205, 115, 255, 145, 160], y=180, row_h=62, size=18)
    banner(s, '直近履歴は全履歴より総費用42.5%増。削った量だけでは効率を評価できない。', size=16)

    s = slide('05 / 比較グラフ', '品質と費用を一緒に読む',
              '保持生成も費用に含む。時間は独立評価を除く。各条件1回の開発観察。', footer)
    picture(s, 'cohort_totals', x=40, y=161, w=880, h=300)
    text(s, 48, 468, 865, 25, 'FOCUS適合版には時間上限・形式不備・再起動の影響がある。原論文の成績ではない。', 13, MUTED)

    s = slide('06 / 中断と再開', '実験を再開しても、元の支出を消さない',
              'プロセス消失を確認。保存されたrunning状態だけで稼働中とは判断しない。', footer)
    table(s, ['保存した中断試行', '扱い'], [
        ['第3課題：4応答／52,285トークン', '最終評価なし・研究支出へ算入'],
        ['応答未保存の要求1件', '使用量不明。完了・費用0としない'],
        ['第3課題を新IDで初期実行', '同一状態の完全復元とは呼ばない'],
        ['第1・第2課題の成否', 'そのまま維持。成功まで再試行しない'],
    ], [440, 440], y=174, row_h=55, size=16)
    total = p13['tokens'] + interruption['interrupted_cost']['known_total_tokens']
    banner(s, f'P13関連の既知支出は少なくとも {total:,} トークン。これに不明使用量がある。', size=16)

    s = slide('07 / 直近履歴から分かったこと', '情報を取り直すことで、節約が逆転した例がある',
              '第3課題：全履歴203,066で成功、直近履歴431,471で予算停止。', footer)
    card(s, 40, 176, 420, 250, '記録で確かめた観測',
         '同じAPI・引数の再要求15組。\n前回の結果は現在の入力から外れ、\n9組は戻った結果も同じだった。\n原文再読も2回あった。', body_size=19)
    card(s, 500, 176, 420, 250, 'まだ確定できないこと',
         '同じ要求が全て無駄だったか。\n忘却だけが唯一の失敗原因か。\n通常の台帳やセッション保持で\n十分に解消できるか。', body_size=19)
    banner(s, '次の対照は通常の台帳。単純な対策で足りれば、独自機構を追加する根拠は弱い。', size=16)

    s = slide('08 / FOCUS適合版の制約', '保持する内容と、保持判断の実装費用を分ける',
              '最初の2課題の例。全課題の結果と監査はリンク先に保存する。', footer)
    table(s, ['観測', '解釈の範囲'], [
        ['課題1：保持4回で76,390トークン', '3回が形式不備、適合1回は全保持'],
        ['課題2：保持3回で45,403トークン', '全3回が適合し全保持。最終成功'],
        ['役割切替で入力の再処理が増えた', '単一スロットの時間制約にも影響'],
        ['原方式との差がある', '小さい草案モデルの効果は未検証'],
    ], [440, 440], y=174, row_h=55, size=16)
    banner(s, '形式不備や遅い適合版を利用して、原方式が劣る・新方式が必要と結論しない。', size=16)

    s = slide('09 / 新規性の現在地', '新規性は、既存部品の接続だけではまだ成立しない',
              '今回の成果物と、論文の中核としてまだ不足するものを区別する。', footer)
    card(s, 40, 176, 420, 250, 'できたこと',
         '強い基本接続と再計算できる記録。\n全費用・再取得・形式不備の分離。\n失敗と中断も残す比較実装。\n現在の方式が負担を生む箇所の観測。', body_size=18)
    card(s, 500, 176, 420, 250, 'まだ必要なこと',
         '強い既存方式でも残る機構の問題。\nその問題に対応する独自の更新規則。\n同じ品質・予算で通常対照を超える効果。\n別課題・別モデルでの成立条件。', body_size=18)
    banner(s, '独自手法の採用は未確定。単なる要約・台帳・キャッシュ改善を新しい名前で包まない。', size=15.5)

    s = slide('10 / 次に進める実験', '校正を収束させ、大規模情報で必要性を確かめる',
              'AppWorldの短い4件を、大規模・長期作業の主実験の代わりにしない。', footer)
    table(s, ['次の作業', 'なぜ行うか／何が出れば見直すか'], [
        ['通常の台帳P14', '既存の状態保持だけで十分なら独自方式を急がない'],
        ['保持提出の形式校正', '未来の計画ラベルと過去の出典IDを区別する'],
        ['固定コーパスの大規模調査', '約10万文書を維持し、取得後の保持・再取得も測る'],
        ['機構を一つに絞る', '単純対照でも残る問題がなければ候補を再検討'],
    ], [250, 630], y=174, row_h=55, size=16)
    banner(s, 'BrowseComp-Plusは配布確認まで。正式採用・評価器の動作・主実験の成功は未確定。', size=15.5)

    s = slide('11 / 出典・再現と進捗', '資料の数値から実験条件・選定理由へ戻れる',
              '原文・認証値・正解・モデルの推論本文は公開せず、集計と出典ハッシュを公開。', footer)
    links = [
        ('P11・P12の条件と全結果', 'docs/P12_findings.md'),
        ('P13の全結果・費用と限界', 'docs/P13_findings.md'),
        ('停止確認・再開理由・中断支出', 'docs/P13_recovery.md'),
        ('独自機構を選び直した理由', 'docs/technical_core_review_20261021.md'),
        ('大規模文書の導入前確認', 'docs/browsecomp_preflight_20261021.md'),
    ]
    for i, (label, path) in enumerate(links):
        text(s, 45, 178+54*i, 870, 35, label, 21, TEAL, True, url=REPO+path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path,
                        default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args = parser.parse_args()
    sources = [f'reports/P{i}_final_measurements.json' for i in (11, 12, 13)] + [
        'reports/P13_interruption_20261021.json', 'reports/P13_01_memory_submissions.json',
        'reports/P13_02_memory_submissions.json', 'reports/P12_03_reacquisition.json',
        'docs/P13_findings.md', 'docs/P13_recovery.md']
    measured = [json.loads((ROOT / p).read_text()) for p in sources[:3]]
    identities = [[r['task_id'] for r in m['trials']] for m in measured]
    if any(ids != identities[0] for ids in identities):
        raise ValueError('task identities/order differ')
    data = [totals(m) for m in measured]
    interruption = json.loads((ROOT / sources[3]).read_text())
    submissions = [json.loads((ROOT / p).read_text()) for p in sources[4:6]]
    (OUTPUT / 'figures').mkdir(parents=True, exist_ok=True)
    figures(data)
    build(measured, data, interruption, submissions)
    render(SLIDES, OUTPUT, args.font, stem=STEM, title='AIハーネス研究 P11〜P13の結果と次の判断')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {'pages': len(SLIDES), 'scope': 'Four development tasks with the original outcomes '
                'for tasks1/2 and an explicitly restarted task3. Includes failed runs, lower-bound '
                'costs and separate interrupted-attempt expenditure. Not a novel-method claim.',
                'totals': data, 'source_sha256': {p: sha(ROOT/p) for p in sources},
                'builder_source_sha256': {p: sha(ROOT/p) for p in (
                    'scripts/build_p13_presentation.py', 'scripts/build_research_presentation.py',
                    'scripts/presentation_renderer.py')},
                'figures_sha256': {'cohort_totals': sha(OUTPUT/'figures/cohort_totals.png')},
                'font': str(args.font), 'font_file_redistributed': False}
    (OUTPUT/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    transcript = ['# P11〜P13 開発比較の区切り', '', manifest['scope'], '']
    for i, spec in enumerate(SLIDES, 1):
        transcript += [f"## {i}. {spec['title']}", '']
        transcript += [e['text']+'\n' for e in spec['elements'] if e['kind']=='text']
    (OUTPUT/'transcript.md').write_text('\n'.join(transcript)+'\n')
    print(json.dumps({'pages': len(SLIDES), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()

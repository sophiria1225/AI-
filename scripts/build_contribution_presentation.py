"""Build a separate, approach-first deck; preserve the P4 historical report."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

from build_research_presentation import (
    SLIDES, slide, text, box, arrow, node, card, banner, table, picture,
    NAVY, TEAL, MUTED, AMBER, WHITE, LIGHT, BLUE, WARM,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "materials/20261020_revised"
REFS = [
    ("S1", "研究のアプローチ・貢献・反証条件", "自分たちの設計仕様",
     "https://github.com/sophiria1225/AI-/blob/main/docs/research_contribution.md"),
    ("S2", "Flow", "ICLR 2025／本文・固定コードの一部",
     "https://proceedings.iclr.cc/paper_files/paper/2025/file/ba84da6921f3040b74ee163aa7451f53-Paper-Conference.pdf"),
    ("S3", "MaAS", "ICML 2025／本文・固定コードの一部",
     "https://proceedings.mlr.press/v267/zhang25bi.html"),
    ("S4", "Puppeteer", "NeurIPS 2025／著者原稿・固定コードの一部",
     "https://proceedings.neurips.cc/paper_files/paper/2025/hash/f1320d2e2842169c6fc89dcbd80e94d0-Abstract-Conference.html"),
    ("S5", "Asynchronous Partial Overlay", "JAIR 2006／原論文・改良論文の一部",
     "https://jair.org/index.php/jair/article/view/10451"),
    ("S6", "AgentGraph", "AAAI 2026 Demonstration Track／掲載3ページ",
     "https://ojs.aaai.org/index.php/AAAI/article/download/42393/46354"),
    ("S7", "WinnowRAG", "EMNLP 2025／掲載概要・書誌",
     "https://aclanthology.org/2025.emnlp-main.587/"),
    ("S8", "Calibration Is Not Control", "著者公開原稿／正式採録未確認",
     "https://arxiv.org/html/2606.21399v1"),
    ("S9", "P3・P5の観察と限界", "自分たちの開発実験／各条件1試行",
     "https://github.com/sophiria1225/AI-/blob/main/docs/P5_findings.md"),
    ("S10", "E1の介入・保存復元仕様", "設計と契約検査／LLMによる四条件比較は未実施",
     "https://github.com/sophiria1225/AI-/blob/main/docs/experiments/E1_intervention_contract.md"),
]


def load_data(font_path):
    sources = [
        "reports/P3_measurements.json", "reports/P5_pro_measurements.json",
        "docs/research_contribution.md", "docs/experiments/E1_intervention_contract.md",
        "docs/related_work_matrix.md", "reports/E1_checkpoint_contract_controls.json",
    ]
    p3 = json.loads((ROOT / sources[0]).read_text())
    p5 = json.loads((ROOT / sources[1]).read_text())
    rows = []
    for r in p3["runs"]:
        rows.append({
            "phase": "P3", "task": r["task"], "strategy": r["strategy"],
            "total_tokens": r["known_total_tokens"], "resolved": r["evaluation"]["resolved"],
            "wall_seconds": r["wall_seconds"], "token_budget": 300000,
        })
    for r in p5["runs"]:
        m = r["result"]["measurements"]
        rows.append({
            "phase": "P5", "task": "Ansible", "strategy": r["strategy"],
            "total_tokens": m["known_total_tokens"], "resolved": m["evaluation"]["resolved"],
            "wall_seconds": m["wall_seconds"], "token_budget": 600000,
        })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "figures").mkdir(exist_ok=True)
    data = {
        "cutoff": "P5 completed; E1 checkpoint contract synthetic controls only",
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
        "observations": rows, "references": REFS,
        "notes": ["Do not pool P3/P5 outcomes or interpret small token differences as savings.",
                  "No task transfer policy or four-arm efficacy experiment has been run."],
    }
    (OUTPUT / "data_sources.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    with (OUTPUT / "observations.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fp = FontProperties(fname=str(font_path))
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.8), layout="constrained")
    fig.set_facecolor("#F5F7FA")
    for ax, task, title in zip(
        axes, ["django__django-15380", "django__django-15957", "Ansible"],
        ["P3 / Django 15380\n予算 300,000", "P3 / Django 15957\n予算 300,000",
         "P5 / Ansible\n予算 600,000"],
    ):
        subset = sorted((r for r in rows if r["task"] == task),
                        key=lambda r: r["strategy"] != "single")
        budget = subset[0]["token_budget"]
        ax.set_facecolor("#F5F7FA")
        ax.barh([1, 0], [r["total_tokens"] for r in subset], color=[NAVY, TEAL], height=.42)
        ax.set_yticks([1, 0], ["単一", "2担当"], fontproperties=fp, fontsize=12)
        for y, r in zip([1, 0], subset):
            outcome = "合格" if r["resolved"] else "未解決"
            ax.text(0, y+.28, f'{r["total_tokens"]:,} / {outcome}', fontproperties=fp,
                    color=NAVY, fontsize=12)
        ax.set_title(title, fontproperties=fp, fontsize=14, color=NAVY, pad=16)
        ax.set_xlim(0, budget)
        ax.set_ylim(-.5, 1.7)
        ax.set_xticks([0, budget/2, budget],
                      [f"{v:,.0f}" for v in (0, budget/2, budget)], fontsize=9)
        ax.set_xlabel("全入力＋出力トークン", fontproperties=fp, fontsize=10)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(OUTPUT / "figures" / ("observations." + ext), dpi=180)
    plt.close(fig)
    return data


def build():
    SLIDES.clear()
    s = slide("RESEARCH APPROACH / 改訂版", "共有で足りるか、仕事の担当を変えるべきか",
              source="2026-10-20｜目的と差分を先に説明する改訂版｜研究期限：2027年12月")
    text(s, 40, 143, 880, 110,
         "情報を渡す効果と、\n判断・実行を一人へ移す効果を切り分ける。", 31, NAVY, True)
    text(s, 40, 280, 860, 80,
         "追加の利益がある局面だけ、関連する未完了作業を引き継ぐ。\n品質を保ち、全担当の総トークンを減らすことを目指す。", 23)
    banner(s, "狙う新規性の説明。担当変更の有効性は、まだ実証していない。",
           y=426, fill=WARM, accent=AMBER)

    s = slide("01 / 背景と問い", "後から分かった共通条件を、誰が判断・実行するか",
              "仮想例：認証担当と保存担当が、識別子の形式と互換性を共同で決める。",
              "出典 S1｜説明用の仮想例。現在の実験で観測した衝突ではない。")
    for x, h, body in [
        (40, "情報を共有", "同じ仕様・コードを読む。\n判断と変更は各担当。\n情報不足を解消できるか。"),
        (340, "中央で方針を決定", "共通仕様を決めて渡す。\n変更は元の担当が実行。\n判断の往復を減らせるか。"),
        (640, "関連作業を引き継ぐ", "一人が双方の条件を持ち、\n判断から変更まで行う。\n実行の分断も問題か。"),
    ]:
        card(s, x, 176, 280, 246, h, body, body_size=19)
    banner(s, "最後の方法が常に最善ではない。文脈集中と移管の費用も発生する。")

    s = slide("02 / 近接研究", "動的な担当選択・再編・費用削減は既に研究されている",
              "既存方式を「固定分担しかできない」と扱わない。",
              "出典 S2–S5｜本文・一部コードの読み取り。性能の完全再現ではない。")
    table(s, ["研究", "既に扱うもの", "今回の扱い"], [
        ["MaAS", "構成・資源配分の選択", "構成最適化だけを新規性にしない"],
        ["Flow", "実行中の作業・担当変更", "直接近い動的方式として比較する"],
        ["Puppeteer", "状態に応じた担当選択と費用", "同じ情報・予算で追加価値を問う"],
        ["APO", "関連部分の一時的な集中処理", "集中化の原理自体は既存技術"],
    ], [160, 355, 365], y=169, row_h=51, size=17)
    banner(s, "差分候補：何を変える必要があるかを、競合する処置と切り分ける。")

    s = slide("03 / 融合や分岐も、そのままでは独自ではない", "「まとめる機能」から「追加価値の検証」へ",
              "エージェント統合、履歴分析、介入の利益予測にも先行研究がある。",
              "出典 S6–S8｜AgentGraphはデモ論文。WinnowRAGは概要確認。S8の採録未確認。")
    table(s, ["研究", "重なる発想", "この研究で詰めること"], [
        ["AgentGraph", "ログから担当・作業の統合を推奨", "推奨した移管が他の対応より有益か"],
        ["WinnowRAG", "回答をまとめ上位の担当で議論", "進行中の判断・実行責任の扱い"],
        ["Calibration Is\nNot Control", "同一状態の分岐・介入価値の比較", "整理／方針／担当変更の対照"],
    ], [175, 350, 355], y=174, row_h=65, size=16.5)
    banner(s, "この組み合わせが未研究だとは断定しない。近接方式との比較が必要。")

    s = slide("04 / 狙う貢献", "問い、制御方式、設計指針を一本につなぐ",
              "三つとも研究の目標。現在の実測で成立した貢献とは区別する。", "出典 S1")
    card(s, 40, 178, 280, 258, "① 機構を切り分ける",
         "同じ情報を持っていても、\n判断と実行の分断で\n負担が残る条件を測る。\nない条件も含める。", body_size=19)
    card(s, 340, 178, 280, 258, "② 必要な部分だけ移す",
         "履歴・必要文脈・残予算から\n対応を選ぶ。\n移管費用を上回る利益が\nある場合に限定する。", body_size=19)
    card(s, 640, 178, 280, 258, "③ 条件を説明する",
         "共有で十分な範囲。\n中央調整で十分な範囲。\n担当変更が有益な範囲。\n品質と費用で整理する。", body_size=19)
    banner(s, "まず①。追加価値が確認できた場合に②へ進む。", y=450)

    s = slide("05 / 提案機構の設計図", "変更するのは、未完了作業・文脈・更新責任",
              "モデルの外側にある、仕事の割り当てと実行状態を制御する。", "出典 S1・S10｜提案設計。自動移管器は未実装。")
    node(s, 40, 174, 240, 100, "実行履歴と現在状態", "作業ID・版・公開検査\n相互修正・残予算")
    node(s, 340, 174, 280, 100, "対応の選択", "継続／整理／中央調整／移管\n品質と全費用を比較", fill=WARM, accent=AMBER)
    node(s, 680, 174, 240, 100, "関連する二担当", "Aの未完了作業\nBの未完了作業")
    arrow(s, 280, 224, 338, 224)
    arrow(s, 620, 224, 678, 224)
    arrow(s, 800, 276, 800, 315)
    node(s, 680, 319, 240, 107, "一人へ引き継ぐ", "作業 + 根拠 + 文脈\n共同判断 + 関連更新", fill=WARM, accent=AMBER, dashed=True)
    node(s, 340, 319, 280, 107, "共通の公開検査", "版・未完了事項を更新\n必要なら独立作業を再分担")
    node(s, 40, 319, 240, 107, "独立した最終評価", "品質と全入力＋出力\n正解は途中へ戻さない")
    arrow(s, 680, 373, 622, 373)
    arrow(s, 340, 373, 282, 373)
    banner(s, "担当変更だけでなく、必要情報の再入力・検査・失敗の費用も数える。")

    s = slide("06 / 反復の目的を明確にする", "同じ途中状態を、四つの対応へ分ける",
              "状態保存・復元を確認し、B/C/Dで取得済み根拠と文脈更新をそろえる。",
              "出典 S10｜四条件のLLM比較は未実施。A/Bでは整理と履歴更新をまとめて測る。")
    table(s, ["対応", "情報・文脈", "判断と実行"], [
        ["A 継続", "元の担当履歴", "元の担当を維持"],
        ["B 情報整理", "共通の状態文書で更新", "元の担当を維持"],
        ["C 中央調整", "Bと同じ更新・原資料アクセス", "共同方針 → 元の担当が実行"],
        ["D 担当変更", "B/Cと同じ更新・原資料アクセス", "関連部分を一人が判断・実行"],
    ], [165, 350, 365], y=173, row_h=50, size=17)
    banner(s, "Dだけ履歴を新しくすると、「担当変更」ではなく「整理」の効果が混ざる。",
           size=17)

    s = slide("07 / 最も重要な対照", "中央で決めるだけで十分なら、移管は不要",
              "C/Dは共通の計画生成手順を使い、調整役の呼び出しも費用に含める。", "出典 S1・S10")
    node(s, 40, 175, 880, 82, "同じ保存状態・取得済み根拠・残予算",
         "同じモデル、基本ツール、状態文書、文脈更新。新しい正解情報は追加しない。")
    arrow(s, 255, 258, 255, 288)
    arrow(s, 705, 258, 705, 288)
    node(s, 40, 292, 430, 114, "C：方針を渡し、元の担当が実行",
         "共同方針は共有する。\n更新を進める担当範囲は維持する。", fill=BLUE, accent=NAVY)
    node(s, 490, 292, 430, 114, "D：共同判断から関連更新まで引き取る",
         "同じ方針作成手順の後、関連部分の\n作業・文脈・更新責任を移す。", fill=WARM, accent=AMBER)
    text(s, 40, 428, 880, 58,
         "強い比較対象も残す：中央役が直接実行できる方式。\nその方式とDが機能的に同じなら、別方式として新規性を主張しない。", 18)

    s = slide("08 / 制御方式と成功条件", "失敗しそうかより、どの対応が品質と費用で有利か",
              "移管の利益が局面によって変わることを確認した後に、選択器を作る。", "出典 S1・S8・S10｜利益予測の一般形式は既出。品質許容差・件数は未確定。")
    box(s, 40, 175, 880, 95, LIGHT)
    text(s, 60, 192, 840, 60,
         "目的：品質の許容条件を満たす中で、全入力＋出力を最小化\nmin E[C]    subject to    E[Y] − E[Y_reference] ≥ −δ", 22)
    card(s, 40, 293, 280, 139, "観測するもの",
         "相互修正・必要文脈・残予算", TEAL, WHITE, 17)
    card(s, 340, 293, 280, 139, "比べるもの",
         "各対応の品質・全費用・移管費用", TEAL, WHITE, 17)
    card(s, 640, 293, 280, 139, "初期の比較",
         "固定時点・往復回数の単純規則", TEAL, WHITE, 17)
    banner(s, "品質低下で安く終わる方式は成功ではない。非有意差を同等と呼ばない。",
           size=17)

    s = slide("09 / 現在の実測", "基準方式の観察はできた。担当変更の検証はこれから",
              "P3とP5は別の課題・予算。各課題・方式1試行で、成績を合算しない。",
              "出典 S9・data_sources.json｜全件予算停止。グラフの横軸上限はP3/P5で異なる。")
    picture(s, "observations", x=40, y=166, w=880, h=254)
    banner(s, "この小さな差を削減率にしない。品質維持・移管の必要性は未実証。")

    s = slide("10 / P5から分かった限界", "両方が未解決では、担当変更が必要とは言えない",
              "Ansibleで入力・モデル・予算をそろえた比較。追加の成功待ち反復は行わない。",
              "出典 S9：P5_findings.md・P5_pro_measurements.json")
    table(s, ["項目", "固定2担当", "単一"], [
        ["全入力＋出力", "580,169", "571,839"],
        ["要求／既存動作の合格", "0/4 ／ 21/21", "0/4 ／ 21/21"],
        ["修正パッチ／途中の変更", "0バイト ／ 0回", "0バイト ／ 0回"],
        ["実時間／入力キャッシュ比", "5,050.03秒 ／ 14.58%", "509.62秒 ／ 96.05%"],
    ], [345, 267, 268], y=171, row_h=50, size=17)
    text(s, 40, 438, 880, 50,
         "相互修正・更新責任の衝突は示せていない。\n時間差はキャッシュを含む実装条件の差で、意味的な調整負担とは区別する。", 17)

    s = slide("11 / 今回続けた実装", "「同じ状態から比較した」と言える条件を作る",
              "状態保存の契約と12項目の制御検査を追加。実コンテナの完全復元は次段階。",
              "出典 S10・E1_checkpoint_contract_controls.json｜合成データでの基盤検査。")
    node(s, 40, 176, 265, 153, "保存すべきもの", "会話・作業管理・予算\n完了状態・ファイル状態\nツール設定と外部入力")
    arrow(s, 306, 251, 345, 251)
    node(s, 350, 176, 265, 153, "不足・不一致を検出", "一時領域の申告漏れ\n保留操作・不明費用\n内容ハッシュ・環境・予算")
    arrow(s, 616, 251, 655, 251)
    node(s, 660, 176, 260, 153, "復元物と照合", "宣言した保存物の一致\n異なる状態なら比較を拒否\n内容を公開せず検査")
    text(s, 40, 359, 880, 78,
         "実装済み：宣言された保存物・範囲・予算・環境の照合。\n未実装：実行中コンテナの完全捕捉、復元後の再実行、四条件のLLM比較。\n保存対象の列挙漏れを自動的に発見する保証はない。", 19)
    banner(s, "12検査の合格は研究手法の改善ではなく、誤った比較を防ぐ基盤の成果。",
           size=17)

    s = slide("12 / 次の実験は何を決めるか", "機能を増やす前に、提案が必要になる条件を確かめる",
              "同じ基準試行を増やすだけの進め方から、機構を区別する検証へ移る。", "出典 S1・S10")
    table(s, ["順序", "確認すること", "進む条件"], [
        ["1 復元校正", "一時・未追跡ファイルも含む復元", "同じ公開操作と結果が再現する"],
        ["2 対象現象", "実際の修正・共同判断の負担", "単なる未着手・知識不足と区別"],
        ["3 四条件", "B/Cを超えるDの追加効果", "費用を含めて利益が残る"],
        ["4 自動選択", "単純規則・近接動的方式と比較", "品質条件を満たして総費用減"],
    ], [170, 355, 355], y=173, row_h=50, size=17)
    banner(s, "状態によって適切な対応が変わらなければ、複雑な判断器は作らない。",
           size=17)

    s = slide("13 / 得たい成果と反証条件", "何を共有し、何を一緒に判断・実行させるべきか",
              "出したい成果は平均スコアだけでなく、ハーネスの構成を選ぶ条件。", "出典 S1｜結果が支持した範囲でのみ論文化する。")
    table(s, ["得られた結果", "主張できること／見直すこと"], [
        ["BでDと同等", "情報整理で十分。担当変更の追加価値は示せない"],
        ["Cや柔軟な中央役で同等", "共同方針・中央実行で十分。名称で差を作らない"],
        ["Dに条件付きの利益", "文脈量・依存・予算に応じた担当変更の設計指針"],
        ["選択器が単純規則と同等", "複雑な学習器の必要性を主張しない"],
    ], [300, 580], y=173, row_h=51, size=17)
    banner(s, "提案機構 + 比較基盤 + 条件付きの知見。新規性は、実証して成立させる。",
           size=17)

    for group, label in [(REFS[:5], "14"), (REFS[5:], "15")]:
        s = slide(label + " / 原典と記録", "出典と、確認した範囲",
                  "青緑の題名から原典へ移動できる。既存研究の性能再現は未完了。",
                  "確認日：2026-10-20｜追加候補・版・未確認事項は docs/related_work_matrix.md")
        for i, (sid, title, scope, url) in enumerate(group):
            y = 169 + 63*i
            text(s, 40, y, 875, 31, sid + "  " + title, 19, TEAL, True, url=url)
            text(s, 40, y+29, 875, 27, scope, 16, MUTED)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path,
                        default=Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"))
    args = parser.parse_args()
    load_data(args.font)
    build()
    render(SLIDES, OUTPUT, args.font)
    transcript = ["# 研究アプローチの説明・改訂版", "",
                  "図・数値の出典と確認範囲はdata_sources.json。旧P4報告は別保存。", ""]
    for i, s in enumerate(SLIDES, 1):
        transcript += [f"## {i}. {s['title']}", ""]
        transcript += [e["text"] + "\n" for e in s["elements"] if e["kind"] == "text"]
    (OUTPUT / "transcript.md").write_text("\n".join(transcript) + "\n")
    code = ["scripts/build_contribution_presentation.py", "scripts/build_research_presentation.py",
            "scripts/presentation_renderer.py"]
    (OUTPUT / "build_manifest.json").write_text(json.dumps({
        "purpose": "Approach-first revision; old deck unchanged",
        "pages": len(SLIDES),
        "builder_source_sha256": {
            p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in code},
        "regenerate": "reporting-venv/bin/python scripts/build_contribution_presentation.py",
        "font": str(args.font), "font_file_redistributed": False,
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pages": len(SLIDES), "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()

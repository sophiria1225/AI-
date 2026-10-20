"""Rebuild the 2026-10-20 Japanese progress deck from committed aggregates.

Run in a separate reporting environment; no experiment, model, or GitHub calls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from presentation_charts import generate
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
BG, NAVY, TEAL = "#F5F7FA", "#17304D", "#087F8C"
MUTED, AMBER, RED, WHITE = "#617084", "#B67922", "#B84D4D", "#FFFFFF"
LIGHT, BLUE, WARM = "#E7F3F3", "#E8EEF6", "#FBF1DF"
REPO = "https://github.com/sophiria1225/AI-"
SLIDES = []


def text(s, x, y, w, h, content, size=20, color=NAVY, bold=False, url=None, leading=1.32):
    s["elements"].append(dict(kind="text", x=x, y=y, w=w, h=h, text=content,
                              size=size, color=color, bold=bold, url=url, leading=leading))


def box(s, x, y, w, h, fill=WHITE, stroke=None, dashed=False):
    s["elements"].append(dict(kind="box", x=x, y=y, w=w, h=h, fill=fill,
                              stroke=stroke, dashed=dashed))


def arrow(s, x, y, x2, y2, color=MUTED, dashed=False, end=True):
    s["elements"].append(dict(kind="line", x=x, y=y, x2=x2, y2=y2,
                              color=color, dashed=dashed, arrow=end))


def slide(section, title, subtitle="", source="", notes=""):
    s = dict(title=title, notes=notes, elements=[], background=BG)
    SLIDES.append(s)
    box(s, 0, 0, 12, 540, TEAL)
    text(s, 40, 21, 800, 22, section, 12, TEAL, True)
    text(s, 40, 54, 880, 48, title, 30, NAVY, True)
    if subtitle:
        text(s, 40, 109, 880, 54, subtitle, 17, MUTED)
    arrow(s, 40, 502, 920, 502, "#D8E0E8", end=False)
    text(s, 40, 511, 812, 21, source or "AIハーネス研究｜2026-10-20｜開発段階の中間報告", 10, MUTED)
    text(s, 868, 510, 60, 21, f"{len(SLIDES):02d}", 11, MUTED)
    return s


def card(s, x, y, w, h, heading, body, accent=TEAL, fill=WHITE, body_size=19):
    box(s, x, y, w, h, fill)
    box(s, x, y, 4, h, accent)
    text(s, x+18, y+16, w-36, 55, heading, 22, accent, True)
    text(s, x+18, y+78, w-36, h-92, body, body_size)


def node(s, x, y, w, h, heading, body="", fill=LIGHT, accent=TEAL, dashed=False):
    box(s, x, y, w, h, fill, accent, dashed)
    text(s, x+12, y+10, w-24, 38, heading, 19, accent, True)
    if body:
        text(s, x+12, y+44, w-24, h-50, body, 15.5)


def banner(s, content, y=449, fill=LIGHT, accent=TEAL, size=18):
    box(s, 40, y, 880, 43, fill)
    text(s, 55, y+9, 850, 31, content, size, accent, True)


def table(s, headers, rows, widths, y=170, row_h=56, size=17):
    x0 = 40
    for ri, row in enumerate([headers]+rows):
        x = x0
        for width, content in zip(widths, row):
            fill = NAVY if ri == 0 else (WHITE if ri % 2 else "#EDF1F6")
            box(s, x, y+ri*row_h, width-1, row_h-1, fill)
            text(s, x+10, y+ri*row_h+10, width-20, row_h-14, str(content),
                 size if ri else size-1, WHITE if ri == 0 else NAVY, bold=ri == 0)
            x += width


def picture(s, name, x=40, y=164, w=880, h=280):
    s["elements"].append(dict(kind="image", x=x, y=y, w=w, h=h,
                              path=f"figures/{name}.png"))


def build(p3, p4):
    m4 = p4["measurements"]
    s = slide("RESEARCH PROGRESS  /  2026.10.20", "AIハーネスの実行制御を検証する",
              source="対象リポジトリ：sophiria1225/AI-｜到達点：P4_PRO_01の独立評価完了",
              notes="2026年10月13日の引き継ぎに従い、総トークン削減を品質条件の下で検証する。"
                    "本資料は実験P4までの区切り。新手法の有効性を実証した論文ではない。")
    text(s, 40, 140, 850, 106, "品質を保ちながら、仕事の完了までに使う\n全担当の総トークンを減らす。", 33, NAVY, True)
    text(s, 40, 274, 825, 82, "分担・情報共有・作業状態の引き継ぎを、\n同じモデルと計算予算でどう設計するか。", 24)
    for x, heading, body in [(40,"今回の報告","目的・構成・実測・考察"),(340,"実験の区切り","基準方式 + Ansible初回"),(640,"研究期限","2027年12月")]:
        box(s,x,390,280,88,WHITE)
        text(s,x+15,402,250,28,heading,17,TEAL,True)
        text(s,x+15,439,250,29,body,17)

    s = slide("01 / 現在地", "測れる基盤はできた。再編の利益はこれから確かめる",
              "実装・運用の成果と、学術的に証明できたことを分ける。",
              "出典 S1–S4：研究仕様、P3/P4測定・考察。各課題・方式は1試行。")
    card(s,40,176,280,258,"できたこと",
         "大型モデルの実機運用\n単一／固定2担当の実行\n全呼び出しの費用記録\n最終成果物の独立評価",TEAL)
    card(s,340,176,280,258,"今回観測したこと",
         "P3：2課題 × 2方式\n同じ課題で合格／未解決\nP4：調査は進んだが\n修正パッチを作れず",NAVY)
    card(s,640,176,280,258,"まだ言えないこと",
         "品質を保った費用削減\n分担や集約の一般的優位\n新規性の確定\n別領域への一般化",AMBER,WARM)
    banner(s,"次の一歩：構成を変える価値がある局面を、強い基準方式から探す。")

    s = slide("02 / 背景", "仕事全体の整合性を、モデルの外側で支える",
              "対象は一回の回答より長い、調査・実装・検査・修正の連続。",
              "出典 S1。下図は問題設定の説明であり、観測済みの因果関係ではない。")
    labels = [("要求を読む","資料・仕様"),("調べて決める","関連コード・条件"),("変更する","成果物・状態"),("検査して戻す","結果・未解決事項")]
    for i,(h,b) in enumerate(labels):
        x=40+i*225
        node(s,x,184,205,100,h,b)
        if i<3:arrow(s,x+205,234,x+222,234)
    arrow(s,812,286,812,320)
    arrow(s,812,320,362,320)
    arrow(s,362,320,362,286)
    card(s,40,349,430,135,"分担で扱う範囲を小さくする","担当ごとの調査・判断・文脈を整理する。",TEAL,WHITE,18)
    card(s,490,349,430,135,"分担後にも整合が必要","前提の共有、変更の往復、履歴の再入力。",NAVY,WHITE,18)

    s = slide("03 / 目的", "品質を条件に、仕事全体の総トークンを減らす",
              "節約だけを目的にせず、未完了や失敗も含めて評価する。",
              "出典 S1・S8：研究仕様と確認評価の検討。式は目標の定式化で、達成済みではない。")
    box(s,40,175,880,110,NAVY)
    text(s,60,190,830,45,"最小化：E [ C全担当・全制御 ]",29,WHITE,True)
    text(s,60,244,830,37,"制約：品質が基準方式から許容差 δ を超えて下がらない",23,WHITE)
    table(s,["測る量","今回の定義"],[
        ["費用 C","すべての入力＋出力。キャッシュ対象の入力も含む。"],
        ["品質 Q","凍結した最終成果物の独立評価。未完了は成功にしない。"],
        ["補助指標","実時間、メモリ、往復修正、移管費用、不要な変更。"],
    ],[165,715],y=296,row_h=36,size=16.5)
    banner(s,"品質許容差 δ・必要課題数・確認用課題は未確定。非有意差は同等性ではない。",size=16.5)

    s = slide("04 / 研究の順序", "現象を観測してから、再編と選択器を作る",
              "自動集約を先に完成させると、本当に必要な機構を見失う。",
              "出典 S1・S5：研究仕様と作業ボード。青緑＝実施、黄＝未実証／今後。")
    stages = [
        ("01","基盤・評価器","状態／費用／成果物","実施済み",TEAL,LIGHT),
        ("02","単一・固定分担","失敗と調整の観察","実施中",TEAL,LIGHT),
        ("03","同一状態の分岐","整理／調整／移管","これから",AMBER,WARM),
        ("04","対応の自動選択","利益と費用を予測","効果があれば",AMBER,WARM),
    ]
    for i,(no,h,b,state,c,f) in enumerate(stages):
        x=40+i*225
        box(s,x,185,205,228,f,c)
        text(s,x+16,201,173,49,no,32,c,True)
        text(s,x+16,260,173,34,h,20,c,True)
        text(s,x+16,308,173,61,b,18)
        text(s,x+16,377,173,28,state,16,c,True)
        if i<3:arrow(s,x+205,297,x+222,297,c)
    banner(s,"今は「構成比較に適した課題と、切り分け可能な失敗」を確認している。")

    s = slide("05 / 実装済みアーキテクチャ", "1つのモデルを、単一または固定2担当で共有する",
              "実験条件・全体予算・成果物の版を、共通の実行器で管理する。",
              "出典 S6：run_fixed_comparison.py / run_pro_pilot.py / artifact_capture.py / experiment_state.py",
              notes="mini-swe-agentの固定ソースへ共通モデル・環境・計測を接続。固定2担当は工程役割で、双方が全作業ツリーを変更できる。"
                    "モデルは同じ1スロットで逐次実行。評価専用の追加テストは成果物凍結後の別環境だけへ入る。")
    node(s,40,174,190,86,"固定した公開入力","要求・コード・予算")
    node(s,278,174,330,86,"共通の実行制御","単一  または  実装役 ↔ 検証役")
    node(s,656,174,264,86,"ローカルLLM","MiniMax M3 IQ4 / 1スロット")
    arrow(s,230,217,278,217)
    arrow(s,608,217,656,217)
    arrow(s,788,260,788,287)
    node(s,656,289,264,87,"共通ツールと隔離環境","読取・変更・検査 / repo全体")
    node(s,278,289,330,87,"記録・成果物・完了判定","全入力＋出力 / 差分 / 版ID")
    arrow(s,656,332,608,332)
    arrow(s,443,289,443,260)
    node(s,40,289,190,87,"公開の検査結果","実行中に利用できる")
    arrow(s,278,332,230,332)
    arrow(s,135,289,135,274,end=False)
    arrow(s,135,274,310,274,end=False)
    arrow(s,310,274,310,260)
    node(s,278,408,330,74,"最終成果物を凍結","停止時の1候補を提出",BLUE,NAVY)
    node(s,656,408,264,74,"独立した最終評価","追加テスト / 生成への返却なし",BLUE,NAVY)
    arrow(s,443,376,443,408,NAVY);arrow(s,608,446,656,446,NAVY)
    text(s,40,415,202,73,"記録・差分は保存済み。\n状態復元と分岐比較は\nこれから。",16,AMBER)

    s = slide("06 / 提案予定のアーキテクチャ", "実行中の状態から、次の対応を選ぶハーネスへ",
              "黄の部分は計画段階。自動再編の効果を示す実験はまだ行っていない。",
              "出典 S1・S7：研究仕様と四条件分岐タスク。モデル重みの融合ではない。")
    node(s,40,175,245,101,"観測するもの","未完了作業・根拠・変更\n検査・履歴・残り予算")
    node(s,347,175,260,101,"対応を選ぶ","続行／整理／中央調整／移管",WARM,AMBER,True)
    node(s,669,175,251,101,"状態を引き継ぐ","作業・文脈・更新責任\n移管費用も計上",WARM,AMBER,True)
    arrow(s,285,224,347,224,AMBER,True);arrow(s,607,224,669,224,AMBER,True)
    node(s,347,323,573,105,"共通の実行・検証へ戻る","同じモデル、基本ツール、公開入力、全体予算を保つ",LIGHT,TEAL)
    arrow(s,794,276,794,323,AMBER,True)
    arrow(s,347,375,162,375);arrow(s,162,375,162,276)
    text(s,40,314,248,43,"観測 → 対応 → 再観測",18,TEAL,True)
    banner(s,"学習器は、状態によって有効な対応が変わり、単純規則では足りない場合に検討。",fill=WARM,accent=AMBER,size=16.7)

    s = slide("07 / 次に切り分けたい効果", "情報を整理する効果と、実行単位を変える効果を分ける",
              "同じ会話・ファイル・環境・成果物・残予算を保存して分岐する。",
              "出典 S7。四条件比較は設計段階。中央調整と移管が機能的に同じなら差分を主張しない。")
    table(s,["分岐","変えるもの","保つもの"],[
        ["A 継続","変更なし","現在の担当・文脈・更新範囲"],
        ["B 情報整理","必要根拠と現在状態を整理","担当・更新範囲"],
        ["C 中央調整","共同方針を決めて返す","元の担当が実行"],
        ["D 作業移管","関連する判断と実行を集める","モデル・ツール・総予算"],
    ],[175,345,360],y=173,row_h=52,size=17)
    banner(s,"DがB・Cを超えた場合にだけ、実行単位を変える追加価値を検討する。")

    s = slide("08 / 機材とモデル", "大型モデルを1つ共有し、担当ごとの履歴を切り替える",
              "実機の256GiBはメモリ。保存領域の容量とは別に測定した。",
              "出典 S9・S3：モデル選定、実機記録、P4の5秒間隔サンプル。GiB＝2^30バイト。")
    table(s,["項目","採用中の開発条件"],[
        ["Mac Studio","M3 Ultra / CPU 28 / メモリ 256GiB"],
        ["モデル","MiniMax M3 IQ4_XS / 重み 213.91GiB"],
        ["推論","llama.cpp b11669 / KV q8_0 / 入力枠 65,536"],
        ["複数担当","同じモデルへ逐次入力。重みを担当数倍にしない。"],
        ["P4の実測","サーバーRSS最大約219.9GiB / 観測swap 0"],
    ],[185,695],y=170,row_h=47,size=17)
    banner(s,"複数担当の検証は可能。ただし、この構成から物理並列の高速化は主張しない。",size=17)

    s = slide("09 / 選定理由", "モデルの大きさより、必要な入力長で測定できること",
              "大型・非Flashという希望と、実際の容量・接続・実課題の結果を合わせた判断。",
              "出典 S9。未測定の候補を劣ると判断した表ではない。一般的な最強モデルの選定でもない。")
    table(s,["候補","確認結果・優先順位の理由"],[
        ["M3 IQ4_XS + q8 KV","64Kとツール往復が動作。P3/P4の共通モデルとして採用。"],
        ["同じIQ4 + f16 KV","64KでMetalメモリ不足。失敗記録を保ち別設定に分離。"],
        ["M3 Q3_K_L","動作済み。比較記録を保持。Q3対IQ4はKV条件も異なる。"],
        ["M3 Q4_K_M","重みだけで約243GiB。長い入力と作業領域の余裕が小さい。"],
        ["別系列・小型モデル","比較候補として残す。今はハーネス条件を先に固定する。"],
    ],[230,650],y=170,row_h=45,size=16)
    banner(s,"本実験のモデルは未確定。2課題の成績や量子化名だけで一般的な優位は決めない。",size=16.6)

    s = slide("10 / 実験の積み重ね", "実行基盤の検証から、構成差の観察へ進んだ",
              "条件が異なる段階を一つの成功率にまとめない。",
              "出典 S10・S2–S4。呼び出し数は実問題の当該試行のみ。校正・失敗した導入は別記録。")
    table(s,["段階","目的","実行規模","到達点"],[
        ["P0 / E0 / P1","接続・評価・単一基準","P1：2モデル×2課題","公開／独立評価を分離"],
        ["P2 Q3","大型モデルの実行適合","2課題 / 53呼出","独立評価0/2"],
        ["P2 IQ4/q8","容量と開発課題品質","2課題 / 58呼出","独立評価1/2"],
        ["P3","単一と固定2担当","2課題×2方式 / 105呼出","両方式で同じ成否"],
        ["P4","広い依存候補の単一観察","Ansible 1課題 / 38呼出","未解決・修正差分なし"],
    ],[135,255,230,260],y=174,row_h=45,size=16)
    banner(s,"ここまでの成果は、方法の改善率ではなく、比較の基盤と失敗の観測記録。",size=17)

    s = slide("11 / P3の設計", "モデル・ツール・総予算をそろえ、工程分担を比べた",
              "同じDjangoの開発2課題を、単一／固定2担当で各1回。",
              "出典 S2：P3固定計画・測定。両担当とも全作業ツリーを読取・変更できる。")
    card(s,40,176,430,234,"単一エージェント",
         "1つの履歴で調査・実装・検査\n外部ツールと全リポジトリを利用\n完了判定と費用を共通管理",TEAL,WHITE,20)
    card(s,490,176,430,234,"固定2担当",
         "実装役と検証役の別履歴\n交互に実行し、同じ作業ツリーを共有\n排他的な責任の移管は行わない",NAVY,WHITE,20)
    banner(s,"共通上限：30呼び出し / 300,000入力＋出力 / 3,600秒 / 同じM3 IQ4/q8",size=17)

    s = slide("12 / P3の結果①", "総トークンは近いが、全件が予算停止だった",
              "15380は両方式合格、15957は両方式未解決。各棒は1試行。",
              "出典 S2・P3_data.csv。バーは0起点。反復がないため誤差棒や有意差は示さない。")
    picture(s,"p3_tokens",y=162,h=278)
    banner(s,"少し少ない消費を「品質を保った費用削減」とは扱わない。完了宣言は全4件0回。",size=16.7)

    s = slide("13 / P3の結果②", "論理トークンが近くても、実時間は大きく違った",
              "単一履歴と交互の2履歴で、キャッシュの利用条件も違う。",
              "出典 S2・P3_data.csv。一つの物理スロットで逐次実行。キャッシュは入力の内数。")
    picture(s,"p3_time_cache",y=164,h=278)
    banner(s,"2担当が常に遅いとは言えない。物理構成とキャッシュを含む、この実行条件での観測。",size=16.5)

    s = slide("14 / P3の考察", "解けない原因を、分担や受け渡しのせいにしない",
              "成果物と操作を調べ、次の研究へ使える観測か判断した。",
              "出典 S2：P3_findings.md。局所修正の成功を大規模・相互依存作業の実証にしない。")
    table(s,["課題","単一","固定2担当"],[
        ["15380\n同時改名","機能修正 / 合格\n857バイトの差分","機能修正＋テスト / 合格\n2,678バイトの差分"],
        ["15957\nprefetchの制限","修正差分なし / 未解決\n公開既存検査は合格","再現テストのみ / 未解決\n追加検査に3エラー"],
    ],[185,347,348],y=177,row_h=77,size=18)
    text(s,40,427,880,63,"両方式で機能修正に至らない失敗はある。\nこの結果だけでは、更新責任を集める必要性を特定できない。",21)

    s = slide("15 / 主課題を選ぶ", "正解の変更箇所を使わず、公開要求から候補を選ぶ",
              "大きなリポジトリであることと、複数作業の依存が強いことは別。",
              "出典 S11：公開課題選定・Pro候補・基点コードの確認。すべて開発用の閲覧台帳に記録。")
    card(s,40,175,280,252,"最初の12候補",
         "6リポジトリ × 2件\n公開要求を先に固定抽出\n局所修正が中心だった\n主課題の採用は保留",TEAL,WHITE,18)
    card(s,340,175,280,252,"Proの追加12候補",
         "604候補から規則で抽出\n3候補の21ファイル確認\nメール復号・YAML等の\n関係を公開コードで検討",NAVY,WHITE,18)
    card(s,640,175,280,252,"Ansibleを先に導入",
         "YAML・信頼情報・vault\nの条件を扱う実行候補\n固定基点と評価器を確認\n正式な主課題採用は未定",AMBER,WARM,18)
    banner(s,"小課題を不自然に分割して、集約が必要な状況を作らない。")

    s = slide("16 / 評価器の確認", "未修正は落ち、参照修正は通ることを先に確かめた",
              "モデルの失敗と、評価基盤の失敗を区別するための正負対照。",
              "出典 S12・S3：PRO_ENV_05 / P4独立評価。参照修正・追加テストの内容は生成側へ渡さない。")
    table(s,["投入した成果物","要求を確認する4テスト","既存動作の21テスト"],[
        ["空の差分（負対照）","0合格 / 4不合格","21合格 / 0不合格"],
        ["参照修正（正対照）","4合格 / 0不合格","21合格 / 0不合格"],
        ["P4の凍結成果物","0合格 / 4不合格","21合格 / 0不合格"],
    ],[300,290,290],y=176,row_h=59,size=18)
    text(s,40,425,880,65,"導入時の3失敗と、終了コード1を基盤エラーにした誤判定も保存。\n残した出力から訂正し、元の結果は上書きしなかった。",19)

    s = slide("17 / P4の設計", "YAML処理の複数の条件を、単一方式でまず観察する",
              "Ansible 1開発課題・1試行。P3から課題と上限が変わるため、直接の手法比較にはしない。",
              "出典 S3・S4。下図は公開要求に登場する関係で、実証済みの因果グラフではない。")
    node(s,40,178,254,113,"YAMLの入口・出口","from_yaml / from_yaml_all\nto_yaml / to_nice_yaml")
    node(s,353,178,254,113,"保持すべき情報","信頼情報・由来情報\n文字列・コンテナ")
    node(s,666,178,254,113,"暗号化とテンプレート","vaultの出力条件\n未定義値等の扱い")
    arrow(s,294,233,353,233);arrow(s,607,233,666,233)
    box(s,40,327,880,102,NAVY)
    text(s,60,342,840,36,"上限 60呼び出し / 600,000トークン / 3,600秒",25,WHITE,True)
    text(s,60,389,840,30,"公開要求3項目をすべて入力。19ソースと条件を実行前に固定。",19,WHITE)
    banner(s,"情報が不足した設定にせず、公開要求を保ったまま挙動を測る。")

    s = slide("18 / P4の経過", "調査から再現確認へ進んだが、修正には届かなかった",
              "最初の再現確認より前に404,067トークンを使用。修正成果物は最後まで0バイト。",
              "出典 S3・S4・P4_timeline.csv。一時領域の再現スクリプトは操作記録に保存。")
    picture(s,"p4_timeline",y=166,h=276)
    banner(s,"読む作業を一律に無駄とは判定しない。調査から変更へ移る条件は、次の検証候補。",size=16.5)

    s = slide("19 / P4の結果", "入力の繰り返しが総トークンの大半を占めた",
              f'実行 {m4["wall_seconds"]:.2f}秒 / {m4["calls"]}呼び出し / {m4["known_total_tokens"]:,}総トークン',
              "出典 S3。キャッシュ対象559,572は入力583,040の内数。課金額や実計算量とは別の指標。")
    picture(s,"p4_composition",y=169,h=161)
    table(s,["入力","出力","最終成果物","独立評価"],[
        ["583,040","3,126","0バイト","未解決：要求0/4"],
    ],[220,220,220,220],y=342,row_h=45,size=18)
    banner(s,"公開既存131件の合格、再現スクリプトの終了0だけでは要求を満たしたとは言えない。",size=16.5)

    s = slide("20 / 解釈", "分かったことと、原因として未確認のこと",
              "失敗も費用へ含め、実装の問題と研究仮説を混ぜない。",
              "出典 S2–S4。内部推論文から原因を断定する分析は行っていない。")
    card(s,40,175,430,254,"観測できたこと",
         "同じモデルで両構成を測れる\n公開検査と独立評価が食い違う\nP4は予算停止で機能修正なし\n計測欠損・形式エラーはなかった",TEAL,WHITE,20)
    card(s,490,175,430,254,"これから切り分けること",
         "基準方式の調査・停止方針の影響\n本当に必要な作業間の調整\n情報整理だけで改善できる範囲\n実行単位変更の固有の追加価値",AMBER,WARM,20)
    banner(s,"単一の失敗を、複数担当や集約の必要性の証拠へ読み替えない。")

    s = slide("21 / 先行研究と新規性", "「動的に担当を変える」だけでは、既に研究がある",
              "本文と固定コードを照合中。完全再現と新規性の確定は未完了。",
              "出典 L1–L4・S13。各研究の原理の要約であり、同条件の性能比較ではない。")
    table(s,["近接研究","既に扱われていること","今回さらに検証したいこと"],[
        ["MaAS / ICML 2025","課題に応じた構成・費用配分","全工程の品質条件と費用"],
        ["TDAG / NN 2025","動的な分解・担当生成","進行した作業状態の移管"],
        ["Flow / ICLR 2025","実行中の作業・担当更新","共有・中央調整を超える効果"],
        ["Puppeteer / NeurIPS 2025","状態に応じた担当選択","移管の利益と費用を含む比較"],
    ],[246,298,336],y=171,row_h=52,size=16.2)
    banner(s,"狙うのは有効条件と機構の説明。再編・分岐実験・利益予測そのものを世界初としない。",size=16.2)

    s = slide("22 / 次の検証", "分担の観察 → 同一状態の対照 → 必要なら自動選択",
              "前段で現象が残らなければ、次の複雑な機能へ進まない。",
              "出典 S1・S5・S7。後続の具体的な試行条件は、開始前に別計画として固定する。")
    table(s,["順序","行うこと","進める条件"],[
        ["1","同条件の工程分担・強い基準の点検","観測可能な調整・状態不整合がある"],
        ["2","同一状態から継続／整理／調整／移管","復元と予算の比較が成立する"],
        ["3","単純規則と利益予測を比べる","局面により有効な対応が変わる"],
        ["4","未使用課題・別モデルで確認する","品質条件・主要指標・必要件数を固定"],
    ],[80,400,400],y=172,row_h=56,size=17)
    banner(s,"並行して決める：主課題、依存の分類、品質許容差、必要件数、最も近い比較実装。",size=16.7)

    s = slide("23 / 研究期限まで", "2027年夏の初回投稿を目標に、段階ごとに判断する",
              "12月は修論・成果物の完成期限。採録時期は査読に依存する。",
              "出典 S1・S5：研究の現方針を基にした予定。結果により手法と件数を見直す。")
    table(s,["時期","重点","残す成果物"],[
        ["2026年10–12月","主課題・基準方式・現象の確認","選定理由、条件、失敗分析"],
        ["2027年1–4月","同一状態の比較・機構の分析","分岐データ、効果と費用"],
        ["2027年5–6月","確認評価と論文の主張を固定","主要図表、限界、再現手順"],
        ["2027年7–8月","執筆・初回投稿","IEICE論文誌を主候補に原稿"],
        ["2027年9–12月","追加検証・査読対応・修論","コード、設定、最終発表"],
    ],[210,350,320],y=172,row_h=45,size=17)
    banner(s,"再編が効かない場合も記録する。ただし、否定結果だけで論文化できるとは保証しない。",size=16.2)

    s = slide("24 / 何を目指すか", "どの状態に、どの構成が必要かを説明できる研究へ",
              "到達目標は、平均スコアの上昇だけではない。",
              "研究コード・記録・Issue・PR・専用Project：sophiria1225/AI-")
    card(s,40,177,280,252,"学術的な成果",
         "情報整理で十分な条件\n中央調整が有効な条件\n移管が役立つ／害になる条件\n品質と費用の根拠",TEAL,WHITE,18)
    card(s,340,177,280,252,"技術的な成果",
         "状態を扱う共通ハーネス\n同じ途中状態の比較基盤\n費用を含む選択規則\n再実行できる記録と設定",NAVY,WHITE,18)
    card(s,640,177,280,252,"現在の課題",
         "強い基準でも残る現象\n近接研究との差分\n主課題と確認評価\n一般化できる範囲",AMBER,WARM,18)
    banner(s,"「誰に何を渡し、どこで判断・実行をまとめるか」を、実測に基づいて決める。",size=17)

    s = slide("付録 A / 正確な実測値", "P3の4試行を比較するためのデータ",
              "下記は開発観察。入力キャッシュは全入力の内数で、費用から差し引かない。",
              "出典 S2・materials/20261020/P3_data.csv。完全な集計はreports/に保存。")
    rows = [[r["task"].split("-")[-1]+(" 単一" if r["strategy"]=="single" else " 2担当"),
             str(r["calls"]),f'{r["input_tokens"]:,}',f'{r["output_tokens"]:,}',
             f'{r["total_tokens"]:,}',f'{r["wall_seconds"]:.2f}',
             "合格" if r["resolved"] else "未解決"] for r in p3]
    table(s,["課題・方式","呼出","入力","出力","合計","秒","評価"],
          rows,[173,60,143,106,143,143,112],y=178,row_h=54,size=16)
    banner(s,"全4試行が予算停止。合計105呼び出し・1,113,881トークン。独立な課題数は2。",size=16.5)

    s = slide("付録 B / 再現性", "固定したものと、原記録のたどり方",
              "公開可能な集計・コードと、実験機上に保持するデータを区別する。",
              "出典 S6・S14。下記は短縮表記。完全なSHA-256・コミットは設定とdata_sources.jsonへ。")
    table(s,["対象","固定版／記録"],[
        ["推論基盤","llama.cpp 620d2225… / mini-swe-agent 04d809ce…"],
        ["P3計画","configs/P3_development_plan_v01.json / ce33553f…"],
        ["P4計画","configs/P4_pro_single_plan_v01.json / 64701ea1…"],
        ["Proデータ・実行環境","HF 2d52cb3d… / V2 image sha256:2ee62346…"],
        ["公開するもの","集計・理由・設定・図表CSV・資料生成コード"],
        ["ローカルに保持","モデル重み・完全な履歴・独立評価の追加テスト"],
    ],[225,655],y=167,row_h=38,size=16)
    text(s,40,446,880,43,"GitHubの変更先はAI-のみ。Issueと専用Projectに状態を継続記録する。",19,TEAL,True)

    s = slide("付録 C / 記録へのリンク", "数値・図表・判断の出典",
              "資料の数値は記録済みの集計から生成。詳細は各リンクと発表者ノートへ。",
              "リンクはGitHub上の記録。資料作成時点の元データSHAはdata_sources.jsonに保存。")
    source_rows = [
        ("S1","研究の目的・評価の基準","docs/research_brief.md"),
        ("S2","P3比較の実測と考察","docs/P3_findings.md"),
        ("S3–S4","P4実測・公開操作の分析","docs/P4_findings.md"),
        ("S5–S7","作業ボード・実装・分岐計画","docs/task_board.md"),
        ("S8–S10","品質条件・モデル選定・以前の実測","docs/model_selection.md"),
        ("S11–S12","主課題選定と評価器の校正","docs/main_task_feasibility.md"),
        ("S13–S14","先行研究比較と固定計画","docs/related_work_matrix.md"),
    ]
    for i,(code,label,path) in enumerate(source_rows):
        y=174+i*42
        text(s,40,y,105,30,code,16,TEAL,True)
        text(s,155,y,750,30,label+"  ↗",18,NAVY,url=f"{REPO}/blob/main/{path}")
    s["notes"] = "\n".join(f"{c} {l}: {REPO}/blob/main/{p}" for c,l,p in source_rows)

    s = slide("付録 D / 近接研究の原典", "新規性の確認に使っている主な文献",
              "下記の正式掲載研究と著者実装を比較。方法全体の再現はまだ行っていない。",
              "本文・実装の確認範囲と未確認事項はdocs/related_work_matrix.mdに記録。")
    refs = [
        ("L1","MaAS: Multi-agent Architecture Search via Agentic Supernet","ICML 2025 / PMLR 267",
         "https://proceedings.mlr.press/v267/zhang25bi.html"),
        ("L2","TDAG: Dynamic Task Decomposition and Agent Generation","Neural Networks 185, 107200 (2025)",
         "https://doi.org/10.1016/j.neunet.2025.107200"),
        ("L3","Flow: Modularized Agentic Workflow Automation","ICLR 2025",
         "https://proceedings.iclr.cc/paper_files/paper/2025/file/ba84da6921f3040b74ee163aa7451f53-Paper-Conference.pdf"),
        ("L4","Multi-Agent Collaboration via Evolving Orchestration","NeurIPS 2025",
         "https://proceedings.neurips.cc/paper_files/paper/2025/hash/f1320d2e2842169c6fc89dcbd80e94d0-Abstract-Conference.html"),
    ]
    for i,(code,title,venue,url) in enumerate(refs):
        y=170+i*76
        text(s,40,y,45,32,code,17,TEAL,True)
        text(s,100,y,810,34,title+" ↗",19,NAVY,url=url)
        text(s,100,y+33,810,31,venue,16,MUTED)
    s["notes"] = "\n\n".join(f"{c}: {t}\n{v}\n{u}" for c,t,v,u in refs)
    for s in SLIDES:
        if not s.get("notes"):
            s["notes"] = "この資料は少数の開発観察の報告。グラフの元データ、条件差、未実証事項は末尾の出典と資料READMEを参照。"
    return SLIDES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT/"materials/20261020")
    parser.add_argument("--font", type=Path,
                        default=Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"))
    parser.add_argument("--font-name", default="Arial Unicode MS")
    args = parser.parse_args()
    if not args.font.exists():
        raise SystemExit("Use --font to specify a local CJK TrueType font; it is not distributed with the repo.")
    args.output.mkdir(parents=True, exist_ok=True)
    p3,p4 = generate(ROOT,args.output,args.font)
    deck = build(p3,p4)
    render(deck,args.output,args.font,args.font_name)
    versions = subprocess.check_output([__import__("sys").executable,"-m","pip","freeze"],text=True)
    (args.output/"requirements-build.lock.txt").write_text(versions)
    manifest = {"source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                "generator_sha256":{p:hashlib.sha256((ROOT/"scripts"/p).read_bytes()).hexdigest()
                                   for p in ("build_research_presentation.py","presentation_charts.py","presentation_renderer.py")},
                "font_sha256":hashlib.sha256(args.font.read_bytes()).hexdigest(),
                "page_count":len(deck),
                "outputs":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                           sorted(args.output.glob("AI_harness_research_20261020.*"))}}
    (args.output/"build_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    # A readable transcript is generated, not separately maintained prose.
    lines=["# AIハーネス研究 中間報告 2026-10-20","",
           "PDF/PPTXの文章版。図表はfigures/、正確な数値はCSVとdata_sources.jsonを参照。",""]
    for i,s in enumerate(deck,1):
        lines += [f"## {i:02d} {s['title']}",""]
        for e in s["elements"]:
            if e["kind"]=="text" and e["y"]>105 and e["y"]<502:
                lines += [e["text"].replace("\n","  \n"),""]
        lines += ["図表と出典は同ページのPDF/PPTXを参照。",""]
    (args.output/"transcript.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"pages":len(deck),"output":str(args.output),"layout_overflow":0}))


if __name__=="__main__":
    main()

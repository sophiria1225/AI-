# P141：既知Task 4だけを用いるobject-delta時点の診断仕様

これは採用判定を行わない、既知課題1件の事後的な機構診断である。P140の全4課題比較を置換せず、未見の保留12課題による確認実験も置換しない。P140の未知費用・失敗・固定gateを変更せず、過去cohortの条件を合算しない。本仕様の作成はモデル実行を許可・開始する操作ではない。

## 選定理由と固定対象

P140閉鎖後に、変更対象のobject promptとdeltaが実際に発動した唯一の既知課題Task 4を選んだ。候補EDOはdelta採用・配信へ到達したが、公式成功はfalse、最後のmodel usageはunknownだった。その結果を見た選定であり、無作為な課題抽出・確認的評価・独立反復とは呼ばない。長いwall上限で救済する比較ではなく、同じ有限上限の下で時点方式を限定比較する。

対象は`6104387_1`、原初期状態の出所は`P29_04_CODE`。新cohortでは**slot 1が元Task 4**を指す。課題・seedの追加、条件削減、成功するまでの反復は行わない。

| 実行順 | mode | 再要約時点 | 第二要約表現 |
|---|---|---|---|
| 1 | `threshold_recursive` | native入力閾値 | 再帰要約 |
| 2 | `threshold_delta_object` | native入力閾値 | 旧summary保持＋明示object delta |
| 3 | `exposure_delta_object` | 過去有料入力の累積Eと前focus費C | 旧summary保持＋明示object delta |

3条件ともmodel seed57、world seed42。新run IDで各1回のみ実施し、途中結果による条件・予算・順序の変更や自動retryをしない。初回focusと初期入力・tools、roleごとのseed進行は共通。最大2機会、fresh turn3、直近2turn保持、初回native入力閾値16,384、通常output cap4,096を維持する。object指定は第二delta focusに限り、hostによるfragment合成、parser、combined8,192文字・field合計32 items等の制限を変えない。初回summaryが採用されなければ、第二機会にdeltaを前提とした採用を偽装しない。

実行順は固定で無作為化しておらず、cache・順序・hostの影響は残る。logical cached inputは費用へ全計上する。新cohort内の記述的policy差であり、timing変更は以後のpayloadや軌跡も変えうる。TR→TDOにはTD対照がないため、object prompt単独の効果は識別しない。

## 有限予算と起動前条件

| 項目 | 各条件 | 3条件の上限 |
|---|---:|---:|
| model要求（actor＋focus） | 80 | 240 |
| logical入力＋出力tokens | 450,000 | 1,350,000 |
| 作業時間 | 1,800秒 | 条件ごとに同じ上限 |
| environment API要求 | 80 | 240 |
| 公式評価 | 1 | 3 |
| setup / cleanup / idle / evaluation | 120 / 180 / 60 / 180秒 | 各条件で同じ上限 |

server lease9,000秒、batch7,200秒、pipeline9,600秒。latest launchは2026-10-28 03:00 JST、モデルの絶対終了は05:30 JST、結果処理目標は06:30 JST。上限を収められない遅延は無断で短縮・延長せず扱う。最終起動は、P140完全閉鎖の固定証拠、所有process停止、別namespace、最終source/plan固定、同headのpush/PR CI成功、初期3＋focus3＋checkpoint後actor2の事前native計数等を別の起動経路で満たしてから行う。このdraftには未確定のheadやSHAを成功値として埋めない。

## 記述的な3比較

1. **TDO→EDO：object deltaを固定した時点比較。** 最初に観測されたtiming predicate差の直前までのprefixを比較し、同じ境界で実dispatchも異なることを要求する。「first actual」はこの保守的定義の略記にすぎず、最初のpredicate差でfocusが未送信ならactual=falseとして、後の有利な境界を探さない。後の第二focus時点やcutoffを同一にする条件は課さない。共通prefix、実dispatch差、両dispatchの既知性を別々に保存し、未送信・unknown・prefix不一致を消さない。
2. **TR→EDO：強い通常対照との全仕事比較。** 成否・既知費用・unknownを並記する。時点と表現がともに異なるため、一要因だけの因果効果と解釈しない。
3. **TR→TDO：同じ閾値での表現＋prompt bundle比較。** delta保持とobject指示をまとめた比較であり、両者を分離した効果ではない。既存strict/canonical representation prefix証拠を併記する。

strictとvalidated transport-ID canonical一致は別判定である。正規化は検証済みprotocol IDの対応だけで、本文・引数・観測・reasoning・費用・状態を任意に同一視しない。証拠が未取得・不正・欠測なら帰属を成立させない。同一seedだけで実prefix一致を仮定しない。

## 会計・失敗・判定

全3予定枠を、評価済み・未完了・未実施・監査エラーも含めて保存する。失敗、未知、非発動を除外しない。費用は全actor/focusのlogical入力＋出力で、cached inputを控除しない。採用されない既知有料focusも含む。native入力計数やoutput予約値を、未知の実terminal usageへ転記しない。未知usage後は停止し、無料retryはない。

対応する2行ともusage既知の場合だけ記述的token差を出す。共通成功が空ならその差はnull、欠測だけのmodeに0の測定費用を作らない。元の全条件完全性に対応する集計は全3使用量既知を要求する。成功数0と未評価を別に報告する。公式成功は独立の最終評価であり、actorの完了宣言やsummary採用ではない。

**`scientific_adoption_evaluated=false`、全comparison gateおよび`development_gate_met=false`を結果によらず固定する。** この診断が全成功でも、新方式採用、一般的非劣性、未知12課題での確認、独立再現、新規性、統計的相乗効果の証拠にはしない。次の判断材料にはできるが、P140の全4課題採用要件を緩める操作ではない。原稿本文はユーザーが執筆する。

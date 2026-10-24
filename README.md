# AIハーネス研究

必要な情報・処理と最終成果の品質を保ち、不要な取得・共有・モデル呼出し・実行・検証を減らす。制御・失敗・再取得を含む仕事全体の費用で評価する。

2026-10-24更新。**新提案の中核、一般的な品質維持、採録に足る新規性は未確立。** 25日までに不足確認と採否を絞り、29〜30日に原稿を整え、31日までのレター投稿完了を目指す。

## 現在の実行

| 対象 | 状態 | 判断 |
|---|---|---|
| P82：常時表示M／非表示H／後半表示L | 全24条件・426生成・24評価を終了、監査不一致０。使用量不明４件 | 全４採用基準未達。Mは3/4・2/4、H/Lは各3/4・3/4成功。Lの全仕事改善は示せなかった |
| P82の資料・原稿 | 配置の自動検査で停止した記録を保持し、別版の資料８頁と原稿４頁を全頁確認 | 狭い費用区間も前提不成立を保存。欠測を推定しない全件資源集計を別に公開 |
| P84：文章化ID差の次出力 | 固定６入力×３反復の初回実行中。初期６計数は一致 | P82全件レビュー後の別途判断で開始。元の自動停止と欠測を保持。生成コードは実行しない |

[P82全件結果](docs/P82_findings.md)／[最新の状態](docs/current_status.md)／[次の作業](docs/next_actions.md)／[引き継ぎ](RESUME.md)／[専用Project](https://github.com/users/sophiria1225/projects/1)。停止はユーザーの最新指示に従う。終了済みの実験を再試行しない。

Lは既知分だけでMより197,929論理token多い。一方、Mには第２反復の写真で失敗があり、安いことを同じ品質での改善とは扱わない。L/Hの成功６組はLの通知開始前に終了し、全要求・公開出力列が一致した。[欠測を推定しない資源別集計](materials/20261024_p82_observed_resources/README.md)。

## 閉じた結果から分かっていること

- P80/P81の既知４課題×３反復では、M/Hとも各反復3/4成功。採用基準は全反復未達。書出しは全６条件で未達だった。[全結果](docs/P81_findings.md)。
- Hの論理tokenは条件付きで合計約0.79〜1.02％少ないが、cacheを除く入力は既知分だけで7.09％以上、出力は39.30％以上多く、作業時間は実測32.26％長い。不明２生成を保持し、論理tokenをGPU計算量や時間と同一視しない。[全件集計と図](materials/20261024_p81_resource_accounting/README.md)。
- 文章化された通信参照の露出は全429保存要求中20要求、Hの書出し３反復だけだった。露出のないMの書出しも未達であり、失敗全体の原因とはいえない。[先行研究と露出範囲](docs/identifier_prior_and_exposure_20261024.md)。
- P83の再構成では、文章化前の参照統一で該当２入力のtoken列が一致した。次出力・課題成功・全費用への効果は別途未検証。[P83](docs/P83_findings.md)／[モデル不要の最小再現例](materials/20261024_protocol_minimal_reproducer/README.md)。
- 終了済み429生成の引数不正３応答は全て4,096出力上限に達していた。P83の６保存入力には同じ遅延文法設定があり、文法制約なしの基準とは扱わない。追加生成は０。[全件の構文診断](materials/20261024_tool_grammar_boundary/README.md)。

[費用評価の追加先行研究](docs/cost_proxy_prior_review_20261024.md)を確認したため、tokenと他の費用の方向差、失敗を残す評価自体は新規性に含めない。

[外部３ライブラリの参照ID経路](materials/20261024_framework_reference_review/README.md)を固定版９ファイルで確認した。本文への転記、専用欄での保持、添付の出所タグという違いがある。外部実装の生成・品質を再現した結果ではなく、修正の適用範囲を絞る資料である。

## 原稿と資料

| 成果物 | 内容と状態 |
|---|---|
| [P80/P81の資源別統合稿](papers/202610_letter/resource_prior_review/README.md) | 全24条件・429生成、条件付き区間、資源別の方向差。近接研究３件を加え、文献14件・本文４頁＋英文１頁を確認済み |
| [P82実結果稿](papers/202610_letter/late_time_control/RESULTS.md) | 全24条件・全４採否・全８表示開始位置を収録。本文３頁＋英文１頁を全頁確認 |
| [P82の全件資料](materials/20261024_p82_results_final/README.md) | 題名だけの表紙＋全７内容頁。全24条件・426生成・不明４件を保持 |
| [全件終了後の統合稿の準備](papers/202610_letter/closed_control_integration/README.md) | P82全24条件とP84全18予定枠を区別して収録する処理。実数表は未生成。合成値で本文３頁＋英文１頁を確認 |
| [参照統一と文章化の１頁図](materials/20261024_protocol_order_figure/README.md) | 処理の順序とP83で確認した範囲を図解。入力一致を成果品質へ読み替えない |
| [教授用の題名・あらまし](materials/20261023_professor_brief/README.md) | 合意した日英題名と456字あらましを保存。著者・所属・順序は未確定 |
| [P81の７枚資料](materials/20261024_p81_results/README.md) | 成否・全費用・経路の照合を全件掲載 |
| [費用指標の１頁図](materials/20261024_p81_resource_accounting/README.md) | 論理token、cacheを除く入力、出力、時間の方向差 |
| [14文献の資源別稿の組版予行](materials/20261024_prior_review_mirror_preview/README.md) | 最新の閉じた稿もミラーのletter形式で本文４頁＋英文１頁を確認。現行公式ファイルとの同一性は未確認 |

投稿先は電子情報通信学会論文誌Dのレター（研究速報）を想定する。現行稿は公式クラス未使用・著者未設定で、投稿可能な最終版ではない。教授への送信・実投稿は行っていない。

[公開ファイルだけでの再計算](materials/20261024_public_resource_reproduction/README.md)では、全24条件・32区分のCSVが一致した。元のモデル実験の再実行とは区別する。

## 実装と記録

[表示前の参照統一](scripts/protocol_stable_history.py)、[後半の時間表示](scripts/late_time_observation.py)、[P82の固定実行系](scripts/run_late_clock_pipeline.py)、[P84の固定計画](docs/experiments/P84_fallback_output.md)、[条件付き接続](docs/P84_continuation_decision_20261024.md)、[作業ボード](docs/task_board.md)。半分閾値、参照正規化、記録整備をそれ自体で新規手法とはしない。

[研究目的](docs/research_objective_20261022.md)／[金曜時点の判断表](docs/letter_friday_decisions_20261022.md)／[アカウント引き継ぎ](docs/handoff_20261022_account_switch.md)。過去の詳細な経過は[更新前READMEの固定版](https://github.com/sophiria1225/AI-/blob/6e38556bcff00b2cfb509da6a645e736f5fcce23/README.md)に保存されている。

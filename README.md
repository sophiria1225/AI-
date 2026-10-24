# AIハーネス研究

必要な情報・処理と最終成果の品質を保ち、不要な取得・共有・モデル呼出し・実行・検証を減らす。制御・失敗・再取得を含む仕事全体の費用で評価する。

2026-10-24更新。**新提案の中核、一般的な品質維持、採録に足る新規性は未確立。** 25日までに不足確認と採否を絞り、29〜30日に原稿を整え、31日までのレター投稿完了を目指す。

## 現在の実行

[P87：通常の推論予算対照](docs/P87_findings.md)は４件目が480秒上限で停止した。３件既知・１件使用量不明・４件未実行、既知76,318論理token、監査不一致０。途中切れ文脈の観測１対では半分指定でコード提出が完成したが、固定した２文脈×２反復の改善条件は判定不能。課題実行・品質評価は０で、新手法や全仕事削減の証明ではない。所有推論器停止・両PID不在済み。[全８枠と全５頁の資料](materials/20261024_p87_results/README.md)。

[P88全仕事比較](materials/20261024_p88_preparation/README.md)は12:30 JSTに開始した。既知４課題×通常の上限なし／固定2,048、各１回の新しい８条件。固定headの両CI/jobと初期８計数の一致を確認済み。最大640生成・3,600,000論理token予約、推論器21,600秒。途中の成否・出力は比較せず、終了後の監査へ進む。[全８条件の報告処理](materials/20261024_p88_reporting_preparation/README.md)も全1,292検査と合成７頁の全頁確認を終えた。実結果は未確定。 [日曜の主張判断](docs/weekend_decision_20261024.md)と[別稿反映の準備](materials/20261024_p88_manuscript_preparation/README.md)も保存した。

| 対象 | 状態 | 判断 |
|---|---|---|
| P82：常時表示M／非表示H／後半表示L | 全24条件・426生成・24評価を終了、監査不一致０。使用量不明４件 | 全４採用基準未達。Mは3/4・2/4、H/Lは各3/4・3/4成功。Lの全仕事改善は示せなかった |
| P82の資料・原稿 | 配置の自動検査で停止した記録を保持し、別版の資料８頁と原稿４頁を全頁確認 | 狭い費用区間も前提不成立を保存。欠測を推定しない全件資源集計を別に公開 |
| P84：文章化ID差の次出力 | 全18生成、422,475論理token、不明０、監査不一致０。推論器停止済み | 元ID一対A/Bは公開出力一致０/９対、統一入力C/Dとnative参照対照A/Nは各９/９対。１保存文脈の局所差を確認 |
| P82/P84統合稿 | 実結果の本文４頁＋英文１頁、ミラー予行は本文３頁＋英文１頁を全頁確認 | 後半通知の不採用と局所出力差を併記。新手法や一般品質維持は未確立 |

[P82全件結果](docs/P82_findings.md)／[P84全件結果](docs/P84_findings.md)／[最新の状態](docs/current_status.md)／[次の作業](docs/next_actions.md)／[引き継ぎ](RESUME.md)／[専用Project](https://github.com/users/sophiria1225/projects/1)。停止はユーザーの最新指示に従う。終了済みの実験を再試行しない。

Lは既知分だけでMより197,929論理token多い。一方、Mには第２反復の写真で失敗があり、安いことを同じ品質での改善とは扱わない。L/Hの成功６組はLの通知開始前に終了し、全要求・公開出力列が一致した。[欠測を推定しない資源別集計](materials/20261024_p82_observed_resources/README.md)。

## 閉じた結果から分かっていること

- P80/P81の既知４課題×３反復では、M/Hとも各反復3/4成功。採用基準は全反復未達。書出しは全６条件で未達だった。[全結果](docs/P81_findings.md)。
- Hの論理tokenは条件付きで合計約0.79〜1.02％少ないが、cacheを除く入力は既知分だけで7.09％以上、出力は39.30％以上多く、作業時間は実測32.26％長い。不明２生成を保持し、論理tokenをGPU計算量や時間と同一視しない。[全件集計と図](materials/20261024_p81_resource_accounting/README.md)。
- 文章化された通信参照の露出は全429保存要求中20要求、Hの書出し３反復だけだった。露出のないMの書出しも未達であり、失敗全体の原因とはいえない。[先行研究と露出範囲](docs/identifier_prior_and_exposure_20261024.md)。
- P83で文章化前の参照統一により該当２入力のtoken列が一致し、P84では統一後の次出力も一致、元ID一対の次出力は不一致となった。課題成功・全費用への改善は示していない。[P83](docs/P83_findings.md)／[P84](docs/P84_findings.md)／[モデル不要の最小再現例](materials/20261024_protocol_minimal_reproducer/README.md)。
- 終了済み429生成の引数不正３応答は全て4,096出力上限に達していた。P83の６保存入力には同じ遅延文法設定があり、文法制約なしの基準とは扱わない。追加生成は０。[全件の構文診断](materials/20261024_tool_grammar_boundary/README.md)。
- [終了済みHの20条件・全24群間比較](materials/20261024_closed_reference_cohorts/README.md)で、P83の統一入力C/DがP82のCSV実行にも両反復の14生成目で使われたことを確認した。その２条件は両方未達であり、入力整合だけから品質回復を主張しない。

[費用評価の追加先行研究](docs/cost_proxy_prior_review_20261024.md)を確認したため、tokenと他の費用の方向差、失敗を残す評価自体は新規性に含めない。

[外部３ライブラリの参照ID経路](materials/20261024_framework_reference_review/README.md)を固定版９ファイルで確認した。本文への転記、専用欄での保持、添付の出所タグという違いがある。外部実装の生成・品質を再現した結果ではなく、修正の適用範囲を絞る資料である。

[途中切れコードの全件点検](materials/20261024_truncated_code_prefix_scope/README.md)では、全48条件855生成の引数不正７件が同じ１コードだった。1,883文字・22文の前半は構文検査を通るが、先頭に認証処理があり、必須引数も未完。後続の全52枠で22文のAST一致は１件に限られた。再利用候補の存在と、安全な実行・品質改善・費用削減は区別し、追加生成や部分実行には進めていない。全1247検査を通過した。

## 原稿と資料

| 成果物 | 内容と状態 |
|---|---|
| [P82/P84の実結果統合稿](papers/202610_letter/closed_results_final/README.md) | 全24条件・全18生成・観測資源・群間照合を収録。本文４頁＋英文１頁、14文献を全頁確認 |
| [実結果稿のミラー組版予行](materials/20261024_closed_results_mirror_preview/README.md) | 本文３頁＋英文１頁を全頁確認。現行公式配布物との同一性は未確認 |
| [P84の５頁資料](materials/20261024_p84_results/README.md) | 全18枠・全15入力間比較・入力内比較・全費用を掲載 |
| [P80/P81の資源別統合稿](papers/202610_letter/resource_prior_review/README.md) | 全24条件・429生成、条件付き区間、資源別の方向差。近接研究３件を加え、文献14件・本文４頁＋英文１頁を確認済み |
| [P82実結果稿](papers/202610_letter/late_time_control/RESULTS.md) | 全24条件・全４採否・全８表示開始位置を収録。本文３頁＋英文１頁を全頁確認 |
| [P82の全件資料](materials/20261024_p82_results_final/README.md) | 題名だけの表紙＋全７内容頁。全24条件・426生成・不明４件を保持 |
| [全件終了後の統合処理の準備記録](papers/202610_letter/closed_control_integration/README.md) | 準備時点の説明は保持し、終了後の実数表を生成済み。PDFは最終派生版で確認 |
| [観測資源と終了判定の統合準備記録](materials/20261024_observed_control_preparation/README.md) | 準備処理から実結果の要旨・結論を生成済み。元の準備記録と中間稿を保持 |
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

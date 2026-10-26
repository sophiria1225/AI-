# P133: 両方式の費用は同じ、要約拒否は0回

P133 は既知 CSV 1課題、事前固定 seeds 57/157、通常の rolling_separate と empirical_payback の全4条件を実行した。両方式とも seed 57 で成功、seed 157 で API80 上限に達して失敗した。各方式の全仕事 logical input+output は **434,623 tokens**、差は **0**。新しい要約拒否規則は一度も発動せず、固定 development gate は **false** だった。

| seed | 方式 | 公式成功 | logical tokens | model呼出し | 実API | paid focus | 実拒否 |
|---|---|---|---:|---:|---:|---:|---:|
| 57 | rolling_separate | 成功 | 332,588 | 31 | 76 | 2 | 0 |
| 57 | empirical_payback | 成功 | 332,588 | 31 | 76 | 2 | 0 |
| 157 | rolling_separate | 失敗 | 102,035 | 10 | 80 | 0 | 0 |
| 157 | empirical_payback | 失敗 | 102,035 | 10 | 80 | 0 | 0 |

全4条件の費用は869,246 tokens、82 model呼出し、312実API、4評価。unknown usage、元producer監査エラー、payback契約失敗は0。各方式1/2成功で、seedごとの成功損失は0だった。共通成功は1 task-seed pair、費用差0、共通成功上の実拒否0。失敗を安くした削減、片seedだけの採用、unknownをゼロにした集計は行わない。[全4条件](../../materials/20261027_p133_results_recovery_v01/conditions.csv)／[集計](../../materials/20261027_p133_results_recovery_v01/summary.json)／[会計と解釈](../../materials/20261027_p133_results_recovery_v01/INTERPRETATION.md)。

[全4条件の図・公開再描画](../../materials/20261027_p133_results_recovery_v01/figures/README.md)。

## 比較で変えたもの

P123 の通常interface、guide、full receipts、API80、別呼出し反復要約を共通にした。初回focusは通常通り許可し、2回目以降だけ過去の採用済み入力短縮量、既払いfocus費用、観測済みactor/focus時間、残call/timeから購入を予測した。通常側では同じ予測をshadow記録しても送信を変えない。今回はshadow拒否も0だった。

seed 57 は各方式ともactor 291,513＋focus 41,075 tokens。seed 157 は各方式actor 102,035 tokensでfocus0だった。したがって本比較は規則が有効に拒否した場合の品質・費用を示していない。seed 57 の通常条件がP123の既報332,588 tokensと同じであることは記録の整合として報告するが、旧結果を新反復へプールせず、軌跡・状態・因果の同値証明とも扱わない。

固定headは `66d9eb71a1e6b8ee10b377be3bf52dca82d06cca`、plan SHAは `357c59a73ed9637e9171d6729f8f4210533fef90d598ec667fa1d7154d09d986`、元source1,459件。各80共有model calls、450,000 logical tokens、1,800作業秒、80 API、server lease14,400秒を固定した。実行開始snapshot189台帳/2,290束縛と後続globalを分ける。[固定仕様](P133_whole_task_checkpoint_payback.md)。

## 集計障害と別回収

2026-10-27 07:50 JSTに全4条件・所有serverを終了し、元の記録監査とserver集計はexit0だった。しかしreportはexit1で停止した。旧path検査が、元planにhash固定されていたmaterials6件とpapers1件を許可していなかったためである。元collector、独立review、図は未起動のまま、各待機処理の失敗記録を保持した。実験失敗や未知usageと、このreport実装不備を混同しない。

別source commit `309e2eb7d6be27dde63d97912d9bfb690e8da7db` のdata-only回収で、この7つの正確なpathと元hashだけを追加検証した。旧pure集計・採否関数を使い、全1,459元source、元run/prep、旧audit/sessionのbytes、原report失敗を保った。別ディレクトリ `20261027_p133_results_recovery_v01` へ1回だけ生成し、追加model/API/evaluator/tokenizer呼出しは0。元のcollector成功markerを作っていない。[原失敗](../../reports/P133_report_once_end.json)／[回収入力](../../reports/P133_reporting_recovery_inputs_v01.json)／[公開安全な完了証拠](../../reports/P133_reporting_recovery_v01_public_completion.json)／[回収manifest](../../materials/20261027_p133_results_recovery_v01/build_manifest.json)。

## 閉鎖後の検算

別lineageの独立reviewは16,788項目に合格し、全4枠・全役割費用・API dispatch・予測算術・unknown・189開始台帳・回収sourceを照合した。実験の採用gateはfalseのままである。native履歴再構成は固定producer監査に依存し、clockは保存されたhost観測の整合を検査する。actor、生成code、producer auditor、model/API/evaluator/tokenizerを再実行せず、独立評価本文も読んでいない。[公開安全な独立検算](../../reports/P133_closed_independent_audit_20261027_recovery_v01.json)。 [回収reviewerの事後source確認](../../reports/P133_recovery_reviewer_source_review_20261027.json)は計算関数が元版とAST一致することを確認し、事前承認とは記録しない。[図の独立確認](../../reports/P133_recovered_figures_peer_review_20261027.json)は公開算術と2PNGの可読性を確認した。

## 主張範囲

品質を維持した全仕事token削減は今回確認できなかった。過去費用に基づく予測は償却や期限内完了の保証ではなく、普通のcontroller改善の開発比較である。規則の一般的有効性・新規性を確立していない。異なるseedを追加して正結果を探索したり、通常対照を弱くしたりせず、全件・失敗・機構未発動を残す。

P134はこのreport障害により待機queueが実験を起動しないまま失敗した。元P134 source/計画/失敗を保持し、同じ6科学条件を別のP135名前空間で再固定した。[P135仕様](P135_whole_task_observed_obligations.md)と[現在の運用状態](../current_status.md)を参照。これはP133の科学的成否による条件選別ではない。原稿本文はユーザーが執筆する。

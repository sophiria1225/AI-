# 閉鎖結果一覧 v02 — P135/P136の追補

引継ぎ後の指定9cohort・全68予定条件、63評価を参照する一覧。元の7cohort・56行を保持し、正規公開auditにあるP135/P136の12行だけを追加した。68は独立標本数ではない。同じ課題・seedの反復やsource差があり、phase横断の合計を方式効果として比較しない。原稿本文ではない。

[9cohortの結果と主張可能範囲](../../docs/closed_results_index_20261027_v02.md)／[全68条件CSV](conditions_68.csv)／[追加6方式CSV](added_arms.csv)／[追加12比較CSV](added_comparisons.csv)／[公開summary](publication_summary.json)／[公開manifest](publication_manifest.json)。既存7cohortの[方式別](../20261027_closed_results_index/arms.csv)・[seed別](../20261027_closed_results_index/arm_seeds.csv)・[比較](../20261027_closed_results_index/comparisons.csv)は同じ元資料を参照する。

## 追加分

| Phase・方式 | 予定／評価／成功 | 既知token小計 | 記録済unknown呼出し | usage件数欠測条件 | 厳密総費用 |
|---|---:|---:|---:|---:|---:|
| P135 raw | 2／2／1 | 434,623 | 0 | 0 | 434,623 |
| P135 counts | 2／2／0 | 274,986 | 1 | 0 | null |
| P135 fields | 2／2／0 | 302,737 | 1 | 0 | null |
| P136 raw | 2／1／1 | 332,588 | 0 | 1 | null |
| P136 IDs | 2／0／0 | 未認証（報告0条件） | 0記録 | 2 | null |
| P136 fields | 2／0／0 | 未測定（報告0条件） | 0記録 | 2 | null |

P135は主比較共通成功0、rawへの成功喪失1、全体費用差と共通成功差はnull、gate false。自動entity行は0。seed57の主2方式は通知前にAPI上限へ到達し、seed157は通知時のunknownにより詳細が非開示だった。この0から義務なしやfield不要とは言えない。P136は評価1・worker未完1・未実施4で比較不能、gate false。途中workerの別診断223,145 tokensはこの認証済み表へ加算していない。

CSV空欄はnull（unknown、欠測、該当計測なし）で、ゼロへ置換しない。P135の未計測field行欄もnullを保持する。全68行の記録済unknownは8呼出し、usage件数欠測は別の5条件。P136のunknown記録0は未知費用がない意味ではない。`accounted_conditions=0`の既知小計0は空の報告小計であり、実行費用0ではない。

全phase横断の既知小計12,912,065 tokensは会計索引上の足し算だけで、厳密総費用はnull。独立標本、手法改善率、成功保持の効果推定へ使わない。共通成功と品質損失・改善・双方失敗は同一phase内だけで分ける。

## 時点と原資料

P137は[固定された開始記録](../../docs/experiments/P137_execution_start_20261027.md)へのリンクと[予定4・未収録placeholder](P137_placeholder.csv)のみ。本一覧の68行へ含めず、現在の稼働状況・成否・費用を表さない。実P137成果・usage・payloadは読んでいない。

P124/P126の[保存再生](../20261027_closed_results_index/replays.csv)、P130/P131/P134の[未開始運用失敗](../20261027_closed_results_index/operational_attempts.csv)も別扱いのまま保持する。旧運用表のP135開始placeholderは旧版時点の記録であり、本v02の閉鎖6行と重複計数しない。P133の元report失敗と別data-only回収も変更しない。

`summary.json`、`source_manifest.json`、`PREPARATION.md`と4 CSVは独立検算済みの準備資料を同byteコピーした。これらのprivate preparationというstatusや「PR0」は**準備時点の記録**で、公開状態は`publication_summary.json`へ別記する。数値は変更していない。元manifestは準備資料6件を束縛し、`publication_manifest.json`はこの公開パッケージの追加入口・公開summaryと依存を束縛する。[準備資料の独立検算2,437項目](../../reports/closed_results_index_v02_preparation_review_20261027.json)は元producer監査の再実行ではない。

旧v01、原cohort資料、保存code、監査・モデル・API・評価器・tokenizerを編集・再実行せず、未見12シナリオも閲覧していない。

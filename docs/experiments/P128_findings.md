# P128: receipt disclosure の全16条件を閉鎖

2026-10-26 22:20 JSTまでに全16条件の評価・所有server停止・回収・独立監査・図生成を完了した。full/discloseはどちらも6/8成功だが、seed57で成功損失1、seed157で成功改善1がある。unknown usageは各方式1呼出し、合計2。全仕事費用の厳密な全体差は不明で、固定development gateは **false**。成功件数の合計一致を品質維持とは扱わない。

| Seed | Full 成功 | Disclose 成功 | Full logical tokens | Disclose logical tokens | unknown calls (F/D) | seed判定 |
|---|---:|---:|---:|---:|---:|---|
| 57 | 3/4 | 2/4 | 871,107 known + unknown | 775,434 known + unknown | 1/1 | false |
| 157 | 3/4 | 4/4 | 849,469 | 833,441 | 0/0 | true |
| 全体 | 6/8 | 6/8 | 1,720,576 known + unknown | 1,608,875 known + unknown | 1/1 | false |

全16枠のうち未実施・未評価は0、監査エラー0、receipt/shared-runtime契約停止0。seed57のPhoto/discloseとCSV/fullはmodel呼出し中の作業時間切れで、それぞれusage1件が不明。CSV/disclose seed57とCSV/full seed157はAPI上限で失敗した。既知小計の差を総token削減として報告しない。

## 同じ成功を達成した範囲と品質改善を分ける

| 範囲 | 共通成功対 | Full tokens | Disclose tokens | 差 (D−F) |
|---|---:|---:|---:|---:|
| seed57 | 2 | 404,335 | 345,401 | −58,934 |
| seed157 | 3 | 674,162 | 591,255 | −82,907 |
| 記述的合計 | 5 | 1,078,497 | 936,656 | −141,841 |

この共通成功部分集合の費用は全件既知なので厳密に集計できる。一方、事前gateの`paired_successful_token_difference`は全cohortの費用既知を要求する定義のため、seed57と全体ではnullのまま保持する。部分集合の減少を使って、未知費用や成功脱落を含む全体gateを上書きしない。

seed157の全課題費用差は−16,028 token。内訳は共通3成功の−82,907と、CSVの失敗→成功に伴う+66,879である。CSVの改善は品質改善として残し、同じ成功を安く達成した対として数えない。seed57ではPhotoの成功を失った。2seedは同じ既知4課題の反復であり、独立8課題や一般的非劣性試験ではない。

## 機構と費用

両方式に同じguide、rolling separate、full-archive参照、通常complete cache、explicit joined fieldsを与え、自動region変換は無効。discloseの最終表示可能turnは115、実dispatch入力に一度以上含まれた固有disclosed turnは109、うち共通成功上は65。未再入力の最終turnを実利用へ加算しない。`read_span` actionは両方式0で、paid expansion経路の有効性をこの試行では示していない。

実APIはfull511/disclose541、通常complete-cache hitは217/60、explicit field要求は61/170。これらは別機構の回数でありtoken削減へ換算しない。表示から除去したreceipt UTF-8 bytesは17,158で、net logical token savingsではない。全役割のinput+output、summary、失敗、notice、回復を費用へ含め、cached inputは差し引かない。

## 検証と限界

固定head `0c29b754b23c8ca97ead6e9319661395b6c603a9`、plan SHA `8b061a77f3e778716e0a846ea3be46e05ec6012aecd826c44b8c9b84bf006d00`。独立閉鎖監査109,295 checks PASS、readonly図loaderは1,171 public sourcesと全16枠を照合した。PASSは原記録・会計の整合確認であり方式採用ではない。formatterを固定実装と共有し、rolling request再構成には固定producer auditorを用いる限界を保持する。保存生成codeやevaluator本文を再実行・意味評価していない。

図v01と元collector資料は同bytesで保持する。v01総費用図のunknown注記には一部重なりがあるため、注記位置だけを変更したv02へ分離済み。全16行dataはv01/v02で同bytes。原cohort、元監査、元図は上書きしない。

通常receipt disclosureの効率校正であり、新規技術・一般品質維持は未成立。片seedの好結果から追加seedや条件を選ばない。P128閉鎖後、既に固定済みのP129は22:20 JSTに元queueから開始した。P130予約も維持し、P128の成否によって後続条件を選び直していない。原稿はユーザーが執筆する。

[全16条件](../../materials/20261026_p128_results/conditions.csv)／[元集計](../../materials/20261026_p128_results/summary.json)／[図](../../materials/20261026_p128_results/figures/README.md)／[独立監査の公開集約](../../reports/P128_closed_independent_audit_20261026.json)／[元監査](../../reports/P128_comparison.json)／[比較仕様](P128_whole_task_receipt_disclosure.md)。

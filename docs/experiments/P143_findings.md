# P143：既知4課題における早期閾値の coverage comparison（閉鎖後 draft）

P142の非発動を見た後に選んだ開発比較である。TR/TDO共通の初回・反復閾値8,192、最大2機会、作業1,200秒、既使用seed157、既知4課題×2方式の全8予定枠を保持する。過去結果と合算せず、予約12課題の確認を置換しない。

以下は固定監査・summaryの値の転記である。known IOは既知の全actor/focus入力＋出力の小計で、unknownがあれば全費用は確定しない。cached inputは入力の内数として控除しない。欠測はnull、未評価は失敗に変換しない。

|課題slot|方式|記録状態|公式成功|known IO|unknown calls|API|要約採用|known object focus|known delta actor|
|---|---|---|---|---:|---:|---:|---:|---:|---:|
|1|TR|evaluated|true|200016|0|104|2|0|0|
|1|TDO|evaluated|false|149194|1|98|1|1|0|
|2|TDO|evaluated|true|218061|0|24|2|1|13|
|2|TR|evaluated|true|182483|0|25|2|0|0|
|3|TR|evaluated|true|68923|0|11|1|0|0|
|3|TDO|evaluated|true|68923|0|11|1|0|0|
|4|TDO|evaluated|false|110147|0|80|2|1|6|
|4|TR|evaluated|false|194187|0|80|2|0|0|

## 固定判定

- `evaluated_conditions`: `8`
- `success_counts`: `{"threshold_delta_object":2,"threshold_recursive":3}`
- `known_token_subtotals_by_mode`: `{"threshold_delta_object":546325,"threshold_recursive":645609}`
- `total_tokens_by_mode`: `{"threshold_delta_object":null,"threshold_recursive":null}`
- `recorded_unknown_usage_calls`: `1`
- `usage_count_missing_conditions`: `0`
- `development_gate_met`: `false`
- `scientific_adoption_evaluated`: `false`
- `all_task_token_difference`: `null`
- `common_success_token_difference`: `null`
- `common_success_tasks`: `["3c13f5a_1","60d0b5b_1"]`
- `success_loss_tasks`: `["34d9492_1"]`
- `changed_intervention_on_common_success`: `true`
- `all_activated_canonical_prefixes_match`: `true`
- `observed_utility_criteria_met`: `false`
- `comparison_gate_met`: `false`

|課題slot|TDO−TR tokens|両方成功|strict prefix|canonical prefix|実介入|
|---|---:|---|---|---|---|
|1|null|false|false|true|false|
|2|35578|true|false|true|true|
|3|0|true|null|null|false|
|4|-84040|false|false|true|true|

## 解釈範囲

低いknown小計を費用削減と解釈しない。nullの全仕事差・共通成功差を0へ補完しない。空の共通成功群や作動例のないprefix判定は実効果の証拠ではない。検算PASSと効用gateを区別する。
TR/TDOは同じ閾値の保持＋object出力指示＋ホスト結合bundle比較であり、要素単独の効果ではない。strictとtransport-ID canonicalの比較を分離し、native計数・canonical導出・公式成功は元監査に依存する。
閾値と作業予算をP142から同時に変更したため、相間差を閾値の因果効果にしない。既知課題・既使用seed・事後選択の開発比較であり、一般化・新規性・独立追試・統計的非劣性・全12確認の完了を確立しない。
このdraftは自動転記であり、最終の科学的解釈と公開はrootの閉鎖後レビューに従う。元producer・auditor・checker・renderer・モデル・API・評価・tokenizerの再実行は行わない。

[元監査](../../reports/P143_comparison.json) / [全8条件](../../materials/20261028_p143_results/conditions.csv) / [全4対](../../materials/20261028_p143_results/pairs.csv) / [summary](../../materials/20261028_p143_results/summary.json) / [公開検算射影](../../reports/P143_closed_metadata_review_public_20261028.json) / [出所](../../reports/P143_results_provenance_20261028.json)

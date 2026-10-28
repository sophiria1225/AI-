# P142：共通閾値での再帰要約とobject差分保持の既知4課題比較

P142は既知4課題×TR/TDOの全8条件を固定model seed157で各1回実行した開発比較である。**全8条件の評価と使用量が揃い、TR/TDOは各3/4成功、全仕事費用はそれぞれ572,405 logical input＋output tokensで完全に同値だった。第2object focus、差分採用、差分を含むactor入力は全課題で0であり、今回の比較は差分保持の処置差に到達しなかった。** 成功喪失は0だが、正の費用削減も機構の実介入も確認されず、固定効用条件とdevelopment gateはいずれもfalseである。

## 全8条件

全actor/focusの入力＋出力を数え、cached inputを控除しない。未知使用量0、費用欠測0、未評価0。数値の同値は公開scalarの同値であり、全メッセージ本文・意味・内部状態の同一性を主張しない。

|課題|方式|公式評価|入力|出力|全費用|不明呼出し|モデル要求|環境API|要約採用|差分付き既知actor|
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|写真操作|TR|成功|179,228|8,251|187,479|0|20|105|1|0|
|写真操作|TDO|成功|179,228|8,251|187,479|0|20|105|1|0|
|精算|TDO|成功|215,106|3,919|219,025|0|22|23|1|0|
|精算|TR|成功|215,106|3,919|219,025|0|22|23|1|0|
|返金|TR|成功|62,361|1,505|63,866|0|10|11|0|0|
|返金|TDO|成功|62,361|1,505|63,866|0|10|11|0|0|
|CSV処理|TDO|失敗|98,248|3,787|102,035|0|10|80|0|0|
|CSV処理|TR|失敗|98,248|3,787|102,035|0|10|80|0|0|

合計124モデル要求（actor120、focus4）、438環境API要求、8評価。actorの入力1,029,848＋出力30,922＝1,060,770、focusの入力80,038＋出力4,002＝84,040、総費用1,144,810である。cached input 863,148は入力に含まれており控除しない。

## 品質・費用・実介入を分ける

全4対のTDO−TR費用差は0（0%）。共通成功は写真操作・精算・返金の3課題で、各方式の合計470,370、共通成功差も0。CSVは双方ともAPI80要求で停止し、公式評価は失敗だった。全4対が評価済みで使用量も既知のため、この0は不明の補完ではない。

両方式の要約採用数は課題順に1、1、0、0であり、第2差分処置に到達した課題は**0/4（該当課題なし）**。写真操作・精算の初回要約は両方式で共通の処理である。共通成功の3課題を差分保持の効果例へ数えない。全pairのstrict/canonical prefixは第二境界がないためnullで、原理由は`boundary_absent`。`all_activated_canonical_prefixes_match=true`は作動例のない空集合に対する判定であり、実際のprefix一致が観測されたという意味ではない。

`observed_utility_criteria_met=false`、`comparison_gate_met=false`、`development_gate_met=false`を保持する。科学的採用と予約12課題での確認は評価していない。今回の非発動から保持方式に一般的な効果がないとも、同値成功から処置が品質を保ったとも結論しない。

## 条件・出所・解釈範囲

両方式の初回・反復閾値は16,384、最大2機会、直近2ターン保持、新規3ターン、model seed157/world seed42。各条件は80モデル要求、450,000 tokens、作業1,800秒、環境APIは写真操作160・他3課題80。奇数課題TR先行・偶数課題TDO先行の固定順で、無作為順序ではない。実行source `fd54c691c7cd2cfabd1c8c279ef0e6f710dfb773`、plan SHA `122a8fe0b4fe723dba21cc20e5f053e960ac542e9d1180dcccff8703ad4697e5`、source 1,783件。元pipeline/audit/session/reportは全exit0、閉鎖metadata独立検算は37,634 checks PASS。運用の完了と科学的効用を区別する。

既知4課題と既使用seed157の新cohortであり、P141の1課題0.84%等と合算しない。保持＋object出力指示＋ホスト結合のbundleを比較する設計であり、要素単独効果、E/C則の効果、統計的非劣性、独立追試、一般化、新規性はこの結果から確立しない。後続の別条件比較を準備しても本P142の条件・費用・判定を上書きしない。

## 根拠

- [固定仕様](P142_threshold_object_confirmation_20261028.md) / [plan](../../configs/P142_threshold_object_v01.json) / [開始時点](P142_execution_start_20261028.md)
- [元監査](../../reports/P142_comparison.json) / [元server session](../../reports/P142_server_session.json)
- [全8条件](../../materials/20261028_p142_results/conditions.csv) / [全モデル要求](../../materials/20261028_p142_results/model_calls.csv) / [全4対](../../materials/20261028_p142_results/pairs.csv)
- [元summary](../../materials/20261028_p142_results/summary.json) / [元manifest](../../materials/20261028_p142_results/build_manifest.json)
- [独立検算の公開射影](../../reports/P142_closed_metadata_review_public_20261028.json) / [コピー記録](../../reports/P142_results_copy_manifest_20261028.json) / [公開出所](../../reports/P142_results_provenance_20261028.json)

公開作業では元producer・auditor・checkerを再実行せず、図も新規生成していない。生成本文・認証値・評価本文・私的絶対パスmapは公開射影から除外した。native計数とcanonical構文再構成は固定producer/auditorに依存することを独立検算の限界として残す。

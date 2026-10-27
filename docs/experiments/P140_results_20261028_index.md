# P140 閉鎖結果・設定資料索引（2026-10-28）

既知4課題×3方式、seed57の全12条件を保持した開発結果の入口。TR4/4、ED3/4、EDO3/4成功、usage不明2呼出し、主・未変更delta・両対照gateはfalse。既知小計を削減効果や確定総費用に読み替えない。保留12課題を読んだ確認実験ではない。

## 結果と原表

- [結果・主張範囲・限定失敗診断](P140_findings.md)
- [元集計README](../../materials/20261028_p140_results/README.md)
- [全12条件](../../materials/20261028_p140_results/conditions.csv)、[全8対応行](../../materials/20261028_p140_results/pairs.csv)、[全255 model呼出しのscalar表](../../materials/20261028_p140_results/model_calls.csv)
- [元summary](../../materials/20261028_p140_results/summary.json)、[元build manifest](../../materials/20261028_p140_results/build_manifest.json)
- [元監査](../../reports/P140_comparison.json)、[元session報告](../../reports/P140_server_session.json)
- [完了済み初期検査](../../reports/P140_initial_checks.json)、[activation](../../reports/P140_activation_v01.json)

元producer10件は閉鎖時のhashでrun / preparation / publicationの同bytesを照合し、元manifestを変更せず収録した。以下の別資料・設定補足は元producer manifestへの追記ではない。

## 独立確認と閉鎖後補足

- [metadata checkerの公開用射影](../../reports/P140_closed_metadata_review_20261028.json)：原検算の範囲・依存・nullを保持し、ローカル絶対パスのprivate binding mapは公開しない。
- [独立科学metadata確認](../../reports/P140_closed_scientific_metadata_peer_20261028.json)：5,285照合PASS。固定判定と全12行を確認した範囲であり、モデル・native count・評価器の再実行ではない。
- [実図確認](../../reports/P140_actual_figures_review_20261028.json)：元の実図、数値、unknown表示の確認。
- [Task4のscalar失敗診断](../../reports/P140_closed_failure_scalar_diagnosis_20261028.json)：actor/focus、delta配信、最後の未知呼出し、条件付き費用余地。意味上の原因・実未知費用・延長成功を推定しない。

## 設定、先行方式、保留範囲

- [methods reference](../../materials/20261028_p140_results/methods_reference.md)と[source検証](../../reports/P140_methods_reference_source_validation_20261027.json)
- [現在hostのhardware / OS補足](../../reports/P140_host_hardware_snapshot_20261028.json)：起動後の観測であり、過去全要求の不変性の証明ではない。
- [先行方式との限定比較](../../reports/P140_method_prior_scope_20261027.json)、[研究史の追補](../../reports/P140_method_prior_historical_addendum_20261027.json)
- [保留12確認実験への未完了条件](../../reports/P140_reserved_confirmation_feasibility_20261027.json)：候補承認・実行済み結果ではない。
- [固定開発仕様](P140_checkpoint_delta_envelope_draft_20261027.md)、[当時の開始記録](P140_execution_start_20261027.md)

## 図

- [全12条件PNG](../../materials/20261028_p140_results/figures/whole_job_cost.png) / [PDF](../../materials/20261028_p140_results/figures/whole_job_cost.pdf)
- [固定2比較PNG](../../materials/20261028_p140_results/figures/paired_comparisons.png) / [PDF](../../materials/20261028_p140_results/figures/paired_comparisons.pdf)
- [元figure data](../../materials/20261028_p140_results/figures/figure_data.json) / [元figure manifest](../../materials/20261028_p140_results/figures/output_manifest.json)

図のunknownは既知部分の表示で、0補完ではない。全体・共通成功の固定差null、非発動、失敗を保持する。本索引と結果所見は原稿用の参照資料であり、原稿本文を代筆したものではない。

## 保存とコンパクト図

- [図の説明とrender source](../../materials/20261028_p140_results/figures/README.md)
- [コンパクト全12条件PNG](../../materials/20261028_p140_results/figures/compact/compact_cost.png) / [PDF](../../materials/20261028_p140_results/figures/compact/compact_cost.pdf)：検証済みの元figure dataから作成した別レイアウト。原図を置換せず、判定・実験・監査を再実行していない。
- [元ファイルのcopy manifest](../../reports/P140_results_copy_manifest_20261028.json) / [公開準備のローカル検証](../../reports/P140_results_local_validation_20261028.json)

公開準備の検証はソフトウェアと記録の整合性を対象とする。新技術の有効性、独立確認、採択の保証を意味しない。

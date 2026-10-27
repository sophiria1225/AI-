# P139 公開資料の入口

全16条件を評価し、固定された全5比較と組合せの採用基準はfalse。閾値＋deltaは4/4成功だが全仕事18,567 tokens増、累積再提示量の2方式は各3/4成功・不明usage各1件だった。元READMEは生成時の記述を同bytesで保存している。

- [結果と限界](../../docs/experiments/P139_findings.md)
- [全16条件](conditions.csv)、[全model要求の会計](model_calls.csv)、[全20対応行](pairs.csv)、[固定集計](summary.json)
- [元監査](../../reports/P139_comparison.json)、[server終了記録](../../reports/P139_server_session.json)
- [独立検算の公開用射影](../../reports/P139_closed_metadata_review_20261027.json)、[別担当の数値確認](../../reports/P139_closed_scientific_metadata_peer_20261027.json)
- [図と読み方](figures/README.md)、[図の独立確認](../../reports/P139_actual_figures_review_20261027.json)
- [途中9条件の閲覧開示](../../reports/P139_interim_exposure_disclosure_20261027.json)、[先行方式との限定比較](../../reports/P139_method_prior_scope_20261027.json)
- [元資料17件のcopy manifest](../../reports/P139_results_copy_manifest_20261027.json)、[公開来歴](../../reports/P139_results_provenance_20261027.json)、[ローカル検査](../../reports/P139_results_local_validation_20261027.json)

全条件、失敗、unknown、固定nullを保持する。既知の費用下界を削減として読まない。過去cohortは合算せず、保留12課題は使用していない。検算の整合性は有効性・新規性・一般的な品質維持の証明ではない。

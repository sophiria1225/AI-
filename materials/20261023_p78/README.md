# P78: API失敗通知の全８条件

2026年10月23日。必要な処理と最終品質を保ち、失敗と再取得を含む仕事全体費用を減らすための通常基準の比較。全８条件の独立評価・監査を終了し、不一致０、使用量不明０。所有推論器は正常停止し、両PIDの不在も確認した。

**文字列／例外通知はともに3/4成功、全仕事tokenは670,713／791,704。例外通知側が120,991多く、事前採用基準は未達。** 返金は実API例外が両側０であり、局所的な67,518 token差を通知方法の効果とはしない。書出しも実例外の前に経路が分かれた。

- [７枚のPDF](AI_harness_api_error_comparison_20261023.pdf)／[発表用HTML](index.html)
- [全８条件CSV](all_error_presentation_conditions.csv)／[全４対CSV](all_paired_results.csv)
- [全137モデル呼出し](all_model_calls.csv)／[全137公開Pythonプログラムの結果](all_python_program_results.csv)
- [全課題の費用図 SVG](figures/P78_whole_task_costs.svg)／[PNG](figures/P78_whole_task_costs.png)／[図単独PDF](figures/P78_whole_task_costs.pdf)
- [詳細な結果と解釈](../../docs/P78_findings.md)／[全件監査](../../reports/P78_comparison.json)／[推論器の終了記録](../../reports/P78_server_session.json)
- [公開APIの共通経路](../../reports/P78_public_api_prefixes.json)／[生JSONの差](../../reports/P78_input_divergence.json)／[参照IDをそろえた内容の差](../../reports/P78_input_content_divergence.json)

全７頁を目視し、レイアウト検査エラー０。表紙は題名のみ。資料の入力、CSV、PDF、描画コードのハッシュは[build manifest](build_manifest.json)に保存した。参照IDの最初の差を行動差へ読み替えず、返金・書出しの最初の内容差が実測残時間１秒だったことも記録している。内部状態の同一性や、その１秒の因果効果は特定していない。

実行は固定版`5971a0d2db71034329eafd91fc69161d16c1d91e`。１条件80生成・450,000 token・1,800秒、API写真160・他80。正常値、持続Python、公開API名、最初からの推論保持を共通にし、同じ実API例外を文字列またはPython例外として通知した。全137生成・1,462,417 token・448 API・８評価。保留12課題は未閲覧のまま。

[固定計画](../../docs/experiments/P78_api_error.md)／[起動版・CI記録](../../reports/P78_execution_start_20261023.json)／[準備manifest](preparation_manifest.json)。元のP76/P77と実API接続検査は別記録として保持する。P78を新手法の実証や旧実装の完全再現とは扱わない。主原稿への組込みは次の作業である。

# P88 全仕事での通常推論予算比較

既知４課題×通常２条件の全８条件を終了し、全て独立評価した。両方式とも成功3/4、成功喪失・獲得０。成功した３課題は各対の論理token差が０だった。曲情報の書出しは両方式で未達となり、上限なし側の１生成で使用量が不明なため、全４課題の費用差は未確定。固定した開発上の採用基準は満たさなかった。

全150生成、既知1,689,160論理token＋不明１生成、399 API、８評価を保持した。固定2,048側は881,697 token、上限なし側は既知807,463 token＋不明であり、この小計同士を確定した差や削減率として扱わない。監査不一致０。所有推論器の停止と両PID不在を確認し、監査・資源集計をそれぞれ一度実行した。

- [全７ページPDF](AI_harness_whole_task_reasoning_budget_20261024.pdf)
- [ブラウザ版](index.html)
- [全８条件CSV](all_eight_conditions.csv)／[全４対CSV](all_four_pairs.csv)
- [全件集計](whole_cohort_summary.json)／[固定比較の監査](../../reports/P88_comparison.json)
- [全生成の出力診断](../20261024_p88_output_diagnostic/README.md)
- [実結果に合わせた原稿](../../papers/202610_letter/reasoning_budget_control_observed/README.md)
- [詳細な所見](../../docs/P88_findings.md)

PDF全７ページを目視確認し、自動レイアウト検査のエラーは０だった。既知４課題・各１反復の開発比較であり、新手法・一般的な品質維持を示す結果ではない。終了済みP87の不足枠を補充せず、未知の生成を再試行していない。

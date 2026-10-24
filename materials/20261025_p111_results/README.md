# P111: 推論履歴３方式の全仕事比較

既知４課題×３方式、各１回の開発比較. 全条件と不明使用量、失敗、未実行を保持する.

| 課題 | 表示 | 成否 | 既知の全論理token | 不明使用量 | 生成 | API |
|---|---|---|---:|---:|---:|---:|
| 34d9492_1 | full | 成功 | 135628 | 0 | 16 | 99 |
| 34d9492_1 | recent | 成功 | 185165 | 0 | 17 | 99 |
| 34d9492_1 | execution_gated | 成功 | 174728 | 0 | 17 | 99 |
| 3c13f5a_1 | recent | 成功 | 194571 | 0 | 22 | 22 |
| 3c13f5a_1 | execution_gated | 成功 | 180000 | 0 | 21 | 22 |
| 3c13f5a_1 | full | 成功 | 211110 | 0 | 24 | 25 |
| 60d0b5b_1 | execution_gated | 成功 | 80314 | 0 | 13 | 12 |
| 60d0b5b_1 | full | 成功 | 102087 | 0 | 13 | 13 |
| 60d0b5b_1 | recent | 成功 | 73896 | 0 | 12 | 11 |
| 6104387_1 | execution_gated | 未達 | 228626 | 1 | 17 | 75 |
| 6104387_1 | recent | 未達 | 101399 | 0 | 11 | 80 |
| 6104387_1 | full | 未達 | 358638 | 1 | 21 | 53 |

開発上の両対照条件: False. この真偽だけで新規性や一般化を主張しない.

[全条件](all_conditions.csv)／[全生成試行](all_model_calls.csv)／[全表示判断](all_projections.csv)／[各対照との成否別比較](summary.json)／[サーバー全費用](server_cost.json).

使用量不明の要求を０へ補完しない. known_logical_tokensは既知部分の合計であり、不明があれば全費用は未確定. control時間はwork内、work/setup/cleanupはfull内、評価とloadはserver内なので重複加算しない. cached tokenの減少を論理tokenや時間の削減と同一視しない.

P110の仮想入力を実費用や新方式の品質へ転記していない. 全履歴の原文と生のモデル推論は非公開保存先に置く. 未見12課題と原稿保留を維持する.

[固定比較](../../docs/experiments/P111_whole_task_receipt_history.md)／[全監査](../../reports/P111_comparison.json).

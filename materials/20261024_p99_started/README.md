# P99開始：通常のauto/requiredを全仕事で比較

2026-10-24 12:37:43 UTCに所有推論器の起動手順へ入り、12:38:06 UTCから固定８条件の実行を開始した. 実行headは `02932c74f532dc1a3b48ad443223ec9d575c3ad0`. 同じ完全SHAのpush・pull_request両workflowと各accounting-and-syntax job成功を確認済み. PR #440はmainへ統合済み.

初期８要求の照合が完了し、４課題の各対で履歴と公開状態が一致、reasoning -1とauto/requiredが明示されている. 提出設定に伴う入力token数の差は処置に含める. 924ソースbindingを凍結した. [開始証拠](../../reports/P99_start_provenance_20261024.json)／[初期入力の確認](../../reports/P99_initial_checks.json)／[有効化](../../reports/P99_activation_v01.json)／[固定計画](../../configs/P99_whole_task_tool_choice_v01.json).

全８条件・全生成・失敗・不明を保持し、閉じるまで成否や費用の途中集計を読まない. 稼働確認はstatus、active、completed件数、時刻など明示した運用キーだけを出力する. 以前の欠測の置換や再試行ではない. 使用量不明の生成は実行せず条件を終え、効果と片付けが既知のときだけ固定の次条件へ進む.

所有推論器の終了後、有限の監視処理が凍結headと両CIを再確認し、監査・資源集計・資料・原稿を各１回作る. 失敗時は停止記録を保持し、自動再試行しない. 生成物は目視確認前で止まり、全頁を読んでから公開する. 現在は実行中で、結果・改善・新規性は未判定.

[P97全12条件の結果](../20261024_p97_results/README.md) は３方式とも3/4成功、CSV全未達で通知案を採らない根拠として保持した. 投稿候補は [P98実証稿](../../papers/202610_letter/README.md). 新手法・一般品質維持は未確立、未見12課題は保留している.

# P101 全36枠: requiredでも提出失敗は解消しなかった

保存６入力×auto/required×３反復を全て終了し、全36枠の使用量が判明した. 監査エラー・使用量不明・未実行は０、所有推論器は停止済み. [７頁PDF](AI_harness_choice_context_20261024.pdf)を全頁目視した. 元build manifestは変更せず、[目視記録](visual_review.json)を追加した.

autoは422,475 token、requiredは439,155 token. 形式の整った提出は両側12/18、ツール提出なしは両側6/18. 同一化したC/Dのauto６生成は各1,316 tokenで終了し、required６生成は各4,096 tokenの上限に到達した. requiredの増分16,680 tokenはこの６生成による. 残るA/B/N/Xでは、同じ入力の設定間で公開出力が一致した.

[全36生成](all_36_generations.csv)／[全12群](all_12_groups.csv)／[全66入力組](all_66_input_pairs.csv)／[全66出力組](all_66_output_pairs.csv)／[全出力比較](all_output_comparisons.json)／[費用](cost_totals.json)／[解釈と実行記録](../../docs/P101_findings.md).

全体861,630 token、追加API・生成コード実行・評価０. この結果は既知CSVの１文脈を用いた局所診断で、対数を独立課題数としない. C/D requiredの公開hashは同じでも途中切れである. ４頁の完全出力判定と５頁のhash比較を区別し、再現可能な有効操作とは扱わない. 提出構造hashはツール名や他引数も含む.

生成中に終了待機処理の報告CLI引数を修正したが、その時点では出力未閲覧、監査・報告段階０だった. 元生成・元監査・元report builderは変更せず、各後処理を１回実施した. [修正の記録](../20261025_p101_corrected_reporting_started/README.md). 原稿の逐次改訂は保留し、全36出力の実操作確認P102へ進む. 新手法・最終品質維持・全仕事削減は未確立.

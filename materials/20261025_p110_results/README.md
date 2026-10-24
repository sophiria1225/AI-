# P110: 実行記録に応じた推論履歴の表示

保存済み全8実行・148要求から、３表示・予定444入力のうち444入力を計数した. 状態はcomplete. 元の使用量不明1件は不明のまま残す.

fullは全推論、recentは直近だけ、execution_gatedは型付き実行記録に応じて古い推論を非表示にし、直近が不確かなら原文を再表示する. 実行正常は意味的な不要性の保証ではない. コード、API結果、指示、要求設定は維持した.

[全444枠](all_inputs.csv)、[全８実行×３表示](all_conditions.csv)、[全手順の適格理由](all_evidence.csv)、[集約](summary.json)を保持する. 元の失敗を含め、一部の成功例に絞っていない.

**固定済み軌跡上の仮想入力であり、新方針の全仕事費用ではない.** hypothetical_input_sumとhypothetical_delta_sumは計数用の集約であり、変更後の生成回数、出力、回復、品質は未測定. 共通接頭辞は実測cache使用量ではない. 原文を再表示する負担も各入力に含めたが、新しい実軌跡の復旧費ではない.

[固定計画](../../docs/experiments/P110_receipt_history_inputs.md)／[全結果](../../reports/P110_receipt_history_inputs.json). 追加モデル生成、API送信、生成コード実行、評価、DB読取、未見課題読取は０. 原稿は保留.

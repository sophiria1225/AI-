# P76：通常の推論保持あり・なし、全８条件

[５枚PDF](AI_harness_reasoning_comparison_20261023.pdf)／[ブラウザー資料](index.html)／[全８条件CSV](all_reasoning_conditions.csv)／[全結果・費用・限界](../../docs/P76_findings.md)。

成功は両方2/4。写真では保持ありが成功を保って38,570 token減少したが、精算・返金では増加し、書出しは両未達・使用量不明各１生成だった。全体の確定費用差は求めず、事前の局所採用基準は未達。保持そのものを新規手法とは扱わない。

新規43生成、既知継続588,495 token＋不明２生成、継続306＋復元102＝408 API、８評価。推論器停止・所有プロセス不在を確認した。全件監査の不一致０、保留群閲覧０。

全５ページを目視確認。出典・PDF・全件CSVのハッシュと確認ページは[生成記録](build_manifest.json)、はみ出し検査は[描画記録](layout_checks.json)。再生成は報告環境で `scripts/build_reasoning_comparison_report.py --pdf`。閉じた全件監査・停止済み推論器・固定条件に対応しない場合は生成しない。

# P123 全12条件の参考図

各barに最終評価を表示し、全4課題×3方式を残した。今回は全12成功・使用量不明0。通常のcheckpoint方式の比較で、新規機構の実証や一般的な品質維持とはしない。判定は[全結果](../../docs/P123_findings.md)を参照。

[PNG](p123_logical_tokens.png)／[SVG](p123_logical_tokens.svg)／[PDF](p123_logical_tokens.pdf)／[集計値](figure_data.json)／[出典hash](source_manifest.json)／[解釈](interpretation_note.md)。

再描画はmatplotlib 3.11.2を使用し、`python draw_p123_tokens.py --repo-root /path/to/AI- --output-dir /new/output/directory`。公開report・session・全件資料の閉鎖とhashを照合し、既存出力を上書きしない。初回の待機後描画はhash-onlyのinitial evidenceで結合している。

# CSVの取得範囲の点検（P69）

[４枚PDF](AI_harness_export_acquisition_scope_20261023.pdf)／[説明付きHTML](index.html)／[全結果と限界](../../docs/P69_findings.md)／[全件集計](../../reports/P69_export_acquisition_scope.json)。

既知CSV１課題の全５公開記録で、要求直前の必要列の充足と、完全なAPI応答の再利用を区別した。必要列が既知の曲詳細要求は0・0・8・9・9件、同一要求の完全な応答保持は全記録０。応答全体を置き換えるキャッシュや実測節約を示した結果ではない。新しい生成・環境API・評価・DB内容・保留群読取は０。

全４枚のレイアウトエラー０、目視確認済み。初回の２枚目の補足と結論の重なりは解消した。出典・生成スクリプト・PDFのハッシュは [build_manifest.json](build_manifest.json)、全検査は [layout_checks.json](layout_checks.json) に保存。

生成：`scripts/build_export_acquisition_report.py --pdf`（リポジトリのreporting環境を使用）。

# API返却の直接利用範囲（P70）

[５枚PDF](AI_harness_return_use_scope_20261023.pdf)／[説明付きHTML](index.html)／[全結果](../../docs/P70_findings.md)／[原典と過去実装の照合](../../docs/field_demand_review_20261023.md)。

P35と同じ全12条件、181プログラム出現・117固有入力を構文解析した。返却の根を名前へ束縛する144箇所と、全体のまま引数へ渡す95箇所があり、直接項目の自動置換候補は０。この限定方式をランタイムへ接続しない。箇所数は実API回数でも節約tokenでもない。

新しい生成・環境API・評価・DB内容・保留群・記録コードの実行は０。全５枚を目視確認し、[レイアウトエラー０](layout_checks.json)。出典とPDFのハッシュは [build_manifest.json](build_manifest.json) に保存した。

生成：`scripts/build_return_use_report.py --pdf`（リポジトリのreporting環境を使用）。

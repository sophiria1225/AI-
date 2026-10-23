# 10月23日：生成境界とAPI返却の利用範囲

[４枚PDF](AI_harness_boundary_lifetime_20261023.pdf)／[HTML・発表ノート](index.html)／[全12条件CSV](all_lifetime_cells.csv)／[全結果と限界](../../docs/P74_findings.md)。

P70と同じ全12条件・181出現・117固有入力を現在のコードだけで点検。144名前保存のうち項目参照のあるものは15箇所、明示的上書き３出現、固定した限定候補は０。最後の参照と根の破棄、正常経路と例外・次の生成を分けた。

0.181136秒、未対応・未処理０。追加生成・API・評価・保存コード実行・保留群０。実行系へ拡張せず、構文数を不要量や節約へ換算しない。通常の依存解析・遅延取得全般の不可能性や、新規手法の成立は主張しない。

全４頁を目視し、重なり・はみ出し０。PDF SHA-256：`d8489e31d5edafe7a24204e2f3e2bc5e6514a9c73f449e3b45f9c738c41fc9bc`。再生成は `scripts/build_boundary_lifetime_report.py --pdf`。出典は[build_manifest.json](build_manifest.json)、表示点検は[layout_checks.json](layout_checks.json)。元コードを再解析する処理ではない。

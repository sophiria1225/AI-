# 10月23日：公開名接続での説明表示比較

[６枚PDF](AI_harness_public_display_20261023.pdf)／[HTMLと発表ノート](index.html)／[全24条件CSV](all_display_cells.csv)／[全結果と限界](../../docs/P71_findings.md)。

全12件を評価。全表示F・詳細省略D・一覧も省略Bの成功は2/4・1/4・2/4、仕事の既知tokenは500,883・523,407＋不明２生成・557,248。Dは既知分だけでFより22,524 token多く、固定採用条件は未達だった。

新しい生成73回、既知継続950,398 token＋不明２生成、継続490 API、復元153 API、12評価。監査不一致０、推論器3,724.097秒で正常停止。全６頁を目視し、レイアウトの重なり・はみ出し０。PDF SHA-256：`deae54f2c9b699297f0c9a64c8be39a0677ebc734909df8861a805ffe77621ec`。

元P55を全件保持し、CSVには両比較の全24表示条件を掲載した。同じ既知４課題であり、独立８課題ではない。公開名接続は共通前半の後に適用し、旧新差を接続制約だけの因果効果としない。写真D/Bの非supervisor保存状態の一致と成否差は、[全12対の照合](../../reports/P71_outcome_scope.json)へ記録した。

資料の再生成は `scripts/build_public_display_report.py --pdf`。参照JSONと描画処理のハッシュは[build_manifest.json](build_manifest.json)、表示測定は[layout_checks.json](layout_checks.json)。再生成後は目視確認を行う。新手法・一般的品質維持・採録に足る貢献は未確定。

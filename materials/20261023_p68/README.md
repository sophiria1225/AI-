# CSVの通常終了制御 — 全２条件の結果

**両条件ともAPI上限で未達、各219,126 tokenで削減なし。** 全16生成・438,252 token・160 API・２評価、使用量不明０。書出しと退会を行う前に停止し、制御も完了通知を送らなかった。監査1,348項目不一致０、推論器正常停止。

[５枚PDF](AI_harness_export_completion_20261023.pdf)／[HTML](index.html)／[説明メモ](slides.json)／[全結果と限界](../../docs/P68_findings.md)／[全監査](../../reports/P68_completion_audit.json)／[全判定境界](../../reports/P68_completion_boundaries.json)。全５頁目視、[レイアウト不一致０](layout_checks.json)。

[P68の固定計画](../../docs/experiments/P68_export_completion.md)／[設定](../../configs/P68_export_completion_v01.json)。同じ既知CSV課題を、新しい通常nativeと同じnative＋外部終了制御で各１回比較した。固定版457aeb8226d0d31928f8c9df3a03e786535d1425の両CI・job成功後に開始し、途中の条件変更はない。

各80生成・450,000 token・1,800秒・80 API。追加の完了通知も同じAPI予算に含める。初期状態・一般案内・静的通知・モデル・seed・cold初回条件をそろえる。モデルによる正しい書出しと、その後の退会の公開証拠がそろったときだけ、制御から通常の完了通知を送る。

[P67](../20261023_p67/README.md)で見つけた後続41,702 tokenは節約額ではない。両成功、未知費用０、監査不一致０、最終13保存ファイル一致、全体token減という局所条件を固定する。失敗も未実行も残し、再試行や条件交換はしない。手書きの既知文型の通常制御であり、新方式や一般的品質維持の証明とはしない。

公開イベント・応答と最終13保存ファイルは両条件で一致したが、呼出しIDによる要求・モデル応答の全文不一致は保持。局所採用条件は満たさない。P66の写真の改善と併記し、終了規則だけで未完了の作業を改善できたとはしない。保留12シナリオは未閲覧のまま。

生成は `scripts/build_export_completion_report.py --pdf`。出典ハッシュ・PDFの確認記録は[build_manifest.json](build_manifest.json)。

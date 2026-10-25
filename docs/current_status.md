# 現在の研究状態：2026年10月26日 08:27 JST

P123は全12条件を終了し、3方式とも既知4課題で4/4成功、使用量不明0、監査エラー0。総logical入力＋出力tokenは単発893,529、別呼出し反復785,656、同時反復836,922。別呼出し反復は単発より12.07%少ない。同時反復は別呼出し反復より6.53%多いため、事前の採用判定はfalseを保持する。

[P123全結果](P123_findings.md)／[独立再計算](P123_independent_audit.md)／[全件資料](../materials/20261025_p123_results/README.md)。P124は保存応答再生で全20program一致、通常完全cache68対提案57。実API/model0で、全仕事の品質・tokenは未測定（[結果](P124_findings.md)）。

P125は2026-10-26 08:25 JSTに開始済み。既知4課題×2方式・seed157で、自動field projectionの追加効果を全仕事で測る。実行head `2c11ceaa65b47b27cd23df8a943ab3d745b94461` のpush/PR両CI成功を確認し、[PR517](https://github.com/sophiria1225/AI-/pull/517)をmerge済み。1,125 source filesとP123/P124閉鎖証拠へ固定した8条件を実行している。初期入力8件と要約transport1件の計数、activationが完了。08:27 JSTにwrapper・pipeline・所有server・batchの生存を確認した。途中の成否・使用量・モデル本文は未読で、P125の結果は未確定。各80 model呼出/450,000 tokens/1,800作業秒、全体8評価・800 API・server6時間の上限を維持する。 [開始記録](../reports/P125_execution_start_20261026.json)。共通の通常cacheは公開実装を照合した対象Song readに限定、checkpointは事前選定の単発を維持する。P123で最小だった別反復への直接比較ではなく、これを既に上回ったとはしない。

目的は最終task成功を保ちながら要約・制御・失敗・再取得を含む全仕事のlogical入力＋出力tokenを減らす、新規性を説明できるハーネス制御。まだ新規機構の目標達成は未実証。原稿はユーザーが執筆し、こちらは約24時間（10/27 06時頃まで）の主要実験と根拠整理を優先する。普通のメッセージには応答しながら実験を継続し、明示停止に従う。

未見12課題は未閲覧の予約を維持。P122のCSV成功損失、不明1要求、全旧結果と原稿を保持する。[履歴レビュー](research_history_review_20261026.md)／[次の作業](next_actions.md)／[RESUME](../RESUME.md)。

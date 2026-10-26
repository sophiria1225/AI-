# 現在の研究状態：2026年10月26日、P125全件閉鎖後

P125は全8条件と所有serverを閉鎖し、独立評価・元監査・collector・独立再計算を終了した。通常cacheと自動projectionは各3/4成功、総logical入力＋出力766,875 tokenで一致。使用量不明0、元監査エラー0。全146 programで静的受理・変換・partial hit・通常complete-cache hitは0、projection契約失敗も0だった。CSVは両方式ともAPI上限80で失敗し、固定の採用gateはfalseを保持する。

[P125全結果](P125_findings.md)／[独立再計算](P125_independent_audit.md)／[全8条件資料](../materials/20261026_p125_results/README.md)。全条件合計は1,533,750 token・154 model呼出し・488実API・8評価。実行head `2c11ceaa65b47b27cd23df8a943ab3d745b94461` と1,125 source filesを保持し、wrapper・collectorを再実行しない。

閉鎖後診断では、CSVの実show_song取得25件は、既存library providerから必要値を再利用できる候補が0だった。既存の通常joinなら必要なtitleとartistsが13件でそろう候補はあるが、実削減・全仕事token・最終品質は未測定。join自体は新規機構ではない。ID guard追加やimport・動的loopの受理だけで改善すると判断しない。次の有限比較は未固定、新しい実験は未開始である。

P123は全12条件を終了し、3方式とも既知4課題で4/4成功、使用量不明0、監査エラー0。総logical入力＋出力tokenは単発893,529、別呼出し反復785,656、同時反復836,922。別呼出し反復は単発より12.07%少ない。同時反復は別呼出し反復より6.53%多いため、事前の採用判定はfalseを保持する。

[P123全結果](P123_findings.md)／[独立再計算](P123_independent_audit.md)／[全件資料](../materials/20261025_p123_results/README.md)。P124は保存応答再生で全20program一致、通常完全cache68対提案57。実API/model0で、全仕事の品質・tokenは未測定（[結果](P124_findings.md)）。

P125はseed157・共通単発checkpoint、P123はseed57・異なるcache/表示条件なので、両結果を一因子差や直接の優劣として扱わない。P125がP123の別反復を上回ったという結果ではない。

目的は最終task成功を保ちながら要約・制御・失敗・再取得を含む全仕事のlogical入力＋出力tokenを減らす、新規性を説明できるハーネス制御。まだ新規機構の目標達成は未実証。原稿はユーザーが執筆し、こちらは約24時間（10/27 06時頃まで）の主要実験と根拠整理を優先する。普通のメッセージには応答しながら実験を継続し、明示停止に従う。

未見12課題は未閲覧の予約を維持。P122のCSV成功損失、不明1要求、全旧結果と原稿を保持する。[履歴レビュー](research_history_review_20261026.md)／[次の作業](next_actions.md)／[RESUME](../RESUME.md)。

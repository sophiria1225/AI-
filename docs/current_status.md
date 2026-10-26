# 現在の研究状態：2026年10月26日、P127全件閉鎖

P127は2026-10-26 13:08 JSTに全8条件・所有server・collector・後処理を閉鎖した。両方式とも3/4成功、全仕事logical入力＋出力695,217 token、共通成功352,584 tokenで差0。全132 programで静的受理・変換・automatic partial hit・明示field要求は0、CSVの通常完全cache hitは各72。使用量不明0、契約停止0、監査エラー0、固定gateはfalse。CSVは両方式とも117 APIで完了宣言したが独立評価は失敗した。

[全件所見](experiments/P127_findings.md)／[元監査](../reports/P127_comparison.json)／[独立再計算](../reports/P127_closed_independent_audit_20261026.json)／[全件資料](../materials/20261026_p127_results/README.md)／[図](../materials/20261026_p127_results/figures/README.md)。

全8条件合計は1,390,434 token・136 model呼出し・490実API・8独立評価。全体と共通成功群の差はどちらも0。通常cache利用を自動機構の効果にしない。元監査と独立監査の一致は方式採用や一般的品質維持を意味しない。

実行head `0219f774326e7e4e2fdacc6aaaf0c45ea381cfc0` と1,142 sourcesを保持する。11:45 JST開始、13:08 JST閉鎖、所有server停止、collector・後処理complete。後処理の待機制御v01→v02修正を保存し、model再実験は0。固定run/editor木を編集せず、元wrapper/collectorを再起動しない。

[全132 sourceのAST診断](experiments/P127_admission_diagnosis.md)を終了した。全66対source/AST同値、対象取得は完全応答を永続dictへ保存するため拒否され、構文緩和だけで安全に取得省略できる根拠はなかった。追加seedや同条件反復を自動開始しない。新しい実験は未開始。限定した効果経路がある場合だけ別の有限比較を固定する。[次の作業](next_actions.md)。

P126の保存prefixで13取得省略×2記録を示したことは、今回のonline token/品質の効果へ移して計上しない。P125は両3/4成功・766,875 token・API80停止、P123は各4/4成功・別反復785,656 token等の異なる条件で、今回と一因子比較として混ぜない。[P126](experiments/P126_findings.md)／[P125](P125_findings.md)／[P123](P123_findings.md)。

新規機構による最終task成功維持と全仕事logical入力＋出力削減は未実証。原稿はユーザーが執筆し、こちらは10/27 06時頃までの主要実験と全件資料・再現根拠を優先する。普通のメッセージには応答しながら継続し、明示停止には従う。未見12課題は予約を維持。P122の成功損失、不明1要求、全旧結果と原稿を保持する。[履歴レビュー](research_history_review_20261026.md)／[RESUME](../RESUME.md)。

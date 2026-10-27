# P137 実行開始 — 2026-10-27 12:29 JST

P137は12:29:26 JSTに一度だけ起動した。12:31:46 JST時点で、最初のentity_fields／seed57条件のactor要求保存とmodel slot処理中を確認した。その観測時点の完了は0/4条件。この記録は時点付きの運用証拠であり、全4完了、課題成功、費用削減を示さない。実行中の要求本文・生成内容・usage・成否・captureは読まない。

対象は既知CSV1課題、P136で未実施だった4条件だけで、実行順は **fields57 → fields157 → IDs157 → raw157**。seed57はentity_fields単独で対照がなく、seed157の3方式だけが同一cohort内の記述的比較となる。不均衡な方式別合計を効果比較に使わない。P136の評価済raw57と未完IDs57は再実行せず、元6行・欠測・gate falseを置換・合算しない。P137の採用判定は行わず、結果にかかわらずdevelopment gateはfalseのまま保持する。

機構・初期guide・CODE_TOOLS・typed観測・capture・rolling checkpointはP136と同じ。query toolや公開snapshot handleを追加しない。accepted checkpoint後の次actorだけに通知を付ける。同じclosed pending-ID列を条件に共通selectorが同じ最大16行のprefixを選び、fields側だけ不足fieldを加える。独立runの実際のID列・軌跡の一致を開始記録から主張しない。JSON本文2048 bytesに見出し43 bytesが加わる最大2091 bytesも実際のlogical入力へ計上する。

新実行では、SIGALRMを記録可能なtimeout経路へ戻す修正とworker終了状態の保存を適用した。これはP136の元停止原因や欠測を取り消すものではない。新規性、一般品質維持、新方式の全仕事token削減は未確立であり、原稿本文はユーザーが執筆する。

実行sourceは`a6c088f8f382521010ff264ffe22f52d2146314e`、plan SHAは`9b8b020c83bf1d996b4d977a628831c46da4d7a0e469a3cf2b8f0e18916720f1`、1,547 sourceを固定した。[PR #550](https://github.com/sophiria1225/AI-/pull/550)の同head push/PR両CI成功後、独立run treeで起動した。開始snapshotは196台帳/2,433束縛であり、その後のglobalを遡及しない。

各条件はactor＋focus共有80呼出し、450,000 logical input+output tokens、1,800作業秒、API80。全4条件は最大320呼出し・1,800,000 tokens・API320・評価4件。所有serverは最大4時間、18:00 JST期限を維持する。失敗・unknown・未完・未実施も全予定行へ残し、cached inputを差し引かず全仕事費用を扱う。

独立検算の待機は12:29:24 JST、図作成の待機は12:29:25 JSTに各一度だけ開始した。待機開始は監査PASSや図完成ではない。collectorと固定独立reviewが閉鎖してからだけ実図を作り、失敗時は元記録を残し自動再試行しない。既存の継続指示の範囲で進め、通常会話では止めず、明示停止 `.runtime/P137.stop` に従う。

[固定仕様](P137_remaining_late_obligations.md)／[開始記録](../../reports/P137_execution_start_20261027.json)／[出所と検証](../../reports/P137_execution_start_validation_20261027.json)／[P136の欠測を含む閉鎖結果](P136_findings.md)。

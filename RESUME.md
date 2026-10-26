# 再開の入口：P128全16条件を実行中（2026-10-26 18:06 JST開始）

通常のユーザーメッセージは停止指示ではない。現在の実験を維持しながら応答し、次の具体比較も並行準備する。ユーザーは明示停止まで実験を継続するよう繰り返し指示している。原稿はユーザー担当。[現在の状態](docs/current_status.md)／[比較仕様](docs/experiments/P128_whole_task_receipt_disclosure.md)。

P128は既知4課題×full/disclose×seed57/157、16条件。固定head `0c29b754b23c8ca97ead6e9319661395b6c603a9`、plan SHA `8b061a77f3e778716e0a846ea3be46e05ec6012aecd826c44b8c9b84bf006d00`。push/PR両CI、初期16＋要約2計数、activationを完了して実model応答進行中。[開始記録](reports/P128_execution_start_20261026.json)。

`p128-run` と `p128-receipt-disclosure` は凍結木で編集しない。元wrapper `run_close_p128_once_20261026.py` は一度だけ起動済み。全16枠audit/session/reportと開始snapshotに基づくcollectorまで自動接続している。再起動・同一seed追加・条件変更をしない。active状態をruntimeの更新時刻と所有processで確認し、終わった管理processを実験中と説明しない。

開始snapshotは181台帳/2,156束縛。今後global台帳が増えても、このsnapshotをP128の凍結木・collectorに用いる。unknown/null・失敗・未実施を全16枠で保持する。各seedで成功維持と全課題/共通成功のtoken削減を要求し、普通のreceipt disclosureを新規手法と呼ばない。最終目標は未達。

P127全8件は13:08 JSTに閉鎖済み。各3/4成功・695,217 token・機構未発動・固定gate false。P127を含む全旧wrapper/collector/closed結果を再実行しない。[P127所見](docs/experiments/P127_findings.md)。その後のmodel空き時間を反省し、今回の稼働中に次の有界比較を準備する。[次の作業](docs/next_actions.md)。

主要実験の目安は10/27 06:00 JST。単一local model serverを共有し、未見12課題は別の固定確認計画まで閲覧しない。未完了の原稿・過去の成功損失・使用量不明を改変せず、教授送信・投稿は行わない。

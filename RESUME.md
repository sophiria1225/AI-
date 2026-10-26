# 再開の入口：P128全16条件を実行中（2026-10-26 18:06 JST開始）

## P130も固定し、自動継続を予約済み（19:30 JST）

P128全16条件を実行中のまま、P129全6条件に続くP130全4条件も固定した。CSV既知1課題×inventory off/on×seed57/157、共通grounding feedback。checkpoint後の変数名・組込み型・コンテナ長だけを一度表示する通常inventoryの効用を測る。値は表示せず、両条件で同じcapture費用を計上する。P33等との重複を保持し、新規性や提示時機の優位性は主張しない。

P130 head `8d60aaedac3ccdb4d2f5cca760574f3ea5c13507`、1,205 sources、合成78testsとpush/PR両CI成功、PR528 merge済み。P129の全6枠回収・所有server停止後に一度だけ起動する待機processを19:30 JSTに開始した。予約時点のP130 model生成は0。各80呼出/450k tokens/1800作業秒/120 API、全320呼出/1.8M tokens/480 API/4評価。4時間server leaseが06:00 JSTまでに収まる02:00 JST以前だけ起動する。

P130の開始snapshotは183台帳/2,158束縛。後から増えるglobal registryを凍結木に適用しない。P128/P129/P130の実行木と元wrapper/queueを変更・重複起動しない。通常の会話で実行を止めず、明示停止を全稼働・待機処理へ反映する。全枠・不明費用・失敗を残して独立検算し、原稿用の全件資料へつなげる。P128の最初3行を運用確認で表示した事実はP130仕様に記録し、それ以前に選んだ4条件を変更していない。

[予約記録](reports/P130_continuation_reserved_20261026.json)／[比較仕様](docs/experiments/P130_whole_task_checkpoint_inventory.md)。

## P129も固定し、自動起動を予約済み（18:54 JST）

P128の実行を続けながら、CSV既知1課題×off/feedback/repair×seed57/157のP129全6条件も固定した。head `35640e5a447f99f182293e6e26033b25c640061c`、1,182 sources、両CI成功、PR526 merge済み。P128全16枠の回収と所有server閉鎖後、P129を一度だけ起動する待機processが稼働している。P128の成否で条件を選ばず、同じserverを重複起動しない。P129のmodel生成はこの予約時点では未開始。

通常のメッセージで実行・予約を止めない。明示停止はP128/P129の両方へ反映する。P129は各80共有呼出/450k tokens/1800作業秒/120 API、全480呼出/2.7M tokens/720 API/6評価、server6時間が06:00 JSTまでに収まる時刻に限って起動する。開始前に予約した182台帳/2,157束縛を用い、後から増えるglobal台帳を凍結木に適用しない。元queue/wrapper/prepareを重複起動しない。

主比較は普通のfeedbackに対する決定論的CSV修復。未知証拠では修復せず、deleteには介入しない。原wire・実送信payload・nonce・noticeを監査し、実送信と保存確認済み修復を分ける。通常検証の校正で、新規性は未確立。P128/P129双方の終了後に全条件・不明費用を保持して判断する。

[P129予約記録](reports/P129_continuation_reserved_20261026.json)。

通常のユーザーメッセージは停止指示ではない。現在の実験を維持しながら応答し、次の具体比較も並行準備する。ユーザーは明示停止まで実験を継続するよう繰り返し指示している。原稿はユーザー担当。[現在の状態](docs/current_status.md)／[比較仕様](docs/experiments/P128_whole_task_receipt_disclosure.md)。

P128は既知4課題×full/disclose×seed57/157、16条件。固定head `0c29b754b23c8ca97ead6e9319661395b6c603a9`、plan SHA `8b061a77f3e778716e0a846ea3be46e05ec6012aecd826c44b8c9b84bf006d00`。push/PR両CI、初期16＋要約2計数、activationを完了して実model応答進行中。[開始記録](reports/P128_execution_start_20261026.json)。

`p128-run` と `p128-receipt-disclosure` は凍結木で編集しない。元wrapper `run_close_p128_once_20261026.py` は一度だけ起動済み。全16枠audit/session/reportと開始snapshotに基づくcollectorまで自動接続している。再起動・同一seed追加・条件変更をしない。active状態をruntimeの更新時刻と所有processで確認し、終わった管理processを実験中と説明しない。

開始snapshotは181台帳/2,156束縛。今後global台帳が増えても、このsnapshotをP128の凍結木・collectorに用いる。unknown/null・失敗・未実施を全16枠で保持する。各seedで成功維持と全課題/共通成功のtoken削減を要求し、普通のreceipt disclosureを新規手法と呼ばない。最終目標は未達。

P127全8件は13:08 JSTに閉鎖済み。各3/4成功・695,217 token・機構未発動・固定gate false。P127を含む全旧wrapper/collector/closed結果を再実行しない。[P127所見](docs/experiments/P127_findings.md)。その後のmodel空き時間を反省し、今回の稼働中に次の有界比較を準備する。[次の作業](docs/next_actions.md)。

主要実験の目安は10/27 06:00 JST。単一local model serverを共有し、未見12課題は別の固定確認計画まで閲覧しない。未完了の原稿・過去の成功損失・使用量不明を改変せず、教授送信・投稿は行わない。

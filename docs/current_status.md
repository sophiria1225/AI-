# 現在の研究状態：P128全16条件を実行中（2026-10-26 18:06 JST開始）

## P129も固定し、自動起動を予約済み（18:54 JST）

P128の実行を続けながら、CSV既知1課題×off/feedback/repair×seed57/157のP129全6条件も固定した。head `35640e5a447f99f182293e6e26033b25c640061c`、1,182 sources、両CI成功、PR526 merge済み。P128全16枠の回収と所有server閉鎖後、P129を一度だけ起動する待機processが稼働している。P128の成否で条件を選ばず、同じserverを重複起動しない。P129のmodel生成はこの予約時点では未開始。

通常のメッセージで実行・予約を止めない。明示停止はP128/P129の両方へ反映する。P129は各80共有呼出/450k tokens/1800作業秒/120 API、全480呼出/2.7M tokens/720 API/6評価、server6時間が06:00 JSTまでに収まる時刻に限って起動する。開始前に予約した182台帳/2,157束縛を用い、後から増えるglobal台帳を凍結木に適用しない。元queue/wrapper/prepareを重複起動しない。

主比較は普通のfeedbackに対する決定論的CSV修復。未知証拠では修復せず、deleteには介入しない。原wire・実送信payload・nonce・noticeを監査し、実送信と保存確認済み修復を分ける。通常検証の校正で、新規性は未確立。P128/P129双方の終了後に全条件・不明費用を保持して判断する。

[P129予約記録](../reports/P129_continuation_reserved_20261026.json)。

P128は18:06 JSTに起動し、モデルの実応答も進行中。既知4課題×receipt full/disclose×固定seed57/157の16条件を比較する。実行head `0c29b754b23c8ca97ead6e9319661395b6c603a9` のpush/PR両CIに成功し、[PR524](https://github.com/sophiria1225/AI-/pull/524)はmerge済み。1,162 source files、初期入力16件と要約transport2件、全条件activationを固定した。[開始記録](../reports/P128_execution_start_20261026.json)／[比較仕様](experiments/P128_whole_task_receipt_disclosure.md)。

両方式に同じguide・explicit joined fields・通常完全cache・rolling separateを使い、自動region変換は両方無効。原receiptの詳細を毎回表示する方式と、同じ元archiveへの参照を表示し必要時に通常tool actionで読む方式を比べる。展開・要約・失敗・回復を含む全仕事logical入力＋出力を計上する。各seedで成功損失なし、全課題と共通成功群の両費用減、実dispatch入力での開示と契約維持が必要。通常の効率校正であり、単独の新規性は主張しない。閉鎖前の品質判定や条件変更はしない。

各80共有model呼出し・450,000 token・1,800作業秒。全体1,280 model呼出し・7.2M token・1,760 API・16評価。所有serverは最長11時間で、06:00 JSTの締切を超える起動を拒否する。元wrapperは全16枠の監査・server会計・集計・回収まで接続済み。起動済みwrapper/prepareを重複実行しない。

P127後に次のmodel比較を開始せず空き時間を作った進め方を修正した。通常の質問・進捗確認は停止指示ではない。実験を動かしながら次比較の実装・対照・有限予算を準備し、明示停止には従う。新規性・品質・token削減を示す最終目標は未達。原稿はユーザーが執筆する。

並行準備は、P127の公開取得データと実CSV書込内容の不一致に対する出力検証、および実行状態とcheckpointの接続を含む技術案。P128途中結果でseedや条件を追加しない。未見12課題は別の確認計画が固まるまで未閲覧。

前段P127は13:08 JSTに全8条件閉鎖。各3/4成功・695,217 tokenで差0、全132 programで自動機構未発動、CSV失敗、監査エラー0、固定gate falseを保持する。[P127所見](experiments/P127_findings.md)／[元全件資料](../materials/20261026_p127_results/README.md)。P123/P125/P126/P127を今回の反復へプールしない。[再開入口](../RESUME.md)／[次の作業](next_actions.md)。

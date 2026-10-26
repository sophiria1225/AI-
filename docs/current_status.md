# 現在の研究状態：P128全16条件を実行中（2026-10-26 18:06 JST開始）

P128は18:06 JSTに起動し、モデルの実応答も進行中。既知4課題×receipt full/disclose×固定seed57/157の16条件を比較する。実行head `0c29b754b23c8ca97ead6e9319661395b6c603a9` のpush/PR両CIに成功し、[PR524](https://github.com/sophiria1225/AI-/pull/524)はmerge済み。1,162 source files、初期入力16件と要約transport2件、全条件activationを固定した。[開始記録](../reports/P128_execution_start_20261026.json)／[比較仕様](experiments/P128_whole_task_receipt_disclosure.md)。

両方式に同じguide・explicit joined fields・通常完全cache・rolling separateを使い、自動region変換は両方無効。原receiptの詳細を毎回表示する方式と、同じ元archiveへの参照を表示し必要時に通常tool actionで読む方式を比べる。展開・要約・失敗・回復を含む全仕事logical入力＋出力を計上する。各seedで成功損失なし、全課題と共通成功群の両費用減、実dispatch入力での開示と契約維持が必要。通常の効率校正であり、単独の新規性は主張しない。閉鎖前の品質判定や条件変更はしない。

各80共有model呼出し・450,000 token・1,800作業秒。全体1,280 model呼出し・7.2M token・1,760 API・16評価。所有serverは最長11時間で、06:00 JSTの締切を超える起動を拒否する。元wrapperは全16枠の監査・server会計・集計・回収まで接続済み。起動済みwrapper/prepareを重複実行しない。

P127後に次のmodel比較を開始せず空き時間を作った進め方を修正した。通常の質問・進捗確認は停止指示ではない。実験を動かしながら次比較の実装・対照・有限予算を準備し、明示停止には従う。新規性・品質・token削減を示す最終目標は未達。原稿はユーザーが執筆する。

並行準備は、P127の公開取得データと実CSV書込内容の不一致に対する出力検証、および実行状態とcheckpointの接続を含む技術案。P128途中結果でseedや条件を追加しない。未見12課題は別の確認計画が固まるまで未閲覧。

前段P127は13:08 JSTに全8条件閉鎖。各3/4成功・695,217 tokenで差0、全132 programで自動機構未発動、CSV失敗、監査エラー0、固定gate falseを保持する。[P127所見](experiments/P127_findings.md)／[元全件資料](../materials/20261026_p127_results/README.md)。P123/P125/P126/P127を今回の反復へプールしない。[再開入口](../RESUME.md)／[次の作業](next_actions.md)。

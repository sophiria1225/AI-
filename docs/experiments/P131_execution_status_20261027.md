# P130起動前失敗とP131の開始記録

P130は10月27日01:07 JST、8011番portの可用性検査で`EADDRINUSE`となり、model本体・tokenizer preflight・task処理・評価の前に停止した。旧sourceと元失敗記録を保持する。当時のsocket状態は保存されておらず、TIME_WAIT等を原因と断定しない。[起動前失敗の確認](../../reports/P130_startup_failure_20261027.json)。

次の新cohort P131 wrapperを04:15:31 JSTに開始した。P130失敗から約3時間8分が経過しており、この間隔を実験継続や成果として数えない。継続指示が有効な中で再開が遅れた運用上の空白である。新しい有限比較として、元P130の先頭seed57だけを使うoff/on各1件へ縮小した。失敗したP130を成功した試行へ置き換えたり、未実施4枠を完了扱いしたりしない。

固定head `d312a0d0b51928ac96150b3863cff75d7577eae9`、plan SHA `a6e22aaeda7f62d4f4dd6ebf7a9b62bf20a947eb22a1c918c48882c9f1404044`、1,225 source、push/PR両CI成功を確認して一度起動した。各80共有model呼出し・450,000 logical tokens・1,800作業秒・120 API、2評価、server最大6,000秒、06:00 JSTを上限とする。[固定仕様](P131_whole_task_checkpoint_inventory_recovery.md)。開始snapshotは186台帳・2,231束縛で、後から増えるglobalを既存runへ適用しない。

開始後の運用metadata確認ではpipelineは`stopped`だった。起動の事実は全2条件の完了、actor生成、品質や費用の改善を意味しない。ここではtask成否・usage・生成内容を読まず、停止原因と実行範囲は別の運用確認で確定する。元cohort・wrapperを重複起動せず、元失敗を上書きしない。[時点付き運用集約](../../reports/P131_execution_status_20261027.json)／[開始原記録](../../reports/P131_pipeline_once_start.json)。

原稿に使える閉鎖済み資料はP129まで整備したが、採択を狙う新規手法、一般的な精度維持と全仕事token削減の成立は未達。P128のseed157や共通成功部分集合の減少を、成功損失・unknownを含む全体の効果にしない。原稿はユーザーが執筆する。通常会話は停止指示と扱わず、明示停止へ従う。未見課題やprivate prompt・reasoning・生成code・課題値・評価本文は公開しない。

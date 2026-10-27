# P136 実行開始 — 2026-10-27 10:46 JST

P136は10:46:31 JSTに一度だけ起動した。10:47:22 JST時点でpreflight/activation成功、最初のraw anchor条件のactor要求保存とmodel slot処理中を確認した。これは時点付きの運用記録であり、全6完了、課題成功、費用削減の証拠ではない。途中の要求本文・生成内容・usage・成否・captureは読まない。

既知CSV1課題、raw anchor／IDのみ／同じIDと不足fieldの3方式×seed57/157、全6条件を固定した。全方式の初期guideとtoolsは元raw構成のまま同一で、query toolや公開snapshot handleを追加しない。typed観測・captureは共通とし、採用済みrolling checkpoint後の次actor一度だけ、主2方式に有料の通知を加える。同じclosed pending-ID列を条件に同じ昇順prefixを選び、fields側だけ不足fieldを加える。独立runの全軌跡が同一になるとは主張しない。

P135の全6閉鎖、品質喪失、unknown2、詳細行0、gate falseを変更しない。P136は初期interface差・scope handle差を除き、普通のID再提示にfield対応付けを追加する価値を問う別設計である。固定公開GETの限定対応で過去のunknownを取り消さず、liked playlist値を所有libraryの対象集合へ加えない。新規性、一般品質維持、新方式の全仕事token削減は未確立である。

実行sourceは`e65fa22d32bd63e80005e7bf807b2c91624e6824`、plan SHAは`ff442f59f9012af6932974469fc5b2fbcb08afc3e8dd9cba4a480a9cc5f36f6a`、1,527 sourceを固定した。[PR #546](https://github.com/sophiria1225/AI-/pull/546)の同head push/PR両CI成功後、独立run treeで起動した。開始snapshotは194台帳/2,389束縛であり、その後のglobalを遡及しない。

各条件はactor＋focus共有80呼出し、450,000 logical input+output tokens、1,800作業秒、API80。全6合計は最大480呼出し・2,700,000 tokens・API480・評価6件。所有serverは最大6時間、18:00 JSTの期限を維持する。通知を含む実入力はnative計数と送信を一致させ、失敗・unknown・非適用も全条件の費用と公式評価へ残す。

閉鎖後の独立検算待機は10:46:43 JST、図作成待機は10:47:14 JSTに各一度だけ開始した。待機の開始は監査PASSや図完成を意味しない。collectorと固定独立reviewが閉鎖してからだけ実図を作り、失敗時は元記録を残し自動再試行しない。ユーザーの継続指示に従い、通常会話で止めず明示停止に従う。原稿本文はユーザーが執筆する。

[固定仕様](P136_whole_task_late_obligations.md)／[開始記録](../../reports/P136_execution_start_20261027.json)／[出所と検証](../../reports/P136_execution_start_validation_20261027.json)／[P135閉鎖結果](P135_findings.md)。

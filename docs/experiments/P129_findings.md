# P129: 全6条件閉鎖、出力修復は発動せず

2026-10-26 22:20 JSTから27日01:07 JSTまでに、既知CSV 1課題×off/feedback/repair×固定seed57/157の全6条件を評価・回収した。各方式は **1/2成功**。seed57は全方式で作業時間切れ・usage1件不明、seed157は全方式で成功・295,152 logical input+output tokensだった。feedback拒否・修復提案・実送信修復・保存確認済み修復はすべて0。固定development gateは **false** で、総token削減や修復の有効性は実証されていない。

## 全6条件

| Seed | Mode | 公式評価 | 全仕事token | 不明usage | model呼出し | 実API | 終了理由 |
|---|---|---|---:|---:|---:|---:|---|
| 57 | off | 失敗 | 219,344既知小計 | 1 | 19 | 82 | model呼出中の作業時間切れ |
| 57 | feedback | 失敗 | 219,344既知小計 | 1 | 19 | 82 | model呼出中の作業時間切れ |
| 57 | repair | 失敗 | 219,344既知小計 | 1 | 19 | 82 | model呼出中の作業時間切れ |
| 157 | repair | 成功 | 295,152 | 0 | 23 | 104 | 完了宣言 |
| 157 | feedback | 成功 | 295,152 | 0 | 23 | 104 | 完了宣言 |
| 157 | off | 成功 | 295,152 | 0 | 23 | 104 | 完了宣言 |

順序は固定計画の実行順。各方式の既知小計は514,496 token、unknown1、42 model呼出し、186 API。全6条件では1,543,488既知token＋unknown3、126 model呼出し、558 API、6公式評価。未実施・未評価・元監査エラー・機構契約停止は0。費用にはactorとfocus、要約、失敗、notice、回復を含み、cached inputを差し引かない。

主比較repair対feedback、補助比較repair対offのどちらも成功損失0・成功改善0。共通成功はseed157の1対だけで、各295,152 token、差0である。全cohortの費用には不明があるため、総費用差を0と確定しない。事前gateの`paired_successful_token_difference`もcohort全費用既知を要求する定義なのでnullのまま保持する。既知の共通成功部分集合の差0と区別する。

## 介入が起きなかった範囲

seed57の対象write checkは各方式0。公開観測の監視状態は3集合の列挙完了、metadata72件、欠落0まで到達していたが、対象書込を送る前にmodel呼出中の時間上限へ達した。seed157は各方式1件の対象write checkがあり、元の内容が公開証拠と整合する`supported`だった。保存返答と、その後の削除が記録され、修復は不要だった。この監視判定は公式task successと別の尺度である。

両seedを通じてfeedback block・repair proposal・content変更を伴うsent repair・typed成功返答と保存根拠まで確認したstrict repairは全0。通常complete-cache hitはseed57各5、共通のexplicit field要求はseed157各72（partial hit12）。これらを出力修復の成果へ加算しない。自動region変換は全条件で無効。介入0の試行から修復の意味保存、品質改善、費用削減を評価し切れたとは言わない。

## 固定条件と閉鎖監査

実行head `35640e5a447f99f182293e6e26033b25c640061c`、plan SHA `f2d546c56b568b3c8b11a2b785ec10b6c93c5f8dea9b3d9a9395c677d091168f`。各80共有model呼出し・450,000 logical tokens・1,800作業秒・120 API、全6評価、所有server最大6時間を固定した。共通guide、ordinary complete cache、explicit joined fields、full compact receipt、rolling separate checkpointを維持し、deleteには介入しない。[比較仕様](P129_whole_task_output_grounding.md)と[開始記録](../../reports/P129_pipeline_once_start.json)を保持する。

閉鎖後の独立再計算は79,576 checks PASS。全6枠、agent/focus費用、元wireと実送信typed payload、nonce、公開根拠monitor、notice、全役割・unknown、開始時予約台帳182件/2,157束縛、所有server停止を確認した。純粋な公開monitorは固定実装を共有し、rollingの完全request再構成は固定producer auditorへ依存する。別アルゴリズムによる契約証明やhidden評価本文の検証ではない。公開版はprivate path/check識別文字列を省き、元結果・check集合・source集合のSHAと件数を保持する。

server壁時計は9,982.062秒。cell/program/control/grounding時間は重なるため加算せず、速度優位を主張しない。元collector資料・監査・図は同bytesで保存し、実験・元監査・rendererの再実行はしない。結果公開に追加model/API/evaluator/tokenizerは0。

## 採否と次の境界

全使用量既知、普通feedbackに対する全体と共通成功の費用減、共通成功上のstrict repair発動という事前条件を満たさない。通常の出力根拠検証の校正であり、新規技術・一般品質維持は未成立。P127の保存CSV矛盾や過去の成功記録を今回の修復効果へ移して計上しない。同じ既知1課題の2seedを独立2課題とも扱わない。

今回の不成立を理由にseed探索、同条件の追加反復、弱い対照への変更は行わない。後続P130はP129結果を読む前に固定した予約で、その運用状態・未実施を別に記録する。原稿はユーザーが執筆する。

[全6条件](../../materials/20261026_p129_results/conditions.csv)／[元集計](../../materials/20261026_p129_results/summary.json)／[図](../../materials/20261026_p129_results/figures/README.md)／[元監査](../../reports/P129_comparison.json)／[独立監査の公開集約](../../reports/P129_closed_independent_audit_20261026.json)／[server会計](../../reports/P129_server_session.json)。

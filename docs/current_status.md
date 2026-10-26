# 現在の研究状態：P129全6条件閉鎖、通常修復の介入なし

## 最新運用：P130起動前失敗、P131は開始後の停止を確認

P130は01:07 JSTにport検査でmodel本体・task処理前に停止した。約3時間8分の空白後、P131固定2条件を04:15:31 JSTに起動したが、開始後の運用metadataは`stopped`である。全条件完了やactor生成を断定せず、元記録を保持して停止原因・実行範囲を確認する。途中の成否・usage・生成内容は未読。

閉鎖済み原稿資料はP129まで整備済み。新規性、一般的な精度維持と全仕事token削減の最終目標は未達。P128の片seedや共通成功subsetを全体効果へ一般化しない。原稿はユーザー担当。通常会話で作業を止めず、明示停止へ従う。[時点付き経過](experiments/P131_execution_status_20261027.md)。

以下はP129公開時点の記録。P130の未確認事項は上記の起動前失敗診断で更新し、元失敗を保持する。

P129は2026-10-27 01:07 JSTに全6評価、所有server停止、collector、独立監査・図生成を完了。各mode1/2成功、seed57全失敗・各219,344既知token＋unknown1、seed157全成功・各295,152 token。全体は1,543,488既知token＋unknown3、126 model呼出し、558 API、6評価。共通成功費用差0、総費用差null、固定gate false。元監査エラー0・契約停止0、独立監査79,576 checks PASS。

[所見](experiments/P129_findings.md)／[全件資料](../materials/20261026_p129_results/README.md)／[図](../materials/20261026_p129_results/figures/README.md)／[独立監査集約](../reports/P129_closed_independent_audit_20261026.json)。seed57は対象write check0、seed157は各1で元内容supported。feedback拒否・修復の全段階は0で、通常cache/explicit fieldを修復効果へ数えない。

固定head `35640e5a447f99f182293e6e26033b25c640061c`、1,182 sources、各80共有呼出/450k tokens/1800作業秒/120 API、全6評価・server6時間。主比較はrepair対普通feedback、offは補助品質対照。単一既知課題×2seedで、新規性・一般品質・全仕事token削減は未成立。

## 後続の運用確認

P130予約queueは01:07 JSTに起動試行1回後`failed_no_retry / P130_closed_collection_not_complete`で終了した。全4枠の閉鎖は確認されていない。model生成の有無や原因はqueue markerだけで決めず、運用metadataから確認する。元失敗を保存し、元queue/prepare/wrapper/collectorを重複起動しない。P130固定head `8d60aaedac3ccdb4d2f5cca760574f3ea5c13507`、CSV1×inventory off/on×seed57/157、共通feedbackという条件を変更しない。[予約](../reports/P130_continuation_reserved_20261026.json)。

P128は全16閉鎖済みで各6/8、成功損失1/改善1、unknown2、gate false。[P128所見](experiments/P128_findings.md)。旧phaseと混ぜず、通常receipt/出力検証/inventoryを新規性と言い換えない。

通常会話では作業を止めず明示停止へ従う。P128開始181/2,156、P129予約182/2,157、P130予約183/2,158の台帳snapshotを保持する。新globalを凍結runへ適用しない。旧run/prep/source/失敗記録を編集・rebaseしない。原稿はユーザー担当、未見12課題は別確認計画まで未閲覧。[再開入口](../RESUME.md)／[次の作業](next_actions.md)。

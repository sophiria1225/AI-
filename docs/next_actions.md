# 次の作業：P129全件結果を保持し、P130運用失敗を確認する

## 最新運用：P130起動前失敗、P131は開始後の停止を確認

P130は01:07 JSTにport検査でmodel本体・task処理前に停止した。約3時間8分の空白後、P131固定2条件を04:15:31 JSTに起動したが、開始後の運用metadataは`stopped`である。全条件完了やactor生成を断定せず、元記録を保持して停止原因・実行範囲を確認する。途中の成否・usage・生成内容は未読。

閉鎖済み原稿資料はP129まで整備済み。新規性、一般的な精度維持と全仕事token削減の最終目標は未達。P128の片seedや共通成功subsetを全体効果へ一般化しない。原稿はユーザー担当。通常会話で作業を止めず、明示停止へ従う。[時点付き経過](experiments/P131_execution_status_20261027.md)。

以下はP129公開時点の記録。P130の未確認事項は上記の起動前失敗診断で更新し、元失敗を保持する。

1. P129全6閉鎖、各mode1/2成功、介入0、unknown3、全体gate falseを保持する。元cohort・元監査・collector・rendererを再実行しない。共通成功差0と総費用差nullを区別する。
2. P130予約queueの失敗markerと起動範囲を運用metadataから確認する。全4評価を完了済み扱いせず、元失敗/固定sourceを残す。再実行や条件変更は行わず、必要な運用対応を具体化してから別記録へ分離する。単一serverを共有し、通常会話は停止扱いにしない。
3. 公開結果・実図・独立監査のhash/全枠/unknownを確認し、最新mainとglobal台帳を用いて別results treeからPR/両CI/公開/Project同期まで進める。各reserved snapshotは不変。R32/R33の履歴を保持する。
4. 10/27 06時頃までに主要実験と全件資料をまとめる。通常機能の校正を新規性とせず、同じ課題の2seedを独立課題数へ換算しない。成功損失・unknownを除外せず、弱い対照や盲目的seed追加へ退かない。
5. 原稿はユーザーが執筆する。未見12課題は固定確認計画前に開かず、生成task code・課題値・認証・推論/evaluator本文を公開しない。実験終了と研究目標の達成を区別する。

[現在](current_status.md)／[P129所見](experiments/P129_findings.md)／[全6条件](../materials/20261026_p129_results/README.md)／[P128所見](experiments/P128_findings.md)／[再開入口](../RESUME.md)。

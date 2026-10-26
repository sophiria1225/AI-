# 再開の入口：P132全2条件閉鎖、採用基準未達

## 最新：P132全2条件閉鎖、実提示2回でも両失敗

P132は2026-10-27 05:11 JSTに全2評価・所有server・collector・独立監査を閉鎖した。offは171,013 token・API120上限で失敗、onは213,642既知token＋usage1件不明・API47・時間上限で失敗した。共通成功0、正確な総費用差null、固定gate false。inventory捕捉/実提示はoff1/0・on2/2。契約停止・元監査エラー0、独立監査56,861 checks PASSを方式採用と混同しない。[全件所見](docs/experiments/P132_findings.md)／[全2条件・図](materials/20261027_p132_results/figures/README.md)。

所有modelは停止済みで、追加model cohortは未起動。開始186台帳/2,231束縛と後続globalを分離し、元run/prep・P130/P131失敗・unknownを保持する。一般品質維持と全仕事token削減、新規性の最終目標は未達。通常会話を停止指示と扱わず、次は閉鎖証拠の有限診断と主張範囲の整理を進める。新model比較は別の有限計画・source/CI・全件採否を固定する。原稿はユーザー担当。

## 以下は過去時点の運用記録

## 最新運用：P132の最初のactor送信を04:27 JST頃に確認

P132は04:26:12 JSTに開始し、preflight/activationを通過。rootが最初のactor要求ファイルの作成とmodel slot処理中を確認した。時点付きの進行確認であり、全2条件の完了や品質・費用の改善ではない。要求本文・生成内容・task成否・usageは未読。同じ既知CSV1課題×seed57×inventory off/on、server最大5,400秒・06:00 JSTまでの固定比較を進める。[開始記録](docs/experiments/P132_execution_start_20261027.md)。

P132開始snapshot186台帳/2,231束縛と、その後のglobal台帳を区別する。P130/P131の失敗と約3時間の空白を保持し、凍結run/prepを変更しない。閉鎖後は全枠・unknownを残して監査・図・費用比較をまとめる。原稿はユーザー担当で、新規性、一般精度維持と全仕事token削減の最終目標は未達。通常会話で止めず明示停止へ従う。

## 過去の運用記録：P130/P131の生成前失敗

P130は01:07 JSTにport検査でmodel本体・task処理前に停止した。約3時間8分の空白後、P131固定2条件を04:15:31 JSTに起動したが、04:16 JSTに旧lease検査が新supervisor名を拒否してpreflightで停止した。所有serverは停止済み、actor生成・tokenizer count・task API・評価は0。元記録を保持し、新P132 attemptの修正を別に準備する。task成否・usage・生成内容は未読。

閉鎖済み原稿資料はP129まで整備済み。新規性、一般的な精度維持と全仕事token削減の最終目標は未達。P128の片seedや共通成功subsetを全体効果へ一般化しない。原稿はユーザー担当。通常会話で作業を止めず、明示停止へ従う。[時点付き経過](docs/experiments/P131_execution_status_20261027.md)。

以下はP129公開時点の記録。P130の未確認事項は上記の起動前失敗診断で更新し、元失敗を保持する。

P129は2026-10-27 01:07 JSTに全6枠・所有server・collector・独立監査・図生成を閉鎖した。off/feedback/repair各1/2成功。seed57は全方式失敗・219,344既知token＋usage1不明、seed157は全方式成功・295,152 token。feedback/repair介入0、共通成功差0、総費用差は不明、固定gate false。[所見](docs/experiments/P129_findings.md)／[全件資料](materials/20261026_p129_results/README.md)／[図](materials/20261026_p129_results/figures/README.md)。独立監査79,576 checks PASSと方式採用を区別する。

P130予約queueは01:07 JST、起動試行1回後に`failed_no_retry / P130_closed_collection_not_complete`で終了した。これは全4評価の完了記録ではなく、model生成の有無や失敗原因をこのqueue markerだけで断定しない。元失敗を保持し、運用metadataを確認する。元queue/wrapper/prepare/collectorや独立reviewを再実行しない。通常の質問は停止指示ではなく、明示停止へ従う。

凍結headはP128 `0c29b754b23c8ca97ead6e9319661395b6c603a9`、P129 `35640e5a447f99f182293e6e26033b25c640061c`、P130 `8d60aaedac3ccdb4d2f5cca760574f3ea5c13507`。各run/prepは編集・rebase禁止。公開は最新mainから別results treeで行う。P128開始181台帳/2,156束縛、P129予約182/2,157、P130予約183/2,158のsnapshotを保ち、後から増えるglobalを過去runへ適用しない。

P128は全16閉鎖済み、各6/8でも成功損失1/改善1・unknown2・全体gate false。[P128所見](docs/experiments/P128_findings.md)。旧phaseを今回の反復へプールしない。P129は普通feedback対repairが主比較、off補助、同じCSV1課題を2seedで反復した通常校正である。

主要実験の目安は10/27 06時。未知を0にせず、失敗・未実施を全枠保持する。単一local serverを重複起動しない。新比較は別の有限計画・強い対照・source/CI・全件会計を固定し、同条件の盲目的追加やseed探索を行わない。原稿はユーザー担当。未見12課題は確認計画前に開かず、生prompt・reasoning・生成task code・課題値・認証・evaluator本文を公開しない。

[現在](docs/current_status.md)／[次の作業](docs/next_actions.md)／[P130予約](reports/P130_continuation_reserved_20261026.json)。

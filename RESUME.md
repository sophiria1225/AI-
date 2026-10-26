# 再開の入口：P129閉鎖、P130予約の失敗記録を確認

P129は2026-10-27 01:07 JSTに全6枠・所有server・collector・独立監査・図生成を閉鎖した。off/feedback/repair各1/2成功。seed57は全方式失敗・219,344既知token＋usage1不明、seed157は全方式成功・295,152 token。feedback/repair介入0、共通成功差0、総費用差は不明、固定gate false。[所見](docs/experiments/P129_findings.md)／[全件資料](materials/20261026_p129_results/README.md)／[図](materials/20261026_p129_results/figures/README.md)。独立監査79,576 checks PASSと方式採用を区別する。

P130予約queueは01:07 JST、起動試行1回後に`failed_no_retry / P130_closed_collection_not_complete`で終了した。これは全4評価の完了記録ではなく、model生成の有無や失敗原因をこのqueue markerだけで断定しない。元失敗を保持し、運用metadataを確認する。元queue/wrapper/prepare/collectorや独立reviewを再実行しない。通常の質問は停止指示ではなく、明示停止へ従う。

凍結headはP128 `0c29b754b23c8ca97ead6e9319661395b6c603a9`、P129 `35640e5a447f99f182293e6e26033b25c640061c`、P130 `8d60aaedac3ccdb4d2f5cca760574f3ea5c13507`。各run/prepは編集・rebase禁止。公開は最新mainから別results treeで行う。P128開始181台帳/2,156束縛、P129予約182/2,157、P130予約183/2,158のsnapshotを保ち、後から増えるglobalを過去runへ適用しない。

P128は全16閉鎖済み、各6/8でも成功損失1/改善1・unknown2・全体gate false。[P128所見](docs/experiments/P128_findings.md)。旧phaseを今回の反復へプールしない。P129は普通feedback対repairが主比較、off補助、同じCSV1課題を2seedで反復した通常校正である。

主要実験の目安は10/27 06時。未知を0にせず、失敗・未実施を全枠保持する。単一local serverを重複起動しない。新比較は別の有限計画・強い対照・source/CI・全件会計を固定し、同条件の盲目的追加やseed探索を行わない。原稿はユーザー担当。未見12課題は確認計画前に開かず、生prompt・reasoning・生成task code・課題値・認証・evaluator本文を公開しない。

[現在](docs/current_status.md)／[次の作業](docs/next_actions.md)／[P130予約](reports/P130_continuation_reserved_20261026.json)。

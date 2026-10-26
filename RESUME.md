# 再開の入口：P128閉鎖、P129実行・P130予約を維持

P128は2026-10-26 22:20 JSTに全16枠・所有server・collector・独立監査・図生成を閉鎖した。各6/8成功でも対応課題の成功損失1/改善1がある。unknown usage計2、全体費用差はnull、固定gate false。元結果を再実行せず[所見](docs/experiments/P128_findings.md)／[全件資料](materials/20261026_p128_results/README.md)／[実図](materials/20261026_p128_results/figures/README.md)から読む。独立監査109,295 checks PASSは方式採用と別。

P129の固定6条件は22:20 JSTに元queueから開始した。P130固定4条件の予約も維持する。通常の質問・進捗確認は停止指示ではなく、実験を継続して応答する。明示停止だけを全稼働・待機へ反映する。現在の稼働は既存運用monitorのmetadataで確認し、閉鎖前の成否や費用を見て条件を変えない。元wrapper/prepare/queue/collectorを重複起動しない。

凍結headはP128 `0c29b754b23c8ca97ead6e9319661395b6c603a9`、P129 `35640e5a447f99f182293e6e26033b25c640061c`、P130 `8d60aaedac3ccdb4d2f5cca760574f3ea5c13507`。各run/prepは編集・rebase禁止。公開は最新mainから別のresults treeで行う。P128開始181台帳/2,156束縛、P129予約182/2,157、P130予約183/2,158のsnapshotを保ち、新globalを過去runへ適用しない。

P129はCSV1×3arm×2seed、普通feedback対repairが主比較、offは補助。全480model呼出/2.7M tokens/720 API/6評価・server6時間。P130は同CSV1×2arm×2seed、共通feedbackでinventoryの効用を測り、全320呼出/1.8M tokens/480 API/4評価・server4時間。P130はP129全件閉鎖後かつ02:00 JSTまでの開始に限定する。主要実験の目安は10/27 06:00 JST、単一local serverを重複起動しない。

未知を0にせず、失敗・未実施を全枠保持する。quality gain、同じ成功での費用減、安いfailureを分ける。通常receipt/CSV検証/inventoryを新規機構と言い換えない。原稿はユーザー担当。未見12課題は別の固定確認計画まで開かず、生prompt・reasoning・生成task code・課題値・認証・evaluator本文を公開しない。

[現在の状態](docs/current_status.md)／[次の作業](docs/next_actions.md)／[P129予約](reports/P129_continuation_reserved_20261026.json)／[P130予約](reports/P130_continuation_reserved_20261026.json)。

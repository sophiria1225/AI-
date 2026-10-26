# 現在の研究状態：P128閉鎖、P129実行・P130予約を継続

P128は2026-10-26 22:20 JSTに全16枠の評価、所有server停止、回収、独立監査と図生成を完了した。full/discloseとも6/8成功だがseed57で成功損失1、seed157で改善1。unknown usageは各1（計2）、総費用差は不明、固定gateはfalse。独立監査109,295 checks PASS、元監査エラー0、契約停止0。既知小計の差をtoken削減と断定しない。

[所見](experiments/P128_findings.md)／[全件資料](../materials/20261026_p128_results/README.md)／[図](../materials/20261026_p128_results/figures/README.md)／[公開独立監査](../reports/P128_closed_independent_audit_20261026.json)。共通成功5対の費用1,078,497→936,656は部分集合の結果。seed157の全費用849,469→833,441という所見を、seed57の脱落と不明費用を含む全体へ一般化しない。

## 後続の固定比較

P129は22:20 JSTに既存queueから開始した（開始metadataだけ確認、途中結果未読）。CSV1課題×off/feedback/repair×seed57/157、head `35640e5a447f99f182293e6e26033b25c640061c`、1,182 sources、push/PR両CI成功。主対照は普通feedback、offは補助品質対照。各80共有呼出/450k tokens/1800作業秒/120 API、全480呼出/2.7M tokens/720 API/6評価、server6時間。delete非介入、未知は修復しない。[予約](../reports/P129_continuation_reserved_20261026.json)。

P130はP129全6枠回収・所有server停止後の一度起動を予約済み。CSV1課題×inventory off/on×seed57/157、共通feedback。head `8d60aaedac3ccdb4d2f5cca760574f3ea5c13507`、1,205 sources、両CI成功。全320呼出/1.8M tokens/480 API/4評価、server4時間が06:00 JSTまでに収まる02:00 JST以前だけ開始する。両armでcaptureし、onのみ次actorへ一度表示。値やscalar長を出さず、普通inventoryの校正で新規性・提示時機優位は未主張。[予約](../reports/P130_continuation_reserved_20261026.json)。

通常の質問・進捗確認で実験を止めず、明示停止を全稼働・待機へ反映する。元wrapper/queue/collectorを重複起動しない。P128開始snapshot181台帳/2,156束縛、P129予約182/2,157、P130予約183/2,158は不変。後から増えたglobal registryを凍結runへ適用しない。P128/P129/P130の旧run/prepは編集・rebaseしない。P128の最初3行を運用表示した事実と、その前にP130の4条件を選定した経過は元仕様に保持する。

P123/P125/P126/P127の結果・失敗を今回へプールしない。採択に向けた新規性、一般品質維持、全仕事token削減の最終目標は未達。未見12課題は別確認計画まで未閲覧。原稿はユーザーが執筆し、こちらは全件・再現根拠を整える。[再開入口](../RESUME.md)／[次の作業](next_actions.md)。

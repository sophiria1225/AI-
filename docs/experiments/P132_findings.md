# P132: inventoryは提示されたが、両条件失敗・採用基準未達

P132は2026-10-27 05:11 JSTに全2評価・所有server停止・collector・独立監査を閉鎖した。保持変数の一覧を出す通常機能はonで実際に2回提示されたが、off/onとも公式課題評価は失敗した。固定development gateはfalse。一般的な品質維持、全仕事token削減、新規手法の実証には至っていない。

| 条件 | 公式成功 | logical token | usage不明 | model呼出し | 実API | 捕捉 / 実提示 | 停止理由 |
|---|---:|---:|---:|---:|---:|---:|---|
| inventory off | 0/1 | 171,013（確定） | 0 | 14 | 120 | 1 / 0 | API上限 |
| inventory on | 0/1 | 213,642（既知小計） | 1 | 18 | 47 | 2 / 2 | model呼出中の作業時間上限 |

全体は384,655既知token＋usage1件不明、32 model呼出し、167実API、2評価。共通成功は0、正確な全体差・共通成功差はnullである。APIが少ないことを成功仕事の削減へ読み替えず、未知を0にしない。[全2条件](../../materials/20261027_p132_results/conditions.csv)／[集計](../../materials/20261027_p132_results/summary.json)／[会計の定義](../../materials/20261027_p132_results/INTERPRETATION.md)／[図](../../materials/20261027_p132_results/figures/README.md)。

契約停止・元監査エラーは0。independent reviewは56,861 checks PASSで、全役割の費用、unknown、typed捕捉、実入力提示、source/台帳、閉鎖を照合した。PASSは方式採用やtask成功を意味しない。純粋formatter/checker/公開monitorを共有し、生成Pythonやproducer auditorの再実行、独立評価本文の読取は行っていない。[公開安全な監査集約](../../reports/P132_closed_independent_audit_20261027.json)。

最初のinventory実提示は第8呼出し。提示前の7 requestは保存bytesが一致した。第1–6応答のraw messageはtool-call ID各1件だけ異なり、それ以外の差は0、第7のfocus応答はrawでも一致した。元の厳密hash不一致は保持し、ID正規化後の比較と区別する。これは全Python/API状態・因果効果・品質の同値証明ではない。[全呼出しhash比較](../../reports/P132_closed_prefix_hash_diagnosis_20261027.json)／[提示前ID差の限定診断](../../reports/P132_closed_prefix_identifier_diagnosis_20261027.json)。

固定headは`71aaa1c5290000902f2cc51ce406f3b47eeb7327`、plan SHAは`16982554d89ba5d64dc47545c74e956604a9a1d22aa1ddcab645d9282ca1b50a`、source1,242件。同じ既知CSV1課題・元の先頭seed57・共通feedback、explicit field、rolling separate、full receiptsを使った。両条件でcheckpoint採用時の捕捉を行い、onだけ次のactor入力へ一度提示する。各80共有model呼出し・450k tokens・1,800作業秒・120 API、server最大5,400秒を事前固定した。[仕様](P132_whole_task_checkpoint_inventory_resumption.md)。

P130はport検査でmodel本体前に停止。約3時間8分後のP131も旧identity検査が新supervisor名を拒否し、tokenizer count・actor生成・task API・評価前に停止した。両失敗と運用空白を残し、P132では新source/plan/CI/名前空間でexact supervisor path/hash、所有PID、model provenance、idle、残leaseを接続した。開始snapshot186台帳/2,231束縛に、後のglobalを遡及適用しない。[P131経過](P131_execution_status_20261027.md)／[P132開始時点](P132_execution_start_20261027.md)。

次の判断は、同じ失敗条件のseed追加や根拠のない再試行ではなく、公開依頼と実行済み証拠だけによる取得需要・完了条件・時間上限の有限診断である。成功維持と総token削減の中心主張は未達のまま保持する。P123の通常要約比較やP128の共通成功subsetと混ぜず、原稿はユーザーが執筆する。追加モデル比較には別の条件・強い対照・有限予算・source/CI・全件採否の固定が必要である。

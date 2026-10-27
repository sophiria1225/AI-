# P137：P136で未実施だった4条件の追加観測

2026-10-27。ユーザーの実験継続指示に基づき、P136全予定6行と所有実行資源を閉じた後に設計者が選んだ有限な追加観測である。P136は評価済みraw57が1件、未完IDS57が1件、未実施4件だった。原記録、未知費用、未評価、gate falseは変更しない。この文書は準備仕様であり、実験開始の証拠ではない。

P136の停止ではSIGALRM handler不在による終端記録欠落をsourceと手書きfixtureで再現したが、実workerの終了signal自体は保存されていない。P137は新worker入口をTimeoutErrorへ変換するcontextで包み、既存adapterの例外処理・未知usage保存・後始末へ到達させる。時間上限や要求を緩める修正ではなく、terminal使用量が戻る保証でもない。新worker終了値を別に保存する。[運用修正](../inference_timeout_recording_20261027.md)を参照。

## 固定する4条件と意味

| 実行順 | model seed | 方式 | 解釈 |
|---:|---:|---|---|
| 1 | 57 | entity_fields | 主対照が未完了のため単独追加観測 |
| 2 | 157 | entity_fields | 同P137内の3方式比較 |
| 3 | 157 | ids_only | 同P137内の主対照 |
| 4 | 157 | raw_anchor | 同P137内のraw対照 |

選択理由は元の未実施状態であり、seedの追加探索や成功条件の再実行ではない。P136の完了済みraw57・中断済みIDs57を再実行・補充しない。4条件は同じ既知CSV1課題の条件であり4独立課題ではない。予約12課題の要求・データ・評価本文は読まない。

モデル・量子化・sampling・world seed・初期raw guide/tools・通常rolling checkpoint・typed観測・通知selector・予算・公式評価をP136と同じにする。checkpoint後の次actor一度だけへ、IDs側は未完ID、fields側は同じ選択規則のIDと不足項目を渡す。queryや公開snapshot handleは追加しない。JSON body上限2048 bytesと固定heading43 bytesは別に数え、全messageのnative countに含める。公開資料から私有値を除く処理は、モデルへ渡す原観測を変更しない。

新しいのは実行namespace、未実施4条件に限った順序と集計範囲、catchableな期限signal、worker終了記録である。機構のP136由来versionは保持する。新modelや新しい効果仮説へ変更しない。

## 予算と閉鎖

各条件はactorとfocus共有80モデル要求、450000 logical input＋output tokens、1800作業秒、環境API80回。setup120秒、cleanup180秒、idle確認60秒、公式評価180秒を別管理する。4条件で最大320モデル要求、1800000 tokens、API320回、評価4回、要約機会12回。別呼出しrollingは閾値16384、直近2turn、最大3機会、fresh最小3を維持する。時間通知・payback・server predict time limit・client graceを追加しない。

batch12000秒、server lease14400秒、outer15600秒。終了目安18:00 JSTにouter全量が収まる場合だけ開始するため、最終開始時刻は13:40 JST以前となる。準備が間に合わなければ予算を勝手に縮めず未実施とする。元記録の上書き、自動再試行、同条件の救済seedは行わない。

新sourceとplan、P136公開・元閉鎖証拠、現在の開始台帳snapshotを凍結し、同じheadのpushとPRのCI成功を確認してから一度だけ開始する。P136の開始194台帳/2389束縛はその時点のまま保存し、新開始snapshotと取り違えない。新main thread入口から、actor/focusのtimeout→unknown保存→cleanup→idle確認→評価→次条件の経路を合成テストする。cleanup失敗、APIの効果不明、backendがidleへ戻らない場合は停止し、残りを未実施として残す。

## 集計と判断

P137全4行、失敗・未評価・未実施・audit error・unknownを表示する。cached inputを差し引かず、actor・focus・通知・失敗を含む全仕事費用を扱う。未知があれば正確な総費用・比較差はnullで、安い失敗や空の共通成功群を改善と呼ばない。

主比較fields対IDs、補助比較fields対rawは、同じP137のseed157だけを記述する。seed57 fieldsは別の単独行で保持する。P136のraw57/未完IDs57との合算でP136 gateを通さず、別sourceの試行を独立反復として足さない。`development_gate_met`は常にfalse、`scientific_adoption_evaluated`、`prior_results_pooled`、`original_P136_gate_replaced`もfalseとする。これは採用を判定できる均衡比較ではない。

全4条件の閉鎖後、機構未到達・品質喪失・費用不成立なら、この経路を追加seedや同条件反復で救済しない。正方向でも既知1課題・同cohort1seedの記述的証拠に留め、一般的品質維持、新規性、レター採択を確定しない。原稿本文はユーザーが執筆し、こちらは結果・図表・技術差と限界を整える。

# P142実行開始：既知4課題・seed157のTR/TDO比較

2026-10-28 09:04:26 JSTに固定8条件を開始した。rootの09:06:32 JSTの運用確認では完了0/8、最初の `threshold_recursive` 条件が実行中だった。最初のactor responseと次のrequestのfile存在を確認した記録であり、応答本文・途中成否・最終課題成功を確認したものではない。この資料はその観測時点だけを表し、公開時点の残件数や現在の処理状況を表さない。rootの非閲覧申告と、公開担当が固定運用記録・完了済み事前検査だけを読んだ範囲は区別する。

実行前のnative事前計数14件（初期actor8、focus4、checkpoint後actor2）が成功し、09:05:27 JSTにactivationが完了した。事前検査のモデル生成・環境API・評価器呼出しは0で、本実験開始後の生成とは区別する。各課題の両方式の初期入力は一致し、planの1,783 sourceとplan自身を含む1,784件をactivationへ束縛した。[事前計数](../../reports/P142_initial_checks.json)と[activation](../../reports/P142_activation_v01.json)は完了済み原記録と同一bytesである。

対象は元の既知4課題すべて、モデルseed157・world seed42、固定8条件とした。seed157は過去の別cohortでも使用しており、未使用seedや未見課題による独立確認とは扱わない。P141の既知Task 4・seed57の観測を選定根拠とする事後的な開発比較である。旧P123/P138〜P141の行は合算・置換せず、保留12課題の要求・データ・正解を読まず、その全12課題の確認を置き換えない。

| 方式 | 要約時点 | 第二要約 |
|---|---|---|
| TR (`threshold_recursive`) | native入力16,384 tokens以上 | 再帰要約 |
| TDO (`threshold_delta_object`) | 同じnative入力閾値 | 旧summary保持＋明示的object deltaをhostで合成 |

元の課題順を維持し、奇数課題はTR→TDO、偶数課題はTDO→TRで実行する。順序は無作為化しておらず、ホスト・キャッシュ・順序効果を除外したとはしない。P141のinference/controllerを変更せず用い、初期入力・tools・初回focusを共通にする。最大2機会、機会間の新規完了turnは3以上、直近2turn保持、focus出力上限4,096、合成後8,192文字・各field合計32 itemsを維持する。比較対象は第二要約の表現とpromptの組であり、各要素単独の効果や全軌跡の一致は主張しない。

各条件はactor/focus合算80呼出し、logical入力＋出力450,000 tokens、作業1,800秒。環境API上限は課題順に160/80/80/80とし、両方式で同じにする。全8条件の上限は640 model calls、3,600,000 logical tokens、800 API要求、8公式評価、16focus機会。setup/cleanup/idle/evaluationは両方式とも60/60/30/60秒で、作業時間は短縮しない。8条件予約16,080秒、batch16,200秒、server lease18,000秒を固定した。CLI内の事前検証もworker外側1,920秒に含まれるため、内部各段階を上限まで使うと早期打切りとなり得る。失敗・未完了も保存し、この余白不足を理由に時間を延長しない。

最新起動09:15 JST、モデル実行の絶対終了14:15 JST、集計とTeX改訂は15:00 JST締切である。これらは実行の上限と成果物の期限であり、成功・削減・全条件完遂の保証ではない。途中の科学的結果で条件を選び直さず、通常メッセージでは停止せず、明示停止・予算・異常時停止に従う。

全8予定枠、失敗・非発動・未評価・未実施・unknownを残す。全roleのlogical入力＋出力を計上しcached inputを控除しない。unknown usageをnative計数や出力予約値で補完しない。公式最終評価はactorに返さない。開発上の判定は、全8評価済み・usage既知・audit errorなし、TR成功課題の成功喪失なし、共通成功あり、全4対と共通成功対の両方で総費用減、完全な契約・会計、共通成功上の既知object focusと差分利用actor、発動した比較のcanonical prefix一致を必要とする。strict prefixは別に報告する。transport-ID対応の一致は隠れ状態や意味の同一性の証明ではない。**開始時点の判定結果は未確定**であり、開発gateが成立しても一般的品質保証・未見課題への汎化・手法の新規性を確定しない。

固定headは `fd54c691c7cd2cfabd1c8c279ef0e6f710dfb773`、[source PR568](https://github.com/sophiria1225/AI-/pull/568)のmergeは `03073dba89fa1be831d6cb5009e6592e495d4003`。plan SHAは `122a8fe0b4fe723dba21cc20e5f053e960ac542e9d1180dcccff8703ad4697e5`。rootのsource検証記録は3,208 tests成功を報告し、独立確認した同headの[push CI](https://github.com/sophiria1225/AI-/actions/runs/40605694196)と[PR CI](https://github.com/sophiria1225/AI-/actions/runs/40605699990)はattempt 1・各accounting-and-syntax全13steps成功である。初回local検査は新worktreeにignoredの固定依存checkoutがなかったため4 import errorsで停止し、その原記録を保持した。固定依存を配置しsourceを変えずに全検査を再実行した。CI成功は科学的効果の証明ではない。

開始snapshotの208台帳・2,730束縛を保持し、公開資料の追加で元snapshotを置き換えない。実験用prep/runのsource、旧結果、原稿v01には変更しない。

[固定仕様](P142_threshold_object_confirmation_20261028.md)／[開始証拠](../../reports/P142_execution_start_20261028.json)／[公開資料検証](../../reports/P142_execution_start_validation_20261028.json)／[開始資料の束縛](../../reports/P142_execution_start_provenance_20261028.json)／[P141閉鎖結果](P141_findings.md)。

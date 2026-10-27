# P141実行開始：既知Task 4のobject-delta時点診断

2026-10-28 02:15:37 JSTに固定3条件を開始した。rootの02:18:41 JSTの運用確認では完了0/3、最初の `threshold_recursive` 条件が実行中だった。最初のactorのrequest・response・raw response fileの存在は02:18:41 JSTに確認した。model slotの処理中状態は先の02:17:35 JSTの観測であり、後の記録へ引き継いだ値であって02:18:41の再照会ではない。この開始資料は二つの時刻付き運用観測を合わせたものとなる。これは固定された観測時点の開始記録であり、公開時点の残件数や現在の処理状況を表さない。本文・usage・途中成否を読まなかったというrootの記録と、公開担当が固定記録だけを読んだ範囲を区別する。先のfile名filterが既知の下位directoryを拾わなかったため、直接の存在確認で補った経緯も保存した。

8件のnative事前計数（初期actor3、focus3、checkpoint後actor2）が成功し、02:16:12 JSTにactivationが完了した。事前検査中のモデル生成・環境API・評価器呼出しは0で、本実験開始後の生成とは別である。初期3方式の入力は一致し、planの1,736 sourceとplan自身を含む1,737件をactivationへ束縛した。[事前計数](../../reports/P141_initial_checks.json)と[activation](../../reports/P141_activation_v01.json)は実行作業木の完了済み記録と同一bytesで公開する。

対象は既知課題1件、元Task 4だけで、新cohortのslot 1に対応する。P140の失敗を見た後に選んだ診断であり、元の既知4課題比較や保留12課題の確認を縮小・置換しない。過去の成功行を合算して全4成功と扱わず、P140の失敗・unknown・固定gateを保持する。

| 固定順 | 方式 | 再要約時点 | 第二要約 |
|---|---|---|---|
| 1 | `threshold_recursive` | native入力閾値 | 再帰要約 |
| 2 | `threshold_delta_object` | native入力閾値 | 旧summary保持＋object delta |
| 3 | `exposure_delta_object` | 累積再提示量Eと直前focus費用C | 旧summary保持＋object delta |

全方式seed57、最大2checkpoint機会。初期入力・tools・初回focus、parser、output上限4,096、合成8,192文字・各field合計32 itemsを維持する。両object方式は同じ第二delta指示を使い、hostが旧summaryと新objectを合成する。TDO→EDOは時点の記述的比較、TR→TDOは表現とpromptをまとめた比較であり、object指示単独の効果を分離しない。同じseedでも全軌跡の一致を仮定しない。

各条件は80 model calls、450,000 logical入力＋出力tokens、1,800作業秒、80 environment API要求。全3条件の上限は240 model calls、1,350,000 tokens、240 API要求、3公式評価、6focus機会。setup/cleanup/idle/evaluationは各120/180/60/180秒、server lease9,000秒、batch7,200秒、pipeline9,600秒。latest launchは03:00 JST、モデルの絶対期限は05:30 JST、結果処理は06:30 JST目標とする。これらは上限・目標であり、期待費用や完了保証ではない。通常メッセージでは実行を止めず、明示停止・予算・異常時停止に従う。

全3予定枠、失敗・非発動・未評価・未実施・unknownを残す。actor/focusの全logical入力＋出力を計上し、cached inputを控除しない。未知usageをnative入力計数やoutput予約値で補完しない。時点比較は最初のpredicate差より前のprefixと、その同じ境界での実dispatch差を分ける。最初の差でfocusが未送信なら後の都合のよい境界を選ばない。後の第二focus時点やcutoffが一致することは要求せず、厳密一致と検証済みtransport-ID対応を別に記録する。

この診断は採用判定を行わず、`scientific_adoption_evaluated=false`、全比較gateと`development_gate_met=false`を結果にかかわらず固定する。仮に全3条件が成功しても、一般的品質維持・全4課題での削減・独立確認・新規性の成立とはしない。保留12課題は未読で、原稿本文はユーザーが担当する。

固定headは`5cab33a2e239f3e6d90e63e32c54ba0764b1c594`、[source PR563](https://github.com/sophiria1225/AI-/pull/563)のmergeは`e91b2daf2d68af4a30af85f67a8bf450424f2b33`。plan SHAは`5dd2581f4aae9fc8831768018a9fe00835c74e8b4f8506d0b77bda5f155ac18d`。rootのsource検証記録は3,139 unit tests成功、同headの[push CI](https://github.com/sophiria1225/AI-/actions/runs/40547922703)と[PR CI](https://github.com/sophiria1225/AI-/actions/runs/40547969966)は各accounting-and-syntaxの全13steps成功を確認している。CIは科学的効果の証明ではない。開始snapshotの205台帳/2,652束縛は、後の公開台帳追加によって置換しない。

[固定診断仕様](P141_object_timing_diagnostic_20261028.md)／[開始証拠](../../reports/P141_execution_start_20261028.json)／[開始資料の束縛](../../reports/P141_execution_start_provenance_20261028.json)／[P140閉鎖結果](P140_findings.md)。

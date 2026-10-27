# P137: P136で未実施だった4条件の追加観測

既知CSV1課題について、entity_fields/seed57 → entity_fields/seed157 → ids_only/seed157 → raw_anchor/seed157の全4条件を保持する。P136の評価済みraw/seed57と中断したIDs/seed57は再実行せず、P136の6行・欠測・判定を置換しない。P136の値と合算しない。

主比較はseed157のids_only対entity_fields、補助比較は同じseed157のraw_anchor対entity_fieldsだけである。どちらも同一の新cohort内の1組の記述的比較であり、seed57のentity_fieldsは対照のない単独結果として別掲する。方式別の全行集計は不均衡（1/1/2条件）なので、その合計同士を方式間の効果比較に使わない。`comparison_costs`はseed157の1組だけ、`seed57_unpaired`はseed57だけを含む。`by_replication["1"]`の比較は0組で、exact費用はnullとなる。

初期guide、CODE_TOOLS、通常rolling checkpoint、typed monitor、表示規則はP136と同じ。追加query toolや公開handleはない。同じclosed pending-ID列を条件に、共通selectorが最大16行の同じprefixを選び、entity_fieldsだけが各IDの不足fieldを加える。独立runの実際のID列や軌跡が同一とは仮定しない。通知は採用checkpoint後の次actorだけに付け、archiveとfocusへ再注入しない。JSON本文は2048 UTF-8 bytes以下、見出し43 bytesを含む追加上限は2091 bytesで、全入力費用に含む。

全actor/focus、失敗、要約、通知のlogical input+outputを数え、cached inputを差し引かない。未実施・未評価・監査不能・unknown usageをゼロにしない。既知小計と報告件数、unknown件数、欠測条件数を併記し、未知・欠測があれば全体exact費用はnull。共通成功、品質増減、双方失敗、未評価を分け、共通成功が空なら共通成功の費用差はnullとする。

列挙open/closed/unknownを区別する。open/unknownの詳細行0は義務なしや成功を意味しない。capture、実dispatchへの通知、累積ID行、field行を別々に数える。ID行はunique entity数ではなく、field行はentity_fieldsだけにあり、queryは全方式0。観測完備は公式課題成功ではない。保存Python・評価器・モデル・tokenizerはこの集計で再実行しない。

この追加観測では採用判定を行わず、`development_gate_met`と`scientific_adoption_evaluated`は常にfalse。結果が良くてもP136の元gateを修復したことにはしない。単一既知課題、seed157の1組とseed57の単独結果から一般品質維持、新規性、timing優位を主張しない。SIGALRMを通常の記録可能な経路へ戻す修正とworker終了状態の保存は新実行に適用するが、P136の元失敗を変更しない。

観測・要約・入力計数はwork内、work/evaluation/setup/cleanupはserver時間と重なるので加算しない。raw prompt・reasoning・API値・認証・評価本文・private pathを公開しない。

[全4条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P137_comparison.json)／[server](../../reports/P137_server_session.json)。

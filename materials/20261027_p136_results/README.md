# P136: 同じ初期interfaceからの未完了IDと不足fieldの提示

既知CSV1課題×固定seed57/157×raw_anchor/ids_only/entity_fieldsの全6条件を保持する。P135の閉鎖結果を受けた別の科学比較であり、P135の結果・失敗・unknownを変更しない。

全方式は元P123の同じ初期guideとCODE_TOOLSを持つ。追加query toolはない。主比較は同じ未完了IDのみの提示に対する、そのIDごとの不足fieldの追加である。通常rawは追加通知なし。同じclosed pending-ID列を前提に、最大descriptorと最大maskで予約する共通selectorが同じ最大16行のprefixを選ぶ。安いID側へ余分な行を詰めず、実countsやmask長で行選択を変えない。共通の表示にsnapshot handleを入れず、実行scope・要件・観測prefixへの私有bindingは維持する。独立runの全軌跡が同一と仮定せず、実際の入力差を閉鎖後に確認する。

採用された通常の別呼出しrolling checkpoint直後、次actorへ一度だけ2048 UTF-8 bytes以下の通知を付ける。archiveやfocusへの通知再注入はしない。公開実装に束縛したshow_liked_playlistsの補助readは対象sourceを変更しないものとして扱うが、その返答値を対象unionへ追加しない。追加API・値の補完・書込み・削除を自動実行しない。

全actor/focus、失敗、要約、通知のlogical input+outputを数え、cached inputを差し引かない。未実施・未評価・監査不能・unknown usageはゼロにしない。未知があればinput/output/cachedを含むexact totalsはnull。全体と共通成功の費用、品質増減と双方失敗を分ける。

列挙のopen/closed/unknownを区別し、open/unknownの不足件数はnull、詳細行は0とする。これは義務なし・成功という意味ではない。capture、実dispatchへの通知、累積ID行、実missing-field行を別に数える。ID行はids_onlyとentity_fields双方にあり、field行はentity_fieldsだけにある。両行数はunique entity数ではない。query数は全方式で0を要求する。保存native要求・typed event・sidecarを再構成する監査で、保存Python、評価器、モデル、tokenizerを再実行しない。観測完備は公式課題成功ではない。

固定gateは全6評価とknown usage、主比較とraw対照への成功喪失なし、主比較の全体と非空共通成功のtoken低下、raw対照の全体token低下、主比較共通成功上の実field行提示、全契約・会計の成立を要求する。同条件の追加seedで判定を救済しない。単一既知課題・2seedの改善だけで一般品質維持、新規性や先行手法への優位を証明したとはしない。

観測・要約・入力計数はworkに含まれ、work/evaluation/setup/cleanupはserver時間と重なる。加算しない。raw prompt・reasoning・API値・認証・評価本文・private pathは公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P136_comparison.json)／[server](../../reports/P136_server_session.json)。

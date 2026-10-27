# P135: 観測済み対象と未充足fieldの提示、全6条件

P134のqueue失敗・モデル未起動の記録を残し、同じ科学条件を新しいP135名前空間で実施する運用復旧である。旧試行の成否や費用へ混ぜない。

既知CSV1課題×固定seed57/157×raw_anchor/counts_only/entity_fieldsを全件保持する。主比較のcounts_onlyとentity_fieldsは同じguide、明示query、API/モデル予算と証拠を持ち、採用checkpoint直後の次actorへの一度の自動提示だけを変える。raw_anchorは元P123のguide/toolsを保ち、同じ観測とcapture費用を負担する。追加API・値の補完・書込み・削除は自動実行しない。

全actor/focus、失敗、問い合わせ返答、通知を含むlogical input+outputを数え、cached inputを差し引かない。未実施・未評価・監査不能・unknown usageはゼロにしない。未知があればinput/output/cachedを含むexact totalsはnull。全体と共通成功の費用、品質増減と両失敗を分ける。安い失敗を効率改善とはしない。

対象列挙はopen/closed/unknownを分ける。open/unknownの不足件数はnullであり、空の不足一覧や成功を意味しない。件数・entity行は観測typed返答のみから再構成し、古いhandle・別実行・別要件を受理しない。capture件数、実dispatch actorへの提示、提示entity行、明示queryを区別する。提示の内容・値・生成codeは公開しない。原Python状態を再実行せず、保存native要求・typed event・sidecarを突合する監査である。archive/focus不変は同arm通常履歴にtransient noticeを混入しない意味であり、raw対照とのfocus bytes一致ではない。明示query返答は通常有料履歴としてfocusへ入り得る。各armのrun_idが異なるため、scopeに束縛したsnapshot handleも異なる。初期main pairの同一入力を、checkpoint後の通知共通部分まで同じバイト列であるという主張へ広げない。最初の入力差をentity内容だけへ因果帰属しない。

固定gateは全6評価とknown usage、主比較とraw対照の両方で成功損失なし、主比較の全体と非空共通成功のtoken低下、raw対照の全体token低下、主比較共通成功上の実entity提示を必要とする。全契約・会計の成立も必須。1課題・2seedsで一般品質や新規技術を証明したとはしない。

観測・問い合わせ・要約・入力計数はworkに含まれ、work/evaluation/setup/cleanupはserver時間と重なる。加算しない。raw prompt・reasoning・API値・認証・評価本文・private pathを公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P135_comparison.json)／[server](../../reports/P135_server_session.json)。

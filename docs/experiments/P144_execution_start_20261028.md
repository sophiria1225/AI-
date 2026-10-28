# P144開始記録と原稿v03の入口

2026年10月28日14:21:42 JST、固定した既知4課題×3方式の12条件を開始した。保存された14:23:41.213870 JSTの運用記録ではbatchはrunning、完了0/12、最初の通常再帰要約条件の要求fileが1件、応答fileが0件だった。rootは別時点の14:23:57 JSTにslot 0のprocessing=trueを報告した。これは要求file存在と運用状態の記録であり、生成内容・課題成功・費用の確認ではない。**観測時点の記録であって、閲覧時点の残件数を表さない。** 公開担当は途中の成否・usage・生成本文を読んでいない。rootの非閲覧申告を独立に証明したものでもない。

ユーザーの新しい依頼に従い、有限の実験をバックグラウンドで継続しながら、原稿を並行して作成する。通常のチャット発話では停止せず、明示的な停止指示・固定予算・異常時停止に従う。モデル実行は本日23:15 JSTまで、結果処理と原稿の締切は本日23:59 JST。これは上限・期限であり、全条件完遂や肯定的成果を保証しない。READMEやRESUMEに残る「P141で実験停止」「原稿はユーザー担当」等は当時の指示を記録した履歴であり、この再開・原稿作成依頼を現在の指示として優先する。

[原稿v03 PDF](../../papers/202610_letter/harness_efficiency_20261028_v03/manuscript.pdf)／[編集用TeX・図一式ZIP](../../papers/202610_letter/harness_efficiency_20261028_v03/source_bundle.zip)／[原稿の根拠と範囲](../../papers/202610_letter/harness_efficiency_20261028_v03/EVIDENCE.md)。v03は閉鎖済みの通常ハーネス制御の実測を扱う校正稿で、P144の途中結果を含まず、成功を先取りしない。本文・文献4頁＋英文1頁、著者情報は仮欄、投稿は未実施。旧v01/v02も保持する。[公開PR573](https://github.com/sophiria1225/AI-/pull/573)は取り込み済みである。

## 固定した比較

|方式|第二要約の扱い|
|---|---|
|TR：通常再帰要約|旧要約と新履歴から全体を生成し直す|
|APP：object delta追記|旧要約を保持し、明示した差分objectをhostが合成する|
|UPD：明示的状態更新|各fieldの旧全項目をkeep/update/deleteで一度ずつ指定し、addを加えてhostが単一要約を作る|

共通の初回・再度閾値はnative入力8,192 tokens、最大2機会、再度は3 fresh turns、直近2 turns保持。初回の構築規則を共通にし、第二要約のsystem指示と出力契約を比較する。同seedでも各runの実際の入力・軌跡の一致を仮定せず、保存prefixで別に判定する。状態更新は上限内で原子的に適用し、不正な提案は現在のviewを保持して既知の有料focus費用を残す。古い情報の正しさや意味保存を保証する契約ではない。

元の既知4課題すべてを各方式1回、model seed257・world seed42で実行する。seed257は57/157の次の固定増分として選び、結果を見たseed探索をしない。課題順の方式順序はTR/APP/UPD、APP/UPD/TR、UPD/TR/APP、TR/UPD/APP。無作為化・完全な順序均衡ではない。保留12課題の要求・データ・正解は読まず、その確認を置き換えない。旧cohortとは合算しない。P143から継承した8k閾値は事後選択であり、seedと作業予算も変わるため、phase間の差を状態更新の因果効果としない。

各条件のactor＋focusは80呼出し・logical入力＋出力450,000 tokens・作業1,800秒。API上限は写真160、他3課題各80で、3方式共通。全12上限は960 model calls、5,400,000 logical tokens、1,200 API要求、12公式評価、24要約機会。setup/cleanup/idle/evaluationは60/60/30/60秒、batch24,240秒・server24,900秒。最遅起動16:15・モデル絶対終了23:15を固定し、条件削除や再試行で救済しない。[仕様と判定条件](P144_state_update_comparison_20261028.md)／[先行技術との範囲](../checkpoint_state_update_prior_scope_20261028.md)。

## 開始前の検証と結果の扱い

native事前計数21件（初期actor12・focus6・採用後actor3）は成功し、14:23:32.543896 JSTにactivationを完了した。事前検査自体のモデル生成・環境API・評価器呼出しは0で、本実験の呼出しと区別する。[事前検査](../../reports/P144_initial_checks.json)と[activation](../../reports/P144_activation_v01.json)は安全な集計記録を原本と同一bytesでコピーした。入力本文はコピーしない。

固定実行headは `6868405b1764104fb75ad77d55cf5791a9da08c6`、plan SHAは `890d43434cc4125dd16fa610e4f5c8fb052306c940aaaa0940fb983942ca595f`、1,861 source（activationはplan自身を含め1,862件）。[source PR572](https://github.com/sophiria1225/AI-/pull/572)の同headで[push CI](https://github.com/sophiria1225/AI-/actions/runs/40636990449)と[PR CI](https://github.com/sophiria1225/AI-/actions/runs/40637057356)は各13 steps成功。rootのlocal記録は3,328 tests成功を報告する。期限経過で失敗した旧合成6検査の原bytes・失敗記録を残し、その検査だけ時計を固定するrunnerを加えた。実験の時計や期限は変更しない。これらは実装・運用の検証であり、科学的効果の証明ではない。

開始時の212台帳・2,836束縛とsnapshot SHA `fd5c186f74f08c712486b80cabc9494f5e295e299d965608ba66340268fb06e6` を保持する。原稿公開後のglobal213台帳・2,884束縛を開始値へ遡及しない。run/prep・旧台帳・過去結果は変更しない。

全12枠、失敗・非発動・未評価・未実施・unknownを残し、cached inputを控除せず全roleの既知logical入力＋出力を計上する。UPD対TRとUPD対APPは別々に判定し、全体の開発判定には両方の条件を要求する。共通成功上で、正味state変更かつ古い項目変更が既知usageのactorへ実送信されることが必要で、編集提案や採用だけでは足りない。未知費用を0・native予約値で補完しない。**開始時点の費用・品質・判定は未確定。** 既知4課題の事後開発比較であり、新規性・一般品質維持・投稿採択を確立しない。

[開始の数値証拠](../../reports/P144_execution_start_20261028.json)／[公開範囲の検証](../../reports/P144_execution_start_validation_20261028.json)／[資料の束縛](../../reports/P144_execution_start_provenance_20261028.json)。

# P139準備：再要約時点と第二checkpoint表現の2×2開発比較

起動前の固定仕様。実装と合成結合検査を実施し、source固定・全体検査・両CI・native preflightを経て起動する。本文の作成時点ではモデル実験は未開始。P138全12条件の成功喪失・unknown・gate falseと元sourceは変更しない。原稿本文はユーザーが執筆する。

## 問いと範囲

P138では提案の再要約時点は変化したが、通常4/4成功に対し候補3/4成功だった。課題4の通常方式と候補はともにAPI送信76件でも、候補はファイル作成・account削除・完了通知の送信に至らなかった。保存metadataだけの診断であり、認証情報やsummary内容の誤りが原因とは断定しない。

次は要約時点と要約表現を全4組合せで比較する。累積指標の効果と、単なる既存summary保持の効果を区別するため、通常16k＋deltaも最初から含める。append/delta自体を新技術と呼ばず、この組合せの効用と限界を検証する。4既知課題・seed57の開発診断であり、P138の独立追試、未見評価、統計的非劣性、一般的意味保存・新規性の証明ではない。

## 固定する16条件

- 既知課題順：34d9492_1、3c13f5a_1、60d0b5b_1、6104387_1。
- mode：threshold_recursive、threshold_delta、exposure_recursive、exposure_delta。
- thresholdは通常16,384入力tokens、exposureはP138と同じ既知paid-prefixのE≥直前paid-focus C。初回triggerは全方式16k。
- model seed57（role内call番号による既存seed導出）、world seed42、同じMiniMax-M3 IQ4_XS・llama.cpp b11669・ctx65536/parallel1/KV q8_0、同じguide/tools/初期packet/actor sampling。model/viewへ新mode名や事前結果を追加しない。
- 同課題内の順序はmode列を課題slot−1だけ左回転し、各条件を1回実行する。旧対照の再利用・cohort間pool・seed探索・失敗の再試行・途中結果での差替えは行わない。
- seed157はP133/P137で同じ通常interfaceのCSVがAPI80・focus0で停止した既知証拠があり、介入地点のあるseed57を開発診断として選ぶ。この選択は結果を見て選んだ既知範囲であり、独立確認とは表示しない。

## 第二機会だけの処置

全方式でkeep2、fresh3、**最大2機会**。採用数の上限ではない。未送信・不正・非短縮でも第三機会は追加しない。第一focusのpacket・schema・parser・採用処理は同じ。第一summaryが採用されたときだけ第二機会のdelta処置を行い、初回不採用なら通常経路として非介入を記録する。

recursiveは前summary＋新eligible rawを統合して置換する。deltaは第二focusの入力に同じ前summaryをread-only参考として含め、新rawについてのdeltaを生成させる。採用時は前summary noteを同bytesで保持し、その後にdelta noteを置く。過去記述の正確さ・現在性・矛盾解消を保証しない。

deltaを含む全summary bodyの合計serialized文字数を8,192以下、fieldごとの合計item数を32以下、各itemを2,048文字以下にする。片方ずつ上限を与えない。元summary noteと追加note、system/task/budget/toolsをすべて含む全actor viewを同じ状態でnative計数し、厳密に短い場合だけ採用する。文字数をtokenに換算しない。canonical bodyは `json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)`、2fragment時は同じ設定で `[previous_value, delta_value]` を直列化し、そのPython文字数を合計上限とする。旧noteは `checkpoint_kind=ordinary_fallible_summary`、delta noteは `ordinary_fallible_delta_summary`、いずれも `semantics_verified=false` と `summary` を持つuserメッセージで、別の見出しは追加しない。body上限とは別に両noteのwrapper費用を含む全入力をnative計数する。

known-paid invalid/oversize/nonshrinkingは旧checkpointとcutoffを保持し、費用を全計上してCを更新、Eをreset。未送信はC/Eとcheckpointを変更せず機会だけ消費。unknownと追加計数失敗は元費用・pending状態を保持して停止する。採用済みでも次actorが送信されなければ、実介入として数えない。

全方式が同じshadow計数を行う。複数summaryの全noteを保持し、新eligible rawだけを除いてnative差を測る。raw archiveを変更しない。max2でもactor後の露出会計を継続し、summary note数に対応する新helperと独立再構成で境界を検証する。元モジュールのglobal monkeypatch、max2をmax3へ偽装するconfig、旧sourceの上書きを行わない。

## 費用・期限

各セル80 all-role model要求、450,000 logical input+output tokens、1,800作業秒。setup/cleanup/idle/evaluationは120/180/60/180秒。APIは課題順160/80/80/80で全4方式共通、focus出力上限4,096、同じ構造採用条件を使う。

全16セル上限：1,280 model要求、7.2M logical tokens、1,600 API要求、16評価、最大32 focus機会。server lease43,200秒、batch40,000秒、外側pipeline timeout44,400秒。**最新起動2026-10-27 20:00 JST、モデルの絶対終了2026-10-28 08:00 JST**。実行中の期限延長は行わず、後処理のみ有限のcleanup枠で閉じる。P138の期限は変更しない。wrapperはpipeline44,400秒、audit900秒、session120秒、report120秒を上限とし、起動・各stage・子process待機で明示停止を確認する。異常時の子cleanupは330秒、最後の強制停止待機15秒。単一namespaceで一回だけ実行し、失敗を上書き・自動再試行しない。

## 固定する判定の骨格

主utility比較はexposure_delta対threshold_recursive。追加の対照はexposure_recursiveとthreshold_delta。全16枠を保持し、各比較で対応する全4pairの評価と費用既知、成功喪失なし、全課題費用減、非空共通成功上の費用減、共通成功上の実介入を要求する。主gateと、両追加対照も満たす組合せgateは別表示する。未知や不完全な会計を0へ補完しない。費用と品質のtradeoffを、失敗した安い方式への単純劣位/優位と誤読しない。

全4組合せの行と、各timing内のrepresentation比較・各representation内のtiming比較を保存する。delta方式の成功だけで累積制御が必要とは主張しない。各comparison gateは対象全4pairの評価・既知費用、両方式の2種類の会計が完全・契約失敗なし、監査errorなしを必要とする。representation-onlyは既知usageを持つdelta actorの実送信と下記prefix一致、timing-onlyは対応する基準predicateと判断が違った地点での実送信、主diagonalはそのいずれかを実介入とする。全4pairの費用が既知でない場合は全課題・共通成功の差をともにnullにし、共通成功0件もnullとする。16枠全体に不明がある場合は各方式の厳密総費用をすべてnull、既知小計は別表示する。組合せgateは主比較とexposure_recursive、threshold_deltaの両対照比較のANDとする。残る2edgeも保存する。

同じtiming内で表現差へ限定して解釈するには、第二focus前までの実request/role/status/output-hash列・第一採用summaryのhashと採用位置・cutoff・E/C・summary集合hashがtyped canonical JSONで一致したことを確認する。空証拠、第一採用なし、第二機会なし、未知terminalは一致とせず、request内のopaque IDも正規化しない。表現だけの比較ではdelta発動の全pairでprefix一致を必要とする。同seedのみで一致を仮定しない。不一致・非発動も除外せず保持し、完全な因果効果や意味保存とは呼ばない。

## 保存と起動条件

P138結果PR556 merge377ce984475ee68bb59191d46218c433c28205f1を基点とする。global201台帳/2,545束縛と旧固定sourceを保持する。新規module/新namespaceだけで実装し、全体検査・独立レビュー・同headのpush/PR両CI・全preflight・所有server不在確認後に、一度だけ起動する。保留12課題、private reasoning、DB/評価本文、保存生成programは開かず実行しない。

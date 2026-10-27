# P140実行開始：第二delta要約の出力形式を明示する開発比較

2026-10-27 22:46:56 JSTに固定12条件を開始した。22:52:14 JSTの運用monitor確認では完了0/12、最初の `BOC_P140_01_THRESHOLD_RECURSIVE` が実行中だった。最初のactorのrequest・response fileが存在し、SHAだけを記録した。本文・usage・成否は読んでいない。これは観測時点の開始記録であり、公開時点の残件数や全条件の結果ではない。

18件のnative事前計数（初期12、focus4、第二採用後actor view2）が成功し、activation完了を確認した。この事前検査中のモデル生成・環境API・評価器呼出しは0。本実験の開始後の生成と区別する。planのsourceは1,675件、activationはそのplan自身を含む1,676件を束縛する。

既知4課題を `threshold_recursive`、`exposure_delta`、`exposure_delta_object` の3方式で比較する。model seed57、最大2回のcheckpoint機会、初期入力・tools・初回focus・parser・上限は共通。候補だけが第二delta focusのsystem instructionに「単一JSON objectを返し、hostが配列に合成する」と明示する。配列の自動修復、文字数や項目数上限の緩和、追加機会や再試行は行わない。閉鎖済みP139の構造診断後に選んだ開発比較であり、新規手法・独立追試・一般的品質維持の証明ではない。

各条件は80 model calls、450,000 logical input+output tokens、1,800作業秒。API上限は課題順160/80/80/80。12条件の予約上限は960 model calls、5.4 million tokens、1,200 API要求、12評価、24 focus機会。server lease30,000秒、batch28,200秒、pipeline30,600秒を固定し、モデルの絶対期限は2026-10-28 08:00 JST。結果処理は08:55、資料は09:00を目標とする。上限は期待費用や完了保証ではない。通常メッセージでは停止せず、明示停止・予算・異常時停止に従う。

候補と通常閾値対照、候補と未変更E/delta対照を別gateで判定する。各比較は全4pairの評価・費用既知・会計整合、成功喪失なし、全課題と非空の共通成功群での全仕事token減、共通成功群での既知object-prompt送信とdelta提示を必要とする。未変更E/deltaとの帰属条件では、厳密prefixを併記した上で、検証済みtransport IDの全単射だけを許す対応も調べる。引数・観測値・要約・request・E/C状態などを正規化しない。主比較だけが通り補助比較が未達なら限定的効用と両対照採用未達を分け、主比較自体の否定へ読み替えない。基準は結果後に緩めない。

全12予定枠と失敗・未実施・unknownを残し、cached inputを控除せずactor/focusの全費用を数える。旧cohortは合算せず、P139の結果・厳密prefix判定を変更しない。保留12課題は未読。原稿本文はユーザーが担当する。

固定source headは`827298fa4219aa4e500d604dfb771f6fe6b815c8`、[source PR560](https://github.com/sophiria1225/AI-/pull/560)のmergeは`872048e5b53f29a38b947ed06a14ce88b5c2586a`。plan SHAは`635730afeb8baa5c34d80ddb12a9f85b7823944b4c72064c0a46621327d163dc`、開始snapshotは203台帳/2,592束縛。固定headの[push CI](https://github.com/sophiria1225/AI-/actions/runs/40514411940)と[PR CI](https://github.com/sophiria1225/AI-/actions/runs/40514449435)は各accounting-and-syntax jobの全13steps成功。CI成功は科学的効果の証明ではない。後の公開台帳追加を開始snapshotへ遡及適用しない。

[固定仕様](P140_checkpoint_delta_envelope_draft_20261027.md)／[開始証拠](../../reports/P140_execution_start_20261027.json)／[開始資料の束縛](../../reports/P140_execution_start_provenance_20261027.json)／[P139閉鎖結果](P139_findings.md)。

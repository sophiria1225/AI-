# P139実行開始：再要約時点と第二checkpoint表現の2×2開発比較

2026-10-27 18:22:59 JSTに固定16条件を開始した。18:25:06 JST時点では最初の `BOC_P139_01_THRESHOLD_RECURSIVE` が実行中、完了0/16。最初のactorのrequest・raw response・response file保存を確認し、同観測時点の単一model slotが処理中であることも確認した。first callがその時点でも処理中という意味ではない。この記録は観測時点の運用証拠であり、公開時の現在の残件数や全件の結果ではない。途中の成否・使用量・生成内容を読んでいない。

22件のnative事前計数（初期16、focus4、第二採用後actor view2）はすべて成功、activationを完了した。事前計数の追加モデル生成は0で、その後に本実験の生成を開始した。

既知の写真・精算・返金・CSVの4課題を、`threshold_recursive`、`threshold_delta`、`exposure_recursive`、`exposure_delta`の4方式で比較する。world seed42、model seed57。同じMiniMax-M3 IQ4_XS、固定llama.cpp b11669、ctx65536、parallel1、KV q8_0を用いる。初期guide/tools/actor入力、初回16,384入力token閾値、直近2turn保持、fresh3、全費用を共有する予算は共通。全方式で最大2機会を実際に設定し、不正・非短縮・未送信でも第三機会を追加しない。

2回目の時点は通常16k閾値と、P138と同じ累積再提示指標Eが直前の既知paid-focus費用Cに達する規則を比較する。表現は前summaryを統合して置換するrecursiveと、第一summaryが採用された場合に限り第二focusでdeltaを生成して旧noteを保持する方式を比較する。第二focusの入力にはどちらも同じ前summaryを参考として含める。deltaを含む全bodyの文字数・field item数を合計上限で制限し、全note・system/task/budget/toolsを含むactor入力をnative計数して厳密に短い場合だけ採用する。第一summaryが不採用ならdelta処置なしとして残す。

各条件は80共有model要求、450,000 logical input+output tokens、1,800作業秒。API上限は課題順160/80/80/80。全16条件の予約上限は1,280 model要求、7,200,000 tokens、1,600 API要求、16評価、最大32 focus機会。これらは上限であり、期待実費や終了予測ではない。server lease43,200秒、batch40,000秒、pipeline timeout44,400秒。最新起動は2026-10-27 20:00 JST、モデルの絶対終了期限は2026-10-28 08:00 JST。全件閉鎖後の監査・図表と判定整理は同日09:00 JSTを目標とし、途中結果で判定を先取りしない。

主utility比較はexposure_delta対threshold_recursive。組合せgateは、exposure_recursiveおよびthreshold_deltaの両対照にも同じ条件を要求する。各比較は全4pairの評価と費用既知、成功喪失なし、全課題と非空の共通成功群の全仕事token減、完全な会計、共通成功群での実送信を伴う介入を必要とする。representation-onlyの解釈には第二focus前の保存request/output列・第一採用summary・cutoff・E/Cの一致も要求し、同seedだけで軌跡一致を仮定しない。主gateと組合せgateを分け、残るfactorial比較も保存する。

全16枠で失敗・未評価・未実施・unknownを保持する。不明usageを0や正確値へ補完せず、actorとfocusの全仕事費用を含める。旧結果を対照として再利用せず、P138以前のcohortと合算しない。seed57は既知の介入地点を踏まえて選んだ開発診断であり、独立追試・未見評価・統計的非劣性・一般的意味保存・新規性の証明ではない。append/delta自体を新規技術と主張しない。

固定source headは`a203874f0fafbaa76f76cfab3603eb43c623916f`、実装mergeは`5925713dd307217857e4d18e7813d305bcd9d055`。plan SHAは`e05b7a0fc0128d972cc2a63afe013fd21d28127c3a74ef9632918b2586b17657`、source1,617件、開始snapshot201台帳/2,545束縛。全3,022テストとcompileall、および同headのpush/PR両CIの成功を確認してから起動した。[実装PR557](https://github.com/sophiria1225/AI-/pull/557)／[push CI](https://github.com/sophiria1225/AI-/actions/runs/40479728642)／[PR CI](https://github.com/sophiria1225/AI-/actions/runs/40479755198)。

[固定仕様](P139_checkpoint_representation_draft_20261027.md)／[開始証拠](../../reports/P139_execution_start_20261027.json)／[開始資料の束縛](../../reports/P139_execution_start_provenance_20261027.json)。全16条件と所有serverの閉鎖後に監査・集計する。通常のメッセージや質問では実験を停止せず、明示停止に従う。固定期限・予算・異常時停止は維持する。原稿本文はユーザーが担当する。

# P138実行開始：累積再提示量による要約時期の比較

2026-10-27 14:31:09 JSTに固定12条件を開始した。14:32:49 JST時点で最初の `BOC_P138_01_ROLLING_SEPARATE` が実行中、完了0/12。最初のactor要求の送信記録・要求と応答fileの保存、単一model slotが処理中であることを確認した。この記録はその観測時点の運用証拠であり、全件結果や現在時点の残件数ではない。途中の成否・使用量・生成内容を読んでいない。

既知の写真・精算・返金・CSVの4課題を、16,384入力token閾値、固定3 fresh turns、累積raw-prefix再提示量の3方式で比較する。world seed42/model seed57、初回要約・直近2turn保持・最大3機会・要約prompt・guide/tools・shadow計数・共有予算は共通。使用モデルはMiniMax-M3 IQ4_XS、同じ固定llama.cpp runtimeである。

各条件80共有model calls／450,000 logical input+output／1,800作業秒、API上限160/80/80/80。全12条件の予約上限は960 model calls、5,400,000 tokens、1,200 API、12評価。32,400秒server lease、30,000秒batch上限、lease-end期限10月28日03:00 JST。上限を期待実費・終了予測へ読み替えない。

主gateは16kに対するpaired成功損失なし、全課題と非空の共通成功群の全仕事token減、完全な使用量・計数会計、実送信を伴う判断差。別gateは固定間隔対照に対しても同条件を要求する。主gateだけ通っても累積指標固有の価値は支持されない。失敗・未実行・unknownを残し、過去P123/P133/P137と合算しない。4既知課題・単一seedの開発比較で、新規性・汎化・統計的非劣性は未確立。

固定head `919b34e9c1a50729bbd83527263e21a407b04499`、plan SHA `52ef2cbf864a581f4f3b93500d961f982a5a19b3e40ffb818df8225f487669cb`、source1,563件、開始snapshot199台帳/2,497束縛。全2,934検査とcompileall、同headのpush/PR両CIが成功してから起動した。[実装PR554](https://github.com/sophiria1225/AI-/pull/554)。

[固定仕様](P138_prefix_exposure_draft_20261027.md)／[開始証拠](../../reports/P138_execution_start_20261027.json)／[予備計数](../../reports/P138_prefix_exposure_feasibility_20261027.json)。全12枠・所有server閉鎖後に監査・集計を一度行う。通常メッセージで実行は止めず、明示停止に従う。原稿本文はユーザーが担当する。

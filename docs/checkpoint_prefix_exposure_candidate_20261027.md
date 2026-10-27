# 有料raw prefix再提示量による反復checkpoint：限定試作

既存P123 rollingに対するutility候補。初回16,384、直近2 closed turns、最少3 fresh turns、最大3機会、summary prompt・構造検査・実入力短縮採用・共有予算は維持する。新規性、意味保存、最終成功、償却や競争比は未確立。

3modeは同じcontrollerとshadow計数を使う。`rolling_separate`は既存16k、`fixed_interval`は反復時にfresh3だけ、`prefix_exposure`は反復の16kをR≥Cへ置換する。Cは直前の有料focusの既知入力＋出力。Rはその後の既知有料actorについて、新eligible rawを除く前後のnative入力差のpositive partを累積する。先行summary全文・system/task・直近2turn・budget notice・toolsは除かない。負のraw差も保存し、0へ改竄しない。

初回paid focus前はC未定義なので補助計数をしない。後続actorが既知終端を得た後、同じ最終budget stateを使って計数専用の欠落入力Uを1回計数する。実Wは既存のadmission countとterminal一致で検証する。Uを生成へ送る経路はない。空eligible prefixは差0で追加計数不要。未送信や未知終端はRへ足さず、unknownは停止する。paid focusはinvalid/nonshrinkingでもC更新・R=0、未送信focusではC/R不変。機会消費とfresh間隔は元規則。

追加計数は3modeとも共有work clockに含む。既知actorの後に計数が失敗した場合、その有料response/usageを残し、返ったactionをworkerへ渡さず停止する。これは無料再試行でもunknown usageの0補完でもない。count-only差は実現可能な要約短縮量ではなく、指標である。次summaryの長さ、残り仕事量、後続行動は予測しない。

新sourceは `checkpoint_prefix_exposure.py`（pure指標/trigger/投影）と `prefix_exposure_inference.py`（既存rollingへの接続）。旧frozen sourceは変更しない。後者は既存call・summary・採用処理を再利用し、mode選択をrepeat triggerへ限定する。初期guide/schemaや追加model-visible通知はない。

起動前には、固定したP123全4rolling traceの実prefixで最初の判断差を有限native計数し、差以降の架空summary/費用は作らない。合成検証は失敗・未送信・negative差・count-only非送信・全3modeを扱う。これは実task成功やtoken削減の測定ではない。普通ski-rental型の一般概念を新規性とせず、P133の将来horizon推定と実送信済prefix累積の判断差を比較する。

本試作にonline plan、モデル/API/evaluator/heldoutアクセス、保存生成code実行、旧実験の再監査は含めない。追加finite cohortと予算は別途固定する。

先行比較の範囲：適応的な要約時期の選択自体は、[SelfCompact §3](https://arxiv.org/html/2606.23525v1)と[StateComp §4.2](https://arxiv.org/html/2609.27298v1)に既存方式がある。今回調べる具体差は、意味的な準備状態ではなく、実送信した有効raw prefixの累積再提示量を使う点である。この限定比較は新規性の証明ではない。[通常のski rentalの定義](https://proceedings.neurips.cc/paper_files/paper/2018/file/73a427badebe0e32caa2e1fc7530b7f3-Paper.pdf)とは、次回要約費用が未確定で、要約後にも履歴費用が残り、後続行動と品質も変わる点が異なるため、その競争比を移さない。

[保存入力の有限計数](../reports/P138_prefix_exposure_feasibility_20261027.json)では、CSVのexposureと16kの初回判断差をafter19で確認した。E=22,306、直前focus費用21,419で、元16k方式の次機会はafter22だった。固定間隔方式はafter16で先に分岐する。分岐後の旧軌跡を新方式の後続費用・成功の実測として使わない。最初のtemplate hash参照誤りによる4描画を保持し、修正後22描画を含む合計26 native描画、decode0である。

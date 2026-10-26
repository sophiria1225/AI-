# P129: 全6条件の監査済み集計

既知のCSV課題1件 × off/feedback/repair × 固定seed57/157を全件保持する。独立課題数は1。主対照はfeedback、offは補助の品質対照。通常の公開source検査と内容修復の校正であり、新規技術・一般的品質維持を主張しない。deleteへ介入しない。

全役割の論理input+output、要約、失敗、修復、通知と回復を含める。cached inputは差し引かない。unknown/nullを0に置換せず、input/output/cachedのnested exact totalもunknown usageがあればnull。全体、seed、各対照との共通成功・品質改善・品質損失・両失敗・未評価を別集計する。品質改善を「同じ成功を安く達成した」と読み替えない。

grounding_repair_attemptsは提案、grounding_sent_repairsは内容変更を伴う実送信、grounding_repairsはさらにtyped returnedの成功と公開monitorのbackup支持を確認した修復である。sent/raised、unsent feedback、成功修復、official task successを区別する。普通cache/explicit fieldとCSV修復は別機構である。最終成果の公式成否は修復検査の成否とは別に残す。

固定gateは全6評価・既知費用、両対照からの成功損失なし、feedback比の全体および非空の共通成功費用減、主共通成功上の実成功修復、両機構契約の維持を必要とする。seed別差を必ず示すが、各seed費用減はこのgateの追加条件ではない。安いfailureや未知費用で採用しない。

control bytesはmodel tokenではない。work/program/control/groundingおよびserver/cell/evaluation時間は重なるので加算しない。raw prompt/reasoning/code、CSV内容、認証値、private pathは公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P129_comparison.json)／[server](../../reports/P129_server_session.json)。

# P132: 全2条件の監査済み集計

既知CSV課題1件 × off/checkpoint_inventory × 固定seed57のみの全2条件を保持する。P130のmodel起動前のport bind失敗とP131の旧lease監視によるpreflight前停止を保存し、残り時間の有限枠に合わせた別phaseであり、結果による条件選択やseed探索ではない。両条件に同じfeedback検査、explicit joined fields、通常cache、full compact receipts、rolling checkpointを使う。accepted checkpoint直後の同じinventory取得を両条件に課し、表示条件だけ次のactor入力へ1回加える。通常inventoryの限定的な有用性比較であり、新規機構・一般的品質維持・提示時機の優越を主張しない。

全役割の論理input+output、要約、失敗、通知と回復を含める。cached inputは差し引かない。unknown/nullを0に置換せず、input/output/cachedのexact totalもunknown usageがあればnull。全体、seed、共通成功・品質改善・品質損失・両失敗・未評価を分ける。品質改善を同じ成功の費用削減と読み替えない。

inventory_notice_actor_callsはinventoryを含む実dispatch済みactor入力数であり、snapshot作成やtokenizer計数だけでは増えない。paid unknown dispatchも露出として残すが、費用不明のため採用gateは通らない。capture件数、host wall、request/reply bytesは別に示し、取得や保存の不完全性を0補完しない。metadataは固定trusted collectorの返答と境界hashから監査する。保存Pythonを再実行して値を独立証明したものではない。

grounding feedbackは両条件共通で、repairは無効。unsent feedback、actual API結果、公式task success、inventory/grounding/projectionの契約状態を別に残す。固定gateは全2評価・既知費用、offからの成功損失なし、全体および非空の共通成功費用減、共通成功上の実inventory露出、全機構契約の維持を必要とする。1seedだけの限定比較であり、seedをまたぐ再現性を示さない。

control bytesはmodel tokensではない。work/program/control/capture/groundingとserver/cell/evaluation時間は重なるため加算しない。raw binding names、値、prompt/reasoning/code、CSV、認証値、private pathは公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P132_comparison.json)／[server](../../reports/P132_server_session.json)。

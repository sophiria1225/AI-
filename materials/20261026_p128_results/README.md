# P128: 全16条件の監査済み集計

既知4課題 × full/disclose × 固定seed57/157の全枠を残す。2seedは独立課題数を増やさない。共通guide・join/明示field/完全cache・rolling separateを維持し、自動region変換は無効。通常receipt開示の効率校正であり新規手法の成立ではない。

全jobのagent/focus・要約・失敗・修復・明示read_span再取得を含むtokenを使用する。whole cohort、seed別、同seed共通成功の費用は別集計。cheap failureは品質維持した削減ではない。unknown/nullを0補完しない。input/output/cachedのexact component totalもunknown usageがあればnull。cached inputをlogical inputから差し引かない。

receipt_disclosuresは実dispatchしたagent/focus入力へ露出した固有receipt数、receipt_disclosed_turnsは終了後を含むfinal表示可能数であり区別する。最終turnだけで後続入力がなければ露出0。receipt byte差は最終表示1回のindex差でありtokenや累積節約ではない。API/cache/field/schema/controlも異なる尺度である。work/program/control/lookupおよびserver/cell/evaluation時間は重なるので加算しない。各seedで全体と共通成功のtoken減・成功損失なしを要求する固定gateを維持する。契約失敗・不完全記録・監査エラーも全16枠に残す。

[全条件](conditions.csv)／[集計](summary.json)／[sourceと生成物hash](build_manifest.json)／[監査](../../reports/P128_comparison.json)／[server](../../reports/P128_server_session.json)。raw prompt/reasoning/code/課題値を公開しない。原稿への採用・一般品質・新規性の判断は別である。

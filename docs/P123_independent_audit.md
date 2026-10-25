# P123 閉鎖後の独立集計確認

判定: PASS（公開集計と固定 gate の整合）。実験採用 gate は **false**。終了印の complete を確認してから読取りを開始した。

12/12 条件が独立評価成功、使用量不明 0、全既知費用 2,516,107 logical 入力+出力 tokens。model seed 57、world seed 42、既知4課題、反復1。

| 方式 | 成功 | 全 tokens | model calls | focus calls / tokens | API requests | checkpoint 導入回数（task slot順） |
|---|---:|---:|---:|---:|---:|---|
| single_checkpoint | 4/4 | 893,529 | 86 | 2 / 39,874 | 217 | [1, 0, 0, 1] |
| rolling_separate | 4/4 | 785,656 | 85 | 3 / 59,530 | 216 | [1, 0, 0, 2] |
| rolling_inline | 4/4 | 836,922 | 88 | 0 / 0 | 207 | [1, 0, 0, 2] |

3方式すべての共通成功は全4taskで、共通成功費用は全体費用と同じ。rolling_separate と rolling_inline はどちらも task slot4で2回導入し、反復発動条件は満たす。導入0のtask slot2/3は3方式の token が同一。

| 比較 | token 差 | baseline比 | task slot別差 |
|---|---:|---:|---|
| rolling_inline_minus_single_checkpoint | -56,607 | -6.3352% | [-10497, 0, 0, -46110] |
| rolling_inline_minus_rolling_separate | +51,266 | +6.5252% | [-10497, 0, 0, 61763] |
| rolling_separate_minus_single_checkpoint | -107,873 | -12.0727% | [0, 0, 0, -107873] |

同時要約は単発要約より 56,607 tokens 少ない一方、反復の別呼出し要約より 51,266 tokens 多い。両方の対照を下回る固定条件を満たさず、gate=false は正しい。rolling_separate がこのcohortで最少費用という所見は可能だが、方式一般の優越性や新規性は示さない。

12条件CSV・259モデル要求CSV・247制御判断CSV・24役割費用行・8比較行を、audit report全行とセル単位で照合した。model callからinput/output・API回数・役割費用を別計算し、control eventsから導入回数も別計算した。collector copy、material build manifest、固定helper/plan、閉鎖server/pipelineのhash結合を確認した。元summary/usage/evaluationはhashだけを照合し、評価本文は解釈していない。

公表表現上の注意: 全12成功はこの既知4課題・1反復・seed57での観測であり、一般的な精度維持・非劣性・意味保存の証明ではない。inlineは別summary呼出し0だが、summary生成費用がゼロという意味ではなくagent出力へ含まれる。4task全体で単発より6.3352%減だけを強調し、反復別呼出しより6.5252%増を伏せない。反復別呼出しはlogical tokens最少だが、wall timeまで最速とは限らない。

server wall 8906.032秒、cell full wall合計 8852.811秒。evaluation等はserver/batch内に含まれ、重複加算しない。

README / summary JSON は gate不合格、既知cohort制約、意味保存・新規性未証明を保持しており、確認範囲で誇大な成功宣言は見つからない。

独立確認 252 項目 PASS。モデル/API/評価器追加実行0、課題本文・生成code・推論・要約本文は未読。

- comparison SHA256: `73d55305300ae6cb332213f08f8a813a40ab17f82a9a167e3fbbf1bb17fb6147`
- server session SHA256: `659c6964867ec752a7f82b7f13d1a560619759c2bbab23d36e9f731d2d19df4b`
- 詳細: `/private/tmp/AI_P123_closed_independent_review_20261026.json`

# P127: 全8条件閉鎖、自動region変換は発動せず

2026-10-26 11:45–13:08 JST。固定した既知4課題×2方式を一度実施し、全8条件の独立評価、所有server停止、元監査・集計・collector・閉鎖後の独立再計算を終了した。両方式とも **3/4成功、695,217 logical入力＋出力token**。全4pairのtoken差は0、自動変換も明示field要求も0で、固定development gateは **false**。トークン削減、新規機構の有効性、一般的な品質維持は実証されていない。

## 全件結果

同じ行の数値は両方式それぞれの値。方式は `explicit_joined_fields` と `automatic_region_joined_fields`。全8行の原集計を[conditions.csv](../../materials/20261026_p127_results/conditions.csv)に残す。

| 課題 | 明示field対照の成功 | 自動region方式の成功 | 各方式の全仕事token | 各方式のmodel呼出し | 各方式の実API |
|---|---:|---:|---:|---:|---:|
| Photo | 成功 | 成功 | 119,589 | 14 | 97 |
| Expenses | 成功 | 成功 | 181,952 | 17 | 22 |
| Refund | 成功 | 成功 | 51,043 | 8 | 9 |
| CSV | 失敗 | 失敗 | 342,633 | 29 | 117 |
| 全4課題 | 3/4 | 3/4 | 695,217 | 68 | 245 |

両方が成功した3課題では各352,584 token、差0。失敗CSVの各342,633 tokenも全体費用へ残す。全8条件合計は1,390,434 token、136 model呼出し、490実API、8独立評価。使用量不明・未評価・監査エラーはすべて0。model呼出しとtokenにはagentとfocusの別呼出し要約を含む。

CSVは両方式とも `agent_declared_complete` で終了したが、独立評価は失敗だった。実API117は固定上限120より少なく、P125の「API80で停止」と同じ失敗原因とは断定できない。評価本文・追加テストを読んでこの差を説明したものではない。

## 機構と採否

全132 program（各66）で静的受理、変換、projection lookup、automatic partial hitは0。両方式で共通の明示field要求も0だった。通常complete-cache hitはCSVのみ各72、projection契約停止は0。この通常cacheの使用を自動region方式の成果へ数えない。

固定gateは、全仕事と共通成功群の両方でtokenが減り、対照の成功を失わず、共通成功上で自動projectionが実際に発動し、使用量と機構契約が全件確認できることを要求する。今回の成功損失0・契約停止0は維持する一方、token差0・自動機構発動0のためgateは通らない。明示field機能が使われなかったことも記録し、これを対照から削除して比較を有利にしない。

P126は保存された旧CSV prefixで13取得省略×2記録を確認した限定再生であり、今回のonline効果へ移して計上しない。P123はseed57、P125は単発checkpointとCSV API80等の異なる条件で、今回との一因子比較や反復として混ぜない。

## 固定条件と監査

[事前計画](P127_whole_task_region_projection.md)、[開始記録](../../reports/P127_execution_start_20261026.json)、[元監査](../../reports/P127_comparison.json)、[server会計](../../reports/P127_server_session.json)、[閉鎖記録](../../reports/P127_closure_once_end.json)。実行head `0219f774326e7e4e2fdacc6aaaf0c45ea381cfc0`、plan SHA `49edf3731b6d4caf79ef7b90f84b928cb7269ebb541148687e444c2bb9557bff`、1,142 source filesを保持する。seed157/world42、共通rolling-separate checkpoint、通常join・明示field・完全cache・簡潔receipt・公開schema feedbackを両側へ与えた。

各80 model呼出し・450,000 token・1,800作業秒、API上限Photo160/Expenses80/Refund80/CSV120、全8評価・880 API・所有server6時間という有限枠を変更しなかった。server壁時計は5,013.537秒。作業・program・control・lookup時間は重なるので加算しない。wire bytesはmodel入力tokenとは別尺度である。

[閉鎖後の独立再計算](../../reports/P127_closed_independent_audit_20261026.json)は67,270 checksでPASS。全8枠、agent＋focus費用、共通成功、契約停止、固定source・開始時台帳179件/2,122束縛、API/receipt/control、server時間・RSS/swapを確認した。public exportではprivate pathと各checkの識別文字列を省き、元private結果とcheck/source集合のSHAを保存している。監査PASSは採用・一般品質・新規性の証明ではない。生成sourceはhash照合のみで、compilerの別アルゴリズムによる意味証明は行っていない。返信wire bytesはhashに束縛されたmetadataの和であり、全返信を別実装で再描画したものではない。

後処理v01は有限待機の期限判定を修正するため、監査・描画を始める前の待機中だけ停止した。model実験を停止・再試行したものではない。[v01修正記録](../../reports/P127_closed_review_wait_v01_prelaunch_correction.json)と[v02終了記録](../../reports/P127_closed_review_wait_v02_end.json)を保存する。v02が閉鎖後監査と描画をそれぞれ一度実行し、追加model/API/評価は0。

## 資料と次の判断

[全件の元資料](../../materials/20261026_p127_results/README.md)、[図](../../materials/20261026_p127_results/figures/README.md)、[会計・再描画注記](../../materials/20261026_p127_results/INTERPRETATION.md)。元collector出力と図v01のbytesを変更せず保存した。図は全8条件、全体と共通成功、通常cacheと自動/明示field利用を分けて示す。

[全132 sourceの閉鎖後AST診断](P127_admission_diagnosis.md)を終了した。全66対でsource/ASTが一致し、対象取得は各方式2 programのみで、完全応答を永続dictへ保存するためconsumer条件に入らなかった。後段の表示が2 fieldを読むことだけでは完全dictの将来可視性を捨ててよくならず、構文緩和だけで成立する安全な小変更は確認できない。この診断から次のモデル実験は採択しない。生の生成code、値、ID、推論、prompt、評価本文は公開しない。追加seedや不成立条件の反復を自動開始しない。限定した機構差と強い通常対照に対する効果経路が見つかった場合だけ、独立レビュー・source/CI・全条件・費用・採否・期限内閉鎖を別途固定する。未見12課題は確認計画固定前の未閲覧を維持する。原稿はユーザーが執筆する。

# 再開の入口：P125全8条件閉鎖、機構未発動（2026-10-26）

まず[P125所見](docs/P125_findings.md)と[独立再計算](docs/P125_independent_audit.md)を読む。全8条件を独立評価し、両方式とも3/4成功・総logical入力＋出力766,875 token。未知使用量0、元監査エラー0。全146 programで静的受理・変換・partial hit・通常cache hitは0、契約失敗0、固定gateはfalse。CSVは両方式ともAPI上限80で失敗した。

既存library providerはCSV実取得25件の必要値を持たず、候補0。既存ordinary joinには必要2項目が13件でそろう候補があるが、実API・全仕事tokenの削減は未測定。次の比較条件は未固定、新しい実験は未開始である。seed変更や共通ID guardだけを根拠に同じ比較を繰り返さない。

## 閉鎖済みP125を再起動しない

- 08:25 JSTに一度開始し、10:12 JSTに全8条件と所有serverを閉鎖した。[開始記録](reports/P125_execution_start_20261026.json)。実行head `2c11ceaa65b47b27cd23df8a943ab3d745b94461`、PR517 merge `f717c9376f546ecadadd7c37ad391eb7ac2c4c2d`。元条件・seed・採用規則を事後変更しない。
- 固定run木は `/Users/tp26013/AI-/.runtime/worktrees/p125-run`、準備木は `/Users/tp26013/AI-/.runtime/worktrees/p125-projection-online`。両木のsourceを編集しない。prepare・pipeline・wrapperを再実行しない。
- `.runtime/P125_closure_once_end.json` のaudit/session/reportは全exit 0、`.runtime/P125_report_collector_once_end.json` はcomplete。server stoppedと所有PID不在を確認済み。元collectorを再実行しない。結果公開用の編集木は `p125-results`。
- planの1,125 sourcesとplan自身を含む1,126 bindingsを照合済み。独立audit v02は全件再計算で一致した。初回v01のswap 0.0/int 0比較による失敗と修正来歴を保持し、元実験を再実行したものと扱わない。
- 全8合計1,533,750 token・154 model呼出し・488実API・8独立評価を保存する。P124の保存再生での11取得差をP125へ移して計上しない。実験バッチの終了を研究目標の達成と扱わない。
- 旧177台帳と2,056 source束縛を保持し、閉鎖結果の26 filesを束縛する `P125_results_provenance_20261026` を追加する。global一覧は178件となる。旧固定実行木へ最新一覧を当て、新file不足を旧記録破損と扱わない。

## 閉鎖済みP123を再起動しない

実行head `df45b1d9f32f8f547b54ea107f10e7534ba73e68`、run木 `p123-run`、回収木 `p123-prep`。`.runtime/P123_closure_once_end.json` と `.runtime/P123_report_collector_once_end.json` はcomplete。collectorは自動待機経由で一度終了、再実行不要。旧174台帳・2013bindingsを照合済み。新規の結果公開木は `p123-results`。

[P123所見](docs/P123_findings.md)：3方式各4/4成功、使用量不明0、監査エラー0。単発893,529、別反復785,656、同時反復836,922 tokenで、同時反復の固定gateはfalse。P124は全20program一致・保存backend68対57、実モデル/API0の局所検証（[所見](docs/P124_findings.md)）。

P123/P124/P125の固定実行木と旧束縛sourceを編集しない。新台帳をglobal一覧へ登録する際は、最新の作業木に全sourceがあることを照合する。旧回収木へ最新一覧を当てて新file不足を旧記録破損と扱わない。

原稿はユーザーが執筆し、こちらは主要実験と全結果・採否・再現根拠を担当。普通のメッセージでは実験を止めず、明示停止には所有processの閉鎖まで対応する。未見12課題、過去の失敗・未知費用・原稿を保持する。[現状](docs/current_status.md)／[次の作業](docs/next_actions.md)／[履歴レビュー](docs/research_history_review_20261026.md)。

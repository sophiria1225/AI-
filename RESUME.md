# 再開の入口：P123閉鎖、P125実行中（2026-10-26 08:27 JST）

P123は全12条件を終了し、3方式とも既知4課題で4/4成功、使用量不明0、監査エラー0。総logical入力＋出力tokenは単発893,529、別呼出し反復785,656、同時反復836,922。別呼出し反復は単発より12.07%少ない。同時反復は別呼出し反復より6.53%多いため、事前の採用判定はfalseを保持する。

[P123所見](docs/P123_findings.md)と[独立確認](docs/P123_independent_audit.md)を読む。P124は全20program一致・保存backend68対57、実モデル/API0（[所見](docs/P124_findings.md)）。新機構の全仕事token削減はまだ未測定。

## 実行中のP125を再起動しない

- 08:25 JSTに専用wrapperを一度開始済み。[開始記録](reports/P125_execution_start_20261026.json)。実行head `2c11ceaa65b47b27cd23df8a943ab3d745b94461`、PR517 merge `f717c9376f546ecadadd7c37ad391eb7ac2c4c2d`。同一headのpush/PR両CI成功を確認済み。
- 固定run木は `/Users/tp26013/AI-/.runtime/worktrees/p125-run`、準備木は `/Users/tp26013/AI-/.runtime/worktrees/p125-projection-online`。両木のsourceを編集しない。prepare・pipeline・wrapperを再実行しない。
- 初期入力8件＋要約transport1件の計数とactivationが完了。planの1,125 sourcesとplan自身を含む1,126 bindingsを照合済み。08:27 JSTにwrapper・pipeline・所有server・batchの生存を確認。P125結果は未確定、途中成否・費用・モデル本文は未読。
- 運用readerは `.runtime/read_projection_study_operational_status.py`。状態・所有processだけを確認し、途中成果で固定8条件、seed157、共通単発checkpointを変更しない。明示停止時は `.runtime/P125.stop` を用いる既存停止手順に従い、所有processの閉鎖まで確認する。
- 元wrapperがpipeline→全件audit→server会計→全8条件資料を処理する。正常終了または停止で全枠と所有serverが閉鎖した後に、保存された失敗・未実施・不明を含め採否を判断する。8条件完了を研究完了と扱わず、次の有限比較へ進む。
- global研究台帳一覧は177件を維持し、この運用更新用の台帳は追加しない。固定実行木に存在しない新sourceを一覧へ要求しない。

## 閉鎖済みP123を再起動しない

実行head `df45b1d9f32f8f547b54ea107f10e7534ba73e68`、run木 `p123-run`、回収木 `p123-prep`。`.runtime/P123_closure_once_end.json` と `.runtime/P123_report_collector_once_end.json` はcomplete。collectorは自動待機経由で一度終了、再実行不要。旧174台帳・2013bindingsを照合済み。新規の結果公開木は `p123-results`。

P123/P124の固定実行木と旧束縛sourceを編集しない。新台帳をglobal一覧へ登録する際は、最新の作業木に全sourceがあることを照合する。旧回収木へ最新一覧を当てて新file不足を旧記録破損と扱わない。

原稿はユーザーが執筆し、こちらは主要実験と全結果・採否・再現根拠を担当。普通のメッセージでは実験を止めず、明示停止には所有processの閉鎖まで対応する。未見12課題、過去の失敗・未知費用・原稿を保持する。[現状](docs/current_status.md)／[次の作業](docs/next_actions.md)／[履歴レビュー](docs/research_history_review_20261026.md)。

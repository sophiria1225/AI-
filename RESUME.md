# 再開の入口：P123閉鎖、P125準備中（2026-10-26 08:16 JST）

P123は全12条件を終了し、3方式とも既知4課題で4/4成功、使用量不明0、監査エラー0。総logical入力＋出力tokenは単発893,529、別呼出し反復785,656、同時反復836,922。別呼出し反復は単発より12.07%少ない。同時反復は別呼出し反復より6.53%多いため、事前の採用判定はfalseを保持する。

[P123所見](docs/P123_findings.md)と[独立確認](docs/P123_independent_audit.md)を読む。P124は全20program一致・保存backend68対57、実モデル/API0（[所見](docs/P124_findings.md)）。新機構の全仕事token削減はまだ未測定。

## 次に動かすもの

- P125準備木：`/Users/tp26013/AI-/.runtime/worktrees/p125-projection-online`、branch `research/p125-projection-online-20261026`、draft PR517。
- P125はモデル未開始、plan作成前。P123結果公開後にmainをmergeして `scripts/prepare_whole_task_projection.py --storage-root /Users/tp26013/AI-` を一度実行する。旧source hash、P124全1095implementation、P123閉鎖12件を確認する。
- 最終plan/headの両CI後に `p125-run` を別作成し、`.runtime/run_close_p125_once_20261026.py --expected-head <固定head>` を一度だけ実行。pipeline→audit→session→全8資料まで行う。
- 運用reader：`.runtime/read_projection_study_operational_status.py`。途中の成否・費用で変更しない。8条件の完了を研究完了と扱わず、全件を判断して次の有限比較へ進む。

## 閉鎖済みP123を再起動しない

実行head `df45b1d9f32f8f547b54ea107f10e7534ba73e68`、run木 `p123-run`、回収木 `p123-prep`。`.runtime/P123_closure_once_end.json` と `.runtime/P123_report_collector_once_end.json` はcomplete。collectorは自動待機経由で一度終了、再実行不要。旧174台帳・2013bindingsを照合済み。新規の結果公開木は `p123-results`。

P123/P124の固定実行木と旧束縛sourceを編集しない。新台帳をglobal一覧へ登録する際は、最新の作業木に全sourceがあることを照合する。旧回収木へ最新一覧を当てて新file不足を旧記録破損と扱わない。

原稿はユーザーが執筆し、こちらは主要実験と全結果・採否・再現根拠を担当。普通のメッセージでは実験を止めず、明示停止には所有processの閉鎖まで対応する。未見12課題、過去の失敗・未知費用・原稿を保持する。[現状](docs/current_status.md)／[次の作業](docs/next_actions.md)／[履歴レビュー](docs/research_history_review_20261026.md)。

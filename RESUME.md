# 再開の入口：P123実行中、2026年10月26日

P124は閉鎖済み。固定応答再生で全20プログラムの出力・方式間境界が一致し、通常cache68対提案57の保存backend応答だった。[全結果](docs/P124_findings.md)と[独立監査](docs/P124_independent_audit.md)。P123は07:07 JST時点で9/12条件終了、途中の成否・費用は未読。P125は`.runtime/worktrees/p125-projection-online`で準備中、実行未開始。P123全件回収後に4既知課題×2方式の有限比較へ進む準備を継続する。P124の実行木`p124-projection-prep`は再生時の固定bytesを保持する。

**2026-10-26 05:49 JST確認：P123を2026-10-26 05:47 JSTに開始し、固定12条件を実行中.** [PR512](https://github.com/sophiria1225/AI-/pull/512)の完全head `df45b1d9f32f8f547b54ea107f10e7534ba73e68`でpush・pull_request両CIと両jobが成功した. 24 native入力計数とactivationも完了し、wrapper・管理プロセス・推論serverの生存を確認. 途中成否と費用はまだ読んでいない.

ユーザーは「時間がないので実験を行い、止めてと言うまで継続する」「最終目標までの認識と作業を詳しく書く」と再指示した. [認識と実験方針](docs/research_execution_route_20261026.md)を読む. 最終目標は最終性能維持と全仕事token削減、その機構の新規性. まだ達成していない.

[P0–P123の詳細な履歴レビュー](docs/research_history_review_20261026.md)を完了. 通常のメッセージでは実験を止めず、質問対応と研究を並行する.

## 今動いているもの

- 固定実行木：`/Users/tp26013/AI-/.runtime/worktrees/p123-run`
- 実装head：`df45b1d9f32f8f547b54ea107f10e7534ba73e68`、PR512
- wrapper PID：2005、server supervisor PID：2043、server PID：2044（05:48 JST確認時. 生存は毎回再確認）
- 実プロセスと進行：`.runtime/read_checkpoint_study_operational_status.py`
- 原開始記録：`.runtime/P123_pipeline_once_start.json`
- pipeline：`records/context_pilot/P123_pipeline_v01/status.json`
- 全枠：`records/context_pilot/P123_batch_v01/status.json`

古い`.runtime/P123_independent_launch_status_20261026.json`のstoppedは、モデル開始前のVSCode認証socket失敗の歴史的記録. 既存gh認証で同一branchを公開し、両CI・merge確認後、元のguard付きwrapperを一度だけ実行した. この失敗launcherを再実行しない. 公開根拠は`.runtime/P123_independent_publication_20261026.json`.

## 編集・回収先

結果回収先は`.runtime/worktrees/p123-prep`. 今回の運用案内・研究方針の編集木は`.runtime/worktrees/p123-operations`、branch `research/p123-history-review-20261026`. 固定実行木と結果回収先の束縛済みソースを変更しない. 結果回収までglobal台帳一覧へ回収先にない新台帳を登録しない.

全12枠とserver閉鎖後、元wrapperが監査、session、全件資料を生成する. `.runtime/P123_closure_once_end.json`を確認してから、新collectorを一度だけ実行する.

```sh
/Users/tp26013/AI-/.runtime/p3_ci_venv/bin/python /Users/tp26013/AI-/.runtime/collect_p123_closed_independent_20261026_once.py --expected-head df45b1d9f32f8f547b54ea107f10e7534ba73e68
```

開始・終了印を消して再実行可能にしない. 途中成否や費用は読まず、全件閉鎖後に採否を判断する. 実験やwrapperの終了を研究完了と混同せず、次の有限比較まで担当する.

## 保存する前提

P122は別10/12対同時9/12で、CSVの成功損失がある. 費用は2,365,604対2,257,940既知＋不明１要求. この未知使用量と旧falseを保持. P123は強い通常対照の比較で、通過しても新規性や統計的品質維持の成立とはしない.

未見12課題は予約を維持し、確認条件を固定する前に開かない. 元原稿checkpoint_cost_v01を保存する. 最新指示により原稿はユーザーが改めて執筆し、こちらは実験・再現可能な結果・採否・根拠を揃える.

[現在状態](docs/current_status.md)／[次の作業](docs/next_actions.md)／[固定仕様](docs/experiments/P123_whole_task_rolling_checkpoint.md).

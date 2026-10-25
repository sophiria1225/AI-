# 再開の入口：2026年10月26日、P123固定準備後

**追加確認：GitHub接続の書込みもHTTP403で拒否されたため、PR公開とCIは未実施. 通常ターミナルからの一括再開は[公開・実行手順](docs/P123_launch_20261026.md)を使う.**

**P123の独立実行判断とconfigを作成済み. 実モデル実験は未開始.** [詳細引き継ぎ](docs/handoff_20261026_context_transfer.md)は移行時点の記録であり、その後の変更は[今回の判断](docs/P123_execution_decision_20261026.md)と[機械可読記録](reports/P123_execution_decision_20261026.json)を優先する.

最終目標は、最終タスクの性能を保ち、要約・制御・失敗・再取得を含む全仕事の入力＋出力トークンを減らすハーネス制御. 新規性と全体目標の達成は未確立. ユーザーの「停止まで実験を進める」という許可を引き継ぐ.

## 完了した準備

- P122全24評価、監査エラー０、閉鎖記録・session・materialsの指紋を再照合.
- CSV seed257最後の要求の使用量null、作用不明０、後始末確認済みを保持. 旧自動判定falseを変更せず、独立したP123の実行判断を新規保存.
- `configs/P123_whole_task_rolling_checkpoint_v01.json`を作成. ３方式×４既知課題、12条件、事前仕様と予算を維持し1,286ソース指紋へ束縛.
- 既存172台帳・2,007指紋を確認. 旧原稿と未見12課題を保持.
- 新しい私有collectorの宛先を今回の編集木へ固定. 旧collectorを変更せず、まだ収集予約はしていない.

## 実行を妨げている環境条件

現在のセッションでは、通常の`sources()`内の`ps`がPermissionErrorで拒否される. ローカル待受ポートの作成もPermissionErrorとなり、推論serverを開始できない. signal 0では旧P122のserverとsupervisorは不在だが、既存runnerの検査を通ったことにはしない. 通信はGitHub接続ツールを使用している.

生成、課題API、評価、native計数は０. 起動印を先に作らない. ガードを無効化しない. 実行可能な承認済み環境で元の検査を通し、CI確認済み完全headで一度だけ起動する.

## 作業場所

| 用途 | 場所 |
|---|---|
| 編集木 | `/Users/tp26013/AI-/.runtime/worktrees/p123-prep` |
| branch | `research/p123-independent-start-20261026` |
| 保存ルート | `/Users/tp26013/AI-` |
| 軽量Python | `/Users/tp26013/AI-/.runtime/p3_ci_venv/bin/python` |
| 固定実行木 | `.runtime/worktrees/p123-run`、CI確認後に作成 |
| 実行wrapper | `.runtime/run_close_p123_once.py` |
| 新collector | `.runtime/collect_p123_closed_independent_20261026_once.py`、宛先p123-prep |
| 私有準備記録 | `.runtime/P123_independent_preparation_private_20261026.json` |
| 公開・CIの最終記録 | `.runtime/P123_independent_publication_20261026.json`、公開処理後に保存 |

## 次の実作業

同じ完全headのpush・pull_request両workflowと両`accounting-and-syntax` jobを確認し、通常runnerの`sources()`、停止印と開始印、固定実行木、collectorの全指紋を照合する. その後wrapperが24事前計数、activation、12条件、server閉鎖、監査、session、資料化を行う. 実際のPIDと更新時刻を確認してから稼働中と説明する.

全件閉鎖後に収集し、課題ごとの成功維持、全４課題と共通成功課題の総token減、両反復方式で２回以上の採用を判定する. 一部の好結果を先に選別しない. その後、次の有限な研究判断を行い、Project/materialsと原稿次版へ反映する. 一回のwrapper終了は研究の完了ではない.

P122は別10/12対同時9/12、費用は2,365,604対2,257,940既知＋不明１要求. 写真２対減・１対増、CSV成功損失. P123が成功しても既知４課題の開発比較であり、統計的非劣性や新規性の成立とは区別する.

[次の作業](docs/next_actions.md)／[現在状態](docs/current_status.md)／[準備資料](materials/20261026_p123_preparation/README.md).

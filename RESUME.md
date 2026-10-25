# 再開の入口：2026年10月26日

**まず[詳細な引き継ぎ](docs/handoff_20261026_context_transfer.md)を読む. P122は終了・公開済み、P123は未開始、実験は現在停止している.** ユーザーはコンテキスト移行のため本資料を依頼した. 本作成中に新しいモデル生成、API実行、評価、native入力計数は行っていない.

最終目標は、最終タスクの性能を保ち、要約・制御・失敗・再取得を含む仕事全体の入力＋出力トークンを減らすハーネス制御. 新規性と性能を保った全体削減は未確立. ユーザーの「止めてと言うまで実験を進める」という指示を引き継ぐ. 現在動いていると説明してはいけない.

## 停止と結果

P122は10/25 23:22:57 JSTに全24条件を終了. 所有server閉鎖、全件監査、資料作成、回収、PR510での公開まで完了した. 別要約10/12対同時要約9/12成功. 写真の３対は全て両側成功だが、同時−別の差は−10,497、−32,865、+2,349 token. CSVで成功損失があり、seed257の最後の要求はtimeoutで使用量不明.

使用量全件既知を求めた自動継続条件により、23:24:38 JSTに `closed_results_need_research_review_no_P123_generation` で終了した. ユーザーの停止指示ではない. P123のconfig、実機事前計数、activation、生成は存在しない. 不明値や古いfalse判定を変更せず、次の独立実験の判断を別に記録する.

[全件所見](docs/P122_findings.md)／[P122資料](materials/20261025_p122_results/README.md)／[現在の証拠](reports/context_handoff_20261026_snapshot.json).

## 作業木と保存先

| 用途 | 場所 |
|---|---|
| 今回の編集木 | `/Users/tp26013/AI-/.runtime/worktrees/context-handoff-20261026` |
| branch | `docs/context-handoff-20261026` |
| モデル・AppWorld・私有記録 | `/Users/tp26013/AI-` |
| 軽量Python | `/Users/tp26013/AI-/.runtime/p3_ci_venv/bin/python` |
| 図表・PDF Python | `/Users/tp26013/AI-/.runtime/reporting-venv/bin/python` |
| P122固定実行木 | `.runtime/worktrees/p122-run`、head `5ddbba8c8b4614bc9856202942dc28caf5b204f7` |
| P122結果 | PR510、merge `4200a464d8aaed187a4361fa7055759b6c5bcbfb` |
| 旧編集木 | `.runtime/worktrees/p107-prep`、終了済みP122の回収物が未追跡のまま存在 |
| P123実行木 | `.runtime/worktrees/p123-run`、現在は未作成 |

ストレージcheckoutと固定実行木の追跡ファイルを編集しない. 新しい作業は最新mainから別worktreeを作る. 旧編集木の未追跡回収物はPR510公開済みの同一成果物で、消去や再生成は不要. 変更先は `sophiria1225/AI-` と専用Project 1のみ.

## 次に行うこと

1. AGENTS、本引き継ぎ、実プロセスと開始・終了印、branch・origin・dirty状態を確認する.
2. P122の24評価、監査エラー０、未知１要求、作用・後始末・server閉鎖の根拠を使い、独立P123の実行判断を新文書へ記録する. 古い自動継続を再起動しない.
3. [P123の既定仕様](docs/experiments/P123_whole_task_rolling_checkpoint.md)の３方式×４課題、12条件のconfigを作る. `make_plan()`は利用可能だが、既存所見を作り直す`prepare()`は実行しない.
4. ソースと新判断を固定し、PRの同一完全headでpush・pull_request両workflowと両`accounting-and-syntax` jobの成功を確認する.
5. 固定実行木と収集先の指紋整合を確認して、準備済みP123 wrapperを一度だけ起動する. 旧collectorは宛先が`p107-prep`固定なので、新編集木との整合を先に解決する.
6. 実行中は運用状態だけ確認する. 全12枠とserver閉鎖後に全件を監査・資料化し、次の有限な研究判断へ進む. Projectとmaterialsを更新する.

詳しい予算、採否、コマンド、終了後の分岐は[引き継ぎ第7–12節](docs/handoff_20261026_context_transfer.md)と[次の作業](docs/next_actions.md).

## 保存を守る

現在の公開指紋は、既存171台帳・2,004指紋に今回の３成果物を加え、172台帳・2,007指紋. 一覧は `.runtime/research_ledger_names.json`. 束縛済みのbytesは保持し、変更が必要なら別版にする. P120/P121/P122、過去の不明要求と失敗、旧原稿を置き換えない. 未見12課題を開かない.

現在の私有入口は `.runtime/context_handoff_20261026.json`. 公開確認は `.runtime/context_handoff_20261026_publication.json`. 運用readerは `.runtime/read_checkpoint_study_operational_status.py`. `.runtime/P122_to_P123_continuation_status.json`は終了済みの歴史的記録である. 古い「continuation armed」という記述を現在へ適用しない.

原稿は `papers/202610_letter/checkpoint_cost_v01/`、PDF SHA-256は `ac0a375b9601e7c84fc33976b8ae736deace9d7ee252556a726f567b2d535ef3`. P122未反映、著者・所属・公式クラスは未完了. 10/31投稿目標. 教授用459字、句点`.`、中黒なしの希望を維持する. 教授への送信と学会投稿は未実施.

# 現在の研究と実行を引き継ぐ

2026-10-24更新。ユーザーは「こちらが止めるまで継続」、さらに就寝中も実行継続を指示した。再度の許可は不要。新しい停止指示が来たら直ちに従う。以前の停止記録を削除したり、終了済み実験を再試行したりしない。

最終目標は必要情報・処理と最終品質を保った全仕事費用の削減。25日まで追加確認と採否、29〜30日に原稿整備、31日にレター投稿完了を目指す。新規手法・一般的品質維持・採録に足る貢献は未確立。[現在の状態](docs/current_status.md)と[次の判断](docs/next_actions.md)を先に読む。

## 同じMacの保存先と作業木

| 用途 | 絶対パス／固定版 |
|---|---|
| モデル・データ・Git管理外記録・環境 | `/Users/tp26013/AI-` |
| 最新の編集木 | `/Users/tp26013/AI-/.runtime/worktrees/p84-prep` |
| P82の実行木 | `/Users/tp26013/AI-/.runtime/worktrees/p82-run`、`ce81c87ed4a456543859ee98e5aec9e7c5703b77`固定。実行中は編集しない |
| P82終了後の資料・原稿出力木 | `/Users/tp26013/AI-/.runtime/worktrees/p82-prep`。待機処理が出力するので、無断で切替・削除しない |

最新編集木のブランチは変わり得るため `git status --short --branch` で確認する。p82-prepの未追跡成果物は終了後処理が作った可能性がある。上書き・清掃しない。コードをcloneするだけでは私有記録・モデルは戻らない。

## 動いている処理

P82は常時残時間表示M、非表示H、後半表示Lを、同じ表示前参照統一下で既知４課題×２反復、全24条件実行中。[固定計画と開始判断](docs/P82_execution_decision_20261024.md)。途中の結果で順序・閾値・予算を変更しない。

保存先を `/Users/tp26013/AI-` とすると、状態は次を読む。

- `records/context_pilot/P82_pipeline_v01/status.json` と `P82_batch_v01/status.json`：本実行。
- `.runtime/P82_closure_status.json`：終了後の全件監査、経路照合、推論器・呼出し集計、７枚資料。
- `.runtime/P82_manuscript_status.json`：上記が成功した後の原稿数表とPDF作成。目視・解釈・公開は未実施として残す。

待機処理はそれぞれ既存lockを持ち、最大72,000秒待機、段階ごと最大300秒、失敗時の自動再試行０。新たに同じ処理を起動しない。原稿の組版先は `.runtime/P82_manuscript_real_render`。開始前に既存の結果表・PDFがないことと準備６出典の不変を確認済み。

停止時は `.runtime/P82.stop` を作り、本実行・終了後監査・原稿待機の停止を確認する。資料処理のみの停止は `.runtime/P82_reports.stop`、原稿のみは `.runtime/P82_manuscript.stop`。停止ファイルを勝手に削除しない。

P84は準備済み・未開始。P82の全24件監査・使用量既知・所有推論器停止を確認した場合だけ固定した18生成へ接続する条件を決めた。[接続の詳細](docs/P84_continuation_decision_20261024.md)。待機状態は `.runtime/P84_continuation_status.json`、実際の開始判断は `.runtime/P84_execution_decision.json`、終了後処理は `.runtime/P84_closure_status.json` に保存する。研究全体の停止時には `.runtime/P82.stop` と `.runtime/P84.stop` の双方を作る。待機のみは `P84_continuation.stop`、P84資料のみは `P84_reports.stop`。既存lock・停止印を削除しない。現在はP84モデル割当て・計数・生成０。[計画](docs/experiments/P84_fallback_output.md)を変更せず、別の実験で不明使用量を埋めない。

## 保存した結果と未完了事項

[現在の状態](docs/current_status.md)に、P80/P81、P83、費用指標の再集計、先行研究、原稿の入口をまとめた。実験結果・準備台帳・既存原稿のhashを保ち、必要な改訂は別版にする。README等の入口は更新してよい。

[教授用案](materials/20261023_professor_brief/README.md)の日英題名・456字あらましは維持する。著者名・所属・順序を推測しない。公式様式確認は未完了。外部送信・投稿は未実施。

GitHub変更先は `sophiria1225/AI-` とその[専用Project](https://github.com/users/sophiria1225/projects/1)のみ。全115件の作業ボードを部分集合で上書きしない。実モデル実験の開始とmainへの統合は、正確なHEADのpush/PR両CIとジョブ成功を確認する。

[AGENTS.md](AGENTS.md)と[当初の引き継ぎ](docs/handoff_20261022_account_switch.md)も読む。長い時系列記録は[更新前RESUMEの固定版](https://github.com/sophiria1225/AI-/blob/6e38556bcff00b2cfb509da6a645e736f5fcce23/RESUME.md)に残っている。

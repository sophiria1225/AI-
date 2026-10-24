# 研究と実行の引き継ぎ

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P111の既知４課題×３方式、全12条件を終了・評価・監査し、不一致０、所有サーバー停止を確認。全方式3/4成功だが採用基準は未達。204生成、既知2,026,162 token＋使用量不明２、610 API、12評価。選別は成功した全３課題の小計では全保持より3.07%、直近保持より4.10%少ないが、全４課題では既知分だけで直近保持の全費用を108,637 token（19.57%）上回る。不明を０で補わず、小計で基準を置き換えない。P112は全204要求×３表示の612計数をbinding済み、同じ完全headの両CI成功後に一度だけ実施する。原稿保留、未見12課題は未閲覧。新規性と一般的品質維持は未確立。 [全件資料](materials/20261025_p111_results/README.md)。
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

## 目的と現在の指示

最終目標は、AIオーケストレーションで必要な情報と処理を残し、最終成果の品質を維持しながら、不要な取得、共有、モデル呼出し、実行、検証を減らすこと. 失敗、再取得、回復、制御を含む仕事全体で評価する. 実装件数や局所的な取得省略だけで新規性を主張しない.

ユーザーは「止めてと言うまで続ける」と指示している. 現在の停止指示はない. ただし新しいモデル実験は、条件、対象、比較、有限予算、欠測の扱いを固定してから行う. 2026年10月25日まで追加確認と採否を進め、29〜30日に原稿を整え、31日までのレター投稿を目指す. 著者名、所属、著者順は未確認. 教授への送信や投稿は未許可.

**原稿の逐次更新はユーザー指示で保留中.** 実験を優先し、結果がまとまってからProjectとmaterialsを更新する. 停止指示が来たら従う. 過去の停止記録を現在の指示と混同しない.

[AGENTS](AGENTS.md)／[現在状態](docs/current_status.md)／[次の作業](docs/next_actions.md)／[元の引き継ぎ](docs/handoff_20261022_account_switch.md). 整理前の長い経緯は[固定版のRESUME](https://github.com/sophiria1225/AI-/blob/20c14641da3bcf34fb827ef85735e2197311d5ce/RESUME.md)に保持している.

## 保存先と実行の境界

| 用途 | 場所 |
|---|---|
| モデル、AppWorld、私有記録 | `/Users/tp26013/AI-` |
| 今回の結果編集木 | `.runtime/worktrees/p107-prep`、`research/p111-results-p112-binding-20261025` |
| P107の固定実行木 | `.runtime/worktrees/p107-run`、`983bdebed74654b5fa80af8a61a98d0af4147458` |
| P108の固定点検木 | `.runtime/worktrees/p108-run`、`4695ca867d13b23be6c0ba10dabf413d0843b316` |
| P109の固定点検木 | `.runtime/worktrees/p109-run`、`21a58c4c47f80e872aab095c6ec056a9cf0a7993` |
| P110の固定計数木 | `.runtime/worktrees/p110-run`、`73389b3ec2b00eee52235660254260ec59bd5090` |
| P111の固定実行木 | `.runtime/worktrees/p111-run`、`a00e87087b93e2b1d3fd506bc40b988979027768` |
| Python 3.12 | `.runtime/p3_ci_venv/bin/python` |
| 図の生成環境 | `.runtime/reporting-venv/bin/python` |

ストレージ用checkoutや固定実行木の追跡済みファイルを編集しない. 編集木のbranchと差分を確認する. `.runtime/research_ledger_names.json`に登録された全公開台帳と固定計画の指紋を照合する. 終了済み実験、入力、失敗、欠測、監査、資料を上書きしない.

P107の開始、閉鎖、収集はそれぞれ `.runtime/P107_pipeline_once_start.json`、`P107_closure_once_end.json`、`P107_collection_once_end.json`で区別する. P108は `.runtime/P108_analysis_once_start.json` と `P108_analysis_once_end.json`を持つ. 印の存在と保存状態を確かめてから進め、同名の処理を重ねて実行しない. P107の成否は全２条件の閉鎖と所有サーバー停止後に読む. P108は保存返答を用いるホストの点検で、生成Pythonや実APIの再実行ではない.

## 誤解しないこと

通常のキャッシュ、遅延評価、取得予約、参照共有そのものは新規性としない. 明示的なReadViewは読取専用Mappingであり、既存dictの透明な置換ではない. 状態変更前の完全取得や未取得の項目へのアクセスで、後回しにした取得が必要になる. 予約は実API送信ではなく、API削減はtoken削減とは別である.

P105の手書き列の13対12という差は、通常の完全応答キャッシュを両側に入れたP106で12対12になった. この差を遅延方式固有の便益へ使わない. P104でも、ホスト内の取得数が減っても応答本文のモデル入力が減らない場合を確認した. [P104](docs/P104_findings.md)／[P105](docs/P105_findings.md)／[P106](docs/P106_findings.md).

P107は事後に選んだ既知１課題、各方式１回の開発比較. 両側に同じ参照インタフェースと通常キャッシュを与え、未見12課題は開かない. P99と異なる接続部分もあるため、過去のP99との差を遅延取得だけへ帰属させない. [固定計画](docs/experiments/P107_whole_task_read_views.md).

P98/P103の入力、公開出力、提出コード、API列の対応は実証材料だが、課題成功や新しい費用削減法とは別. 未知の使用量は０や予約上限で補完しない. 全条件と失敗を保持する. 新提案の中核、一般的品質維持、採録に足る貢献は未確立.

## 投稿と同期

現在の検討稿は `papers/202610_letter/execution_evidence_controls_v02/`. 本文４頁＋英文１頁を確認済みだが、公式様式適合、著者情報、投稿完了は未確認. [教授用の和英題名とあらまし](materials/20261023_professor_brief/README.md)は保持する. 原稿の保留を、投稿済みや完成と解釈しない.

変更先は `sophiria1225/AI-` と専用[Project 1](https://github.com/users/sophiria1225/projects/1)だけ. Projectは全120件を保持し、部分同期後も全件からtask boardを生成する. 同じ完全SHAのpush・pull_request両workflowと両`accounting-and-syntax` job成功後にmergeや新しい実記録処理へ進む. 生のモデル推論、完全履歴、正解、認証情報はGitへ登録しない.

P109は全件終了済みで、`.runtime/P109_analysis_once_start.json`と`P109_analysis_once_end.json`を保持する. [P109所見](docs/P109_findings.md)と[先行方式の確認](docs/receipt_history_prior_scope_20261025.md)を次の準備の前提にする. P109完了時点では新しい履歴制御の性能比較は未開始だった. 最新は冒頭のP111開始状態を参照.

P110も全444入力の計数を終了した. `.runtime/P110_analysis_once_start.json`と`P110_analysis_once_end.json`を保持. [所見](docs/P110_findings.md)を前提に、次の全仕事比較を準備する. P110はモデル性能の測定ではない.

P111の全12条件と所有サーバーは閉鎖済み. `.runtime/P111_pipeline_once_end.json`、`P111_closure_once_end.json`、`P111_report_collector_once_end.json`、`P111_editor_artifacts_once_end.json`を保持する. pipeline、全記録監査、session点検、全件資料作成、P112 bindingはいずれも一度だけ完了し、再実行しない. サーバーのrequested_stopは有限比較完了後の終了理由であり、ユーザーによる研究停止指示ではない.

P112の完全計画は `configs/P112_realized_history_inputs_v01.json`. 全204保存要求×３表示=612入力、360公開ソース、519私有入力を固定した. 計数は未開始. 計画とコードの同じ完全headの両workflow・両job成功後、`.runtime/worktrees/p112-run`を作り、`.runtime/run_p112_bound_once.py --repo-root /Users/tp26013/AI-/.runtime/worktrees/p112-run --head FULL_SHA`から一度だけ実施する. `.runtime/P112_analysis_once_start.json`と`P112_collection_once_end.json`を確認し、重ねて実行しない.

P111の結果収集元は固定木 `.runtime/worktrees/p111-report`（`356fd9f5203cfaf060c2a89a26ea949ee955e931`）. 全監査、全資料、P112計画は編集木へ同一bytesでコピー済み. 詳細は `.runtime/P111_P112_pending_execution_handoff.json`. P112終了後は `scripts/plot_receipt_history_results.py`で実データの図を生成し、目視確認する. 合成プレビューは実績として公開しない.

[P111の判断](docs/P111_findings.md)／[実行成否を使う先行研究との追加照合](docs/receipt_history_execution_prior_scope_20261025.md). 未知２試行、元の採用基準未達、原稿保留、未見12課題を維持する. ユーザーの停止指示があれば直ちに従う.

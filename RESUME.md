# 研究と実行の引き継ぎ

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P114は既知４課題の通常public_only対照を実行中。全件成否を読む前にP115の入力差診断を準備した。全４条件の全保存要求を４表示で計数し、表示の省略量と過去P111を参照した全仕事の費用差を区別する。11追加検査を含む全1,839検査成功。P114の途中成否は未閲覧。閉鎖・監査・全記録の指紋固定・計画の両CI成功後にのみ計数する。新規生成、API、評価０。新規性と一般的品質維持は未確立。原稿保留、未見12課題未閲覧を維持。 [診断の準備](materials/20261025_p115_preparation/README.md)。
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
| 今回の結果編集木 | `.runtime/worktrees/p107-prep`、`research/p115-input-diagnostic-20261025` |
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

P112は全612入力の計数と全件資料を一度だけ終了した. 固定実行木は `.runtime/worktrees/p112-run`、`5205cc54afe8c2a7b71d0e17d259ebc5b46cf4f7`. `.runtime/P112_analysis_once_start.json`、`P112_collection_once_end.json`、`P112_editor_artifacts_once_end.json`を保持し、再実行しない. 全12計数プロセスは終了、未知使用量２件を元のまま残した.

P111/P112の実データ図６ファイルを生成し、PNG２枚の全ラベルと未知表示を目視した. [全件の図](materials/20261025_p111_p112_figures/README.md)と[P112所見](docs/P112_findings.md)を参照する. 合成図は公開結果へ含めない.

P113の全12条件・204要求・610 APIの診断と全件資料は一度だけ終了した. 固定実行木は `.runtime/worktrees/p113-run`、`5f8aa671ee154c1f50df481cc146bc70ff5376bd`. `.runtime/P113_analysis_once_start.json`、`P113_collection_once_end.json`、`P113_editor_artifacts_once_end.json`を保持し、再起動しない. 全12対と末尾を含む219位置を残した. [P113所見](docs/P113_findings.md)と[全件資料](materials/20261025_p113_results/README.md)を参照する.

P114は[固定計画](configs/P114_whole_task_public_only_history_v01.json)と[方法](docs/experiments/P114_whole_task_public_only_history.md)を準備済み. 既知４課題、各１回、public_onlyだけを最初から追加する. 各80生成、450,000 token、1,800仕事秒、写真160 API・他80 API. 所有server14,400秒. 全1,828検査成功、計画391 sourceを固定、固定headから実行開始済み. `.runtime/P114_preparation_once_end.json`と`P114_pipeline_once_start.json`を保持する.

P111は全12条件を過去参照としてそのまま使う. 同時実行対照でも未見確認でもない. P76の途中継続とP25のnative toolは同じ初期構成の対照へ読み替えない. 最初の４要求はP111の各３方式の完全要求・計数・予算通知と照合する. 直前や失敗時の推論も送信時に省くが、完全保存履歴と公開情報・状態は保持する. 生成の推論予算は変えない.

同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功を確認し、`.runtime/worktrees/p114-run`から一度だけ起動済み. 実行headは`c74c579c1addad248cffcdb9639178b20d5b46b6`. `.runtime/run_close_p114_once.py`がpipeline後にaudit・session・全件reportを一度だけ実行する. 起動を重ねない. 新しい停止指示があればP114の停止印と所有プロセスを扱う. 所有server閉鎖後に全４条件と全12過去条件を整理する. P111の不明使用量２、採用基準未達と先行研究上の限界を維持する. 条件探索、再試行、未見12課題の閲覧をしない. 原稿は保留し、停止指示があれば直ちに従う.

P115はP114閉鎖後の入力差診断を準備した段階. 完全計画のbindとcountは未開始. [固定範囲](docs/experiments/P115_realized_history_inputs.md)を同一headの両CIで確認し、閉鎖した全４条件の全記録をbindingした後、計画の両CIを経て一度だけ計数する. 生の推論や完全要求はGitへ登録しない.

# 研究と実行の引き継ぎ

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P120全８条件を閉鎖した. 必須欄の同時出力は写真とCSVで要約を生成・採用した. 写真は両方式成功、139,871→129,374 token（約7.50%減）、17→16モデル要求、APIは両側102だった. 一方、CSVは同時出力がtoken予約制約で未達となり、別呼出し4/4対同時出力3/4で成功損失１. 全167要求の使用量既知、1,774,173 token、422 API、８評価. 全体の採用基準は未達で、成功例だけを一般化しない. P121は全24枠・487保存要求・974入力のbindingを完了し、計数は同一headの両CI成功後. 新規モデル呼出しは０. 10月25日の指示により原稿執筆を再開し、P120とP121で追加実験を区切る. 新規性は未確立、未見12課題は未閲覧. [全件所見](docs/P120_findings.md).
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
| 今回の結果編集木 | `.runtime/worktrees/p107-prep`、`research/p119-results-20261025` |
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

P114は全４条件と所有serverの閉鎖、監査、session費用確認、全件資料作成、実データ図の生成・目視確認まで一度だけ終了した. 固定実行木は `.runtime/worktrees/p114-run`、`c74c579c1addad248cffcdb9639178b20d5b46b6`. 図の実行木は `.runtime/worktrees/p114-report`、`459f77276898158e92d9c508e15bbd38d018e346`. `.runtime/P114_closure_once_end.json`、`P114_report_collector_once_end.json`、`P114_figure_visual_review_once.json`を保持する. 全79要求の使用量既知、全４件評価済み、3/4成功、CSVは次要求のtoken予約停止で未達. P111の不明２件と採用基準未達は変更しない.

`.runtime/await_p114_collect_bind_p115_once.py`は閉鎖後に収集とP115 bindingを一度だけ終了した. `.runtime/P114_collection_P115_binding_wait_once_end.json`、`P115_binding_once_end.json`を確認し、collectorやbindを重ねて動かさない. serverのrequested_stopは有限比較後の閉鎖理由であり、ユーザーの研究停止指示ではない.

P115は全79要求×４表示=316入力を一度だけ計数し、全件資料と編集木への回収も終了した. 固定実行木は `.runtime/worktrees/p115-run`、`748d3a12268d2b37bd550920383e4adac7c5d75f`. 405公開ソース、197私有ファイルを固定し、全79実入力と一致、欠測・不一致０、４renderer停止、追加生成・API・評価０. `.runtime/P115_analysis_once_start.json`、`P115_collection_once_end.json`、`P115_editor_artifacts_once_end.json`を保持し、count、report、collectorを再実行しない.

最初の `.runtime/run_p115_bound_once.py` は資料フォルダーの不在確認に旧P112名が残っており、実計数より前で停止した. `.runtime/P115_wrapper_preflight_failure_v01.json`と原wrapperを保持. この１か所だけを修正した `.runtime/run_p115_bound_v02_once.py`で初めての実計数を完了した. 固定済み実験ソースは変更していない. 診断結果SHAは`1ce3f8b0a45c7eac37eb5567d5c1b05cb397959bd209f617a28c751e0b8e66f8`.

準備PR485はhead `77ecc51f0529e1edc01af2d4ded86a7bd963bdd2`、merge `48e774d186fc39ca9fc838a12b42d834ff9e6d4f`. P114結果・P115 bindingのPR486はhead `748d3a12268d2b37bd550920383e4adac7c5d75f`、merge `4902a7d979538251c38044a9d9cd9e2020880293`. それぞれ同一headのpush・pull_request両workflowと両accounting-and-syntax job成功後に進めた.

[P115所見](docs/P115_findings.md)と[全316入力](materials/20261025_p115_results/README.md)を参照する. 成功３課題の局所省略は39,005 token、過去fullとの実測増分は126,371. CSVの仮想full費用484,362は仕事予算450,000を超えるため実行済み・実行可能なfull軌跡ではない. 元のP111未知使用量２を補完しない.

次は、推論を省いても増えた公開観測や操作の内訳を全件で絞り、具体的に減らす処理と通常対照を定める. 現時点で次の新モデル実験は開始していない. 診断件数を新規性や品質維持の証明に置き換えず、閾値・seed変更で好成績を探さない. [技術説明](materials/20261025_harness_technical/README.md)、[追加原典](docs/reasoning_state_and_cache_prior_scope_20261025.md)を継承する. 原稿と未見12課題には進まず、ユーザー停止に直ちに従う.

P116は全16条件・283要求・820 API・614私有ファイルの点検と全件資料を一度だけ終了した. 固定実行木は `.runtime/worktrees/p116-run`、`ee4748bdf1fc52e58665c1bebd651c5eb110bd35`. `.runtime/P116_analysis_once_start.json`、`P116_collection_once_end.json`、`P116_editor_artifacts_once_end.json`を保持し、診断・資料生成・回収を再実行しない. 完全報告SHAは `5f8ea54cea0649d14769e97f0d62efa2b70f601ef25de499400ec75dffd3458d`.

全1,849テスト通過. PR488の同一headについてpush workflow40148738864/job121035586259、pull_request workflow40148769750/job121035675149の成功を確認して実施した. mergeは `a6c2bdfc11b7aff0e91030a2fae3a717fa45f6e8`. P115結果のPR487はhead `f03837cc8816c1d4a2d087d87dceb5c14f1e33a5`、merge `030a3fd00b93bafe68b6a6449ab7cc6235798bc8`で閉鎖済み.

[P116所見](docs/P116_findings.md)と[全件資料](materials/20261025_p116_results/README.md)を参照する. 精算の非再入力条件は同一API再取得０だが、大きな観測を繰り返し入力していた. CSVの同一読取再取得と同じ原因へまとめない. 次は観測の内容と出典を全条件で確認し、既存の文書省略・状態保持・通常キャッシュとの差を整理する. 次のモデル実験は未開始. 原稿と未見12課題は保留し、ユーザー停止に直ちに従う.

P117は全16条件・283要求・263観測の固定公開API仕様への照合と全件資料を一度だけ終了した. 固定実行木は `.runtime/worktrees/p117-run`、`12faef73fea288862f78ce7f8e92b8f3cbb281dc`. `.runtime/P117_analysis_once_start.json`、`P117_collection_once_end.json`、`P117_editor_artifacts_once_end.json`を保持し、処理を繰り返さない. 315私有ファイル、22公開仕様ファイル、422公開ソースを固定し、エラー０、追加生成・API・評価０. 完全報告SHAは `99894bcf6c8b2f657049cf818ecd940855b0b357f686157e2876216b43526089`.

全1,859テスト通過. PR490の同一headについてpush workflow40149758036/job121038617175、pull_request workflow40149821152/job121038807778の成功を確認して実施した. mergeは `14a7889db51768ab5a5dd16056eb683d23ff91e0`. P116結果のPR489はhead `1b62e698a5d112d72ddb2716ec01218f13ecbaf6`、merge `f11e965b7eb0064cba9c5c1b1a363ef4867cdf13`で閉鎖済み.

準備時は既存literal解析コードの指紋不足を実記録処理前に検出した. `.runtime/P117_preparation_bookkeeping_failure_v01.json`と原準備スクリプトを保持し、そのソースを追加してから初回の点検を実施した. 終了済み診断の再試行ではない.

[P117所見](docs/P117_findings.md)と[全件資料](materials/20261025_p117_results/README.md)を参照する. ４件の仕様一致量の大部分は精算１件で、この一致だけを根拠とした追加モデル生成は見送る. [PAIRとの範囲比較](docs/counterfactual_adaptation_prior_scope_20261025.md)も継承する. 次は制御に使う実行情報と通常対照との差を具体化する. 次のモデル実験は未開始. 原稿と未見12課題は保留し、ユーザー停止に直ちに従う.

P118は[固定計画](configs/P118_whole_task_single_checkpoint_v01.json)と[準備資料](materials/20261025_p118_preparation/README.md)を用意した. 通常の１回要約対全保持、既知４課題の計８条件. 全1,880テストと構文検査成功、444公開ソースと110実行依存を固定、149台帳・1,642指紋が不変. `.runtime/P118_preparation_once_end.json`と`P118_preparation_publication_once_end.json`を保持する. 実モデル生成は未開始.

最初のworker合成試験で既存費用照合が実行役だけを扱う不具合を検出し、`.runtime/single_checkpoint_worker_failure_v01.json`へ保存した. 既存コードを変えず、要約役と実行役の共通予約から未知を含む全要求を照合する専用実装を追加した. 修正後は全試験成功. 失敗時もモデル生成・API・実記録処理０.

同じ完全headの両workflowと両job成功後、`.runtime/worktrees/p118-run`から有限pipelineを一度だけ起動する. 各条件の80呼出し・450,000 token・1,800仕事秒は要約役を含む. 所有server上限21,600秒. 全８枠とserverが閉じてから成否比較、全費用監査、session確認、全件資料を作る. 成功例を見て条件を増やさず、欠測を埋める再試行もしない.

P118計画の`predecessor_results_publication`は継承元PR439の歴史的記録. 今回の直前結果公開は`latest_results_publication`のPR491、head `5f4dcb08c4ee348425f04fc77736d763ac3c1e52`、merge `d44d66d44deceb210877fdc4fe86486a341c1a29`. 実行前の閉鎖条件はP114の監査・serverとP117の全件診断を明示的に照合する. 過去PRを今回のCI根拠に使わない.

通常要約が有効でも、それ自体は新規性ではない. P14とは課題・実行経路・更新規則が違い、差を要約頻度だけへ帰属させない. P111の基準未達と未知２件、原稿保留、未見12課題の分離、ユーザー停止優先を維持する.

P118はhead `a22cedb40f99b99fd4a488fdc131e62361fccbbd`、固定実行木`.runtime/worktrees/p118-run`から一度だけ起動済み. PR492の同じheadの両workflow・両job成功後に進めた. mergeは`d908e080d3b77ec8a7159a3439b2a120225295c8`. 直前段落の「未開始」は準備時点の記録であり、現在は実行中. [開始の公開記録](reports/P118_execution_start_20261025.json)を参照する.

`.runtime/run_close_p118_once.py`が有限pipeline終了後にaudit・session・全件資料を一度だけ作る. `.runtime/P118_pipeline_once_start.json`、`P118_pipeline_child_once.json`、`P118_pending_execution_handoff.json`を確認してから扱い、起動を重ねない. 中間は`.runtime/read_p118_operational_status.py`の運用状態だけ読む. `.runtime/P118_closure_once_end.json`で全閉鎖を確認後、`.runtime/collect_p118_closed_once.py --expected-head a22cedb40f99b99fd4a488fdc131e62361fccbbd`を一度だけ実行する. collectorの開始・終了印も確認し、失敗時は自動再試行しない. ユーザー停止には直ちに停止印と所有プロセスで対応する.

[要約の出典判定と型別保持の原典照合](docs/checkpoint_source_and_type_prior_scope_20261025.md)を追加した. この調査でP118の固定条件や実行ソースを変更していない. 単純な要約選別や型別保持を新手法の中核へ読み替えない.

P118の閉鎖後回収と図生成は、`.runtime/await_p118_collect_figure_once.py`が有限の待機を開始済み. `P118_collection_wait_once_start.json`と`P118_collection_wait_once_end.json`で管理する. 上記collectorを手動で重ねて起動しない. 図の固定木は`.runtime/worktrees/p118-report`、head `7d0d1fe92ac98507d31256a7bad269a5d95a777c`、PR493の同一head両workflow・両job成功済み. 実データPNGは全閉鎖後に生成し、必ず目視してから公開する.

費用分解と要約前の完全要求SHA照合も[別の有限集計](docs/experiments/P118_pair_controls.md)として準備した. 固定木は`.runtime/worktrees/p118-pairs`、head `c0f0e622e2a984a27c8fbae59081bc8bfc7f5904`、PR494の両workflow・両job成功済み. `.runtime/await_p118_pair_controls_once.py`が回収完了を待機中で、`P118_pair_wait_once_start.json`と`P118_pair_wait_once_end.json`を確認する. この集計も手動で重ねない. 現在の編集branchと所有processの最新情報は`.runtime/P118_pending_execution_handoff.json`を優先する. 未知・失敗を保持し、全８条件と全４対をまとめてからProject・materialsへ反映する.

P118の全８条件、所有server、監査、session確認、全件資料、実データ図、全４対の費用分解は一度だけ終了した. `.runtime/P118_closure_once_end.json`、`P118_report_collector_once_end.json`、`P118_figure_collection_once_end.json`、`P118_pair_collection_once_end.json`、`P118_collection_wait_once_end.json`、`P118_pair_wait_once_end.json`を保持する. ２つの待機processは完了済みで、collector・描画・対比較を手動で再起動しない. 実PNGは`.runtime/P118_figure_visual_review_once.json`で目視を記録した.

[全件所見](docs/P118_findings.md)のとおり、通常要約4/4、全保持3/4成功. 写真とCSVで要約を採用し、精算と返金では起動していない. CSV要約は440,461 token、77 APIで完了. 全保持CSVは時間上限で最後の使用量１件が不明. 全160要求・407 API・８評価を残す. 要約条件合計893,529 token、全保持既知807,463＋不明１件. 両側成功３件の導出差は+4,243 tokenで、固定監査の全８件既知を前提とするnullと採用基準未達を変更しない.

完全監査SHAは`25d37fd0d64441b92134a769d13e66298037e53fcb092acbc570c8edeb8a1f77`. 事前固定した３つの完全headで実行し、PR492・493・494のそれぞれ同一head両workflow・両job成功を確認した. 全件閉鎖後の図と対比較で追加モデル生成・API・独立評価は０. 元のP111不明２件は別の要求として保持する.

通常要約で４件を完了した経路を、今後の品質の比較対象へ残す. [同じ応答に引き継ぎ情報を載せる候補](docs/inline_checkpoint_candidate_scope_20261025.md)は検討範囲のみで、方式の実装・性能・独自性は未確立. 専用要約のinput 37,350 tokenをそのまま将来の節約実績へ使わない. 追加指示、schema、出力、形式不備、後続行動を含む通常対照を具体化する. 次のモデル実験はまだ開始していない. 原稿と未見12課題は保留し、ユーザー停止を優先する.

P119は[通常の別呼出し要約対同時出力要約](configs/P119_whole_task_inline_checkpoint_v01.json)の全８条件を固定した. [準備資料](materials/20261025_p119_preparation/README.md)に実装と試験を記録. 新規52件を含む全1,936テストと構文検査が成功、476公開ソースと116実行依存を固定、154台帳・1,697指紋を照合した. `.runtime/P119_preparation_once_end.json`と`P119_preparation_publication_once_end.json`を保持する. モデル生成はまだ開始していない.

同時出力のschemaと指示を一度だけ追加し、古い完結履歴だけの要約を受け取る. コードと順序付き参照IDを変えず、metadataだけを実行引数から分離する. 原応答は保存し、当該ターンの閉鎖後、次の入力が短い場合だけ要約を採用する. 不正な要約や非短縮でも対応するmetadataを両候補の表示から取り除く規則を明示した. 同じ呼出しの未実行結果を要約せず、意味の正しさを確認したとはしない.

同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功後、`.runtime/worktrees/p119-run`から有限pipelineを一度だけ起動する. ８初回入力＋通常要約１入力＋合成inline３入力の12件を語彙計数し、各条件80呼出し・450,000 token・1,800仕事秒内で固定順に実行する. 所有server21,600秒. 全８枠とserverが閉じてから全件照合、session費用、全件資料を作る. 中間成否を見て条件を変えず、不明を埋める再試行をしない. ユーザー停止を優先する.

P118の通常要約側をそのまま比較に残す. 同時出力側との差には、要約時点、指示、schema、出力枠の競合、後続行動も含まれる. 専用要約の入力37,350 tokenを今回の節約へ転用しない. 同時出力や形式検査の存在だけを新規性としない. 原稿と未見12課題は保留する.

P119はPR496、head `391e2921beeb8f53cd87b086289729609a4b5c62`の両workflowと両job成功後に一度だけ起動済み. mergeは`32bf29dc19444866fcf5ca021287c56c7c40b52c`、2026-10-25T04:25:02Z. [開始記録](reports/P119_execution_start_20261025.json)に12入力の事前計数と指紋を保存した. ８初期入力、別呼出し要約１入力、合成inline３入力を確認し、固定順の全８条件を実行中. 中間成否は読んでいない.

実行木は`.runtime/worktrees/p119-run`. `.runtime/run_close_p119_once.py`がpipeline終了後に監査、session点検、全件資料を一度だけ作る. `.runtime/P119_pipeline_once_start.json`、`P119_pipeline_child_once.json`、`P119_pending_execution_handoff.json`を確認し、同じ処理を重ねて起動しない. 状態確認には`.runtime/read_p119_operational_status.py`を使う. 停止指示には`.runtime/P119.stop`と所有processで対応する.

全閉鎖後の[図と対比較](configs/P119_reporting_v01.json)も準備した. 新規４件を含む全1,940テストと構文検査成功、73ソースを固定. 合成previewを目視したが、実データ図は未生成で、実際の図の目視が別途必要. `.runtime/P119_synthetic_figure_review_once.json`は実結果のレビューではない. 155台帳・1,704指紋が不変. 実行器と予算を変えていない.

`.runtime/P119_closure_once_end.json`の全閉鎖後、専用collectorで全件資料を一度だけ回収する. 図と対比較もその集計headの両workflow・両job成功後に行う. 途中成否を見て条件や対象を変えず、未知を埋める再試行をしない. 原稿と未見12課題は保留する.

## P119 全件閉鎖後の引継ぎ（2026年10月25日）

P119は05:52:49 UTCに監査と全件資料を閉鎖し、05:52:57 UTCに図と全４対の集計を終えた. 所有serverの停止と実測PNGの目視を確認した. 完全監査SHAは `b6fa3dda80c953752df919981f30e329faeafd3fd86c5c9d285bfaab11227f70`. 再実行しない.

任意の同時出力は２機会ともcheckpointを出さず、採用０件. 別呼出し4/4対同時出力3/4でCSVの成功を失ったため採用基準未達. 次は要約欄を必須引数として指定する通常対照を、新しい有限計画として実装・確認する. この変更だけを新規性としない. P119のモデル、計画、履歴、記録、結果を変更しない. [全件所見](docs/P119_findings.md)と[技術説明](materials/20261025_inline_checkpoint_technical/README.md)を参照する.

原稿と未見12課題は保留する. ユーザーから停止指示はなく、実験を優先して継続する. 今回のserverのrequested_stopは有限実験終了時の処理で、ユーザーによる作業停止ではない.

## P120 必須欄を指定する通常対照の準備（2026年10月25日）

現在の編集ブランチは`research/p120-results-20261025`. [固定計画](configs/P120_whole_task_required_inline_checkpoint_v01.json)と[準備資料](materials/20261025_p120_preparation/README.md)を追加した. 新規34件を含む全1,974テストと構文検査が成功、503ソースと118実行依存を固定し、157来歴台帳・1,747指紋を照合した. モデル生成は未開始. P119の全件結果はPR498でmainへ反映済み.

同時出力の要約を求める１回だけcheckpointを必須引数として指定し、指示文も出力を求める. tool_choiceはauto、元のコードと参照IDをそのまま一度だけ実行し、欠落・不正・打切りでは古い履歴を残す. 追加生成や別呼出しへの切替はしない. 出力上限4,096はコードと要約で共有する. 必須指定は実際の生成・採用や意味の保証ではない.

同じ完全headのpushとpull_request両workflow、両accounting-and-syntax job成功後、専用の`.runtime/worktrees/p120-run`から有限pipelineを一度だけ実行する. 全８初回入力と要約関連４入力を語彙計数し、各条件80呼出し・450,000 token・1,800仕事秒内で固定順の８条件を実行する. 所有server上限21,600秒. 全件とserverが閉じてから成否、要約の実採用、全役の費用を読む. 旧P119の任意欄は２機会とも欠けており、その不発動とCSVの成功損失を上書きしない.

原稿と未見12課題は保留する. ユーザーから停止指示はなく実験を優先して継続する. 必須欄の追加自体を新規性とはしない.

P120はPR499、head `d2306e6461cf4aaadf739584d724fcdb05247edf`の両workflowと両job成功後に一度だけ起動済み. mergeは`3a6d5ff9d19ac23b139a49d74e2e7bc0d76f5971`、2026-10-25T06:15:56Z. [開始記録](reports/P120_execution_start_20261025.json)に初回８入力、別呼出し要約１入力、合成inline３入力の計数を保存した. 生成を伴わない事前確認は12入力、1,235ソース指紋. 固定順の全８条件を実行中で、中間成否は読んでいない.

実行木は`.runtime/worktrees/p120-run`. `.runtime/run_close_p120_once.py`は起動済みで、pipeline終了後に監査、session点検、全件資料を各１回作る. 開始印、子process印、`.runtime/P120_pending_execution_handoff.json`を確認し、起動を重ねない. 運用状態は`.runtime/read_p120_operational_status.py`で確認する. ユーザー停止を優先する.

[終了後の図と対比較](configs/P120_reporting_v01.json)は73ソースを固定した. 全1,974テストと構文検査成功、合成図を目視. 実結果の図は未生成で、全閉鎖後の別途目視が必要. 158台帳・1,753指紋が不変. 必須欄の指示とschemaを費用に含め、要約要求回数と実際の履歴置換を区別する.

全８枠と所有serverの閉鎖後、専用collectorで一度だけ回収する. 図と対比較も、その集計headの両workflow・両job成功後に各１回行う. 中間成否に応じた条件変更や未知を埋める再試行はしない. 原稿と未見12課題は保留する.

P120終了後の集計はPR500で両workflow・両job成功、head `665aa195383c192beed8cd4da5c383e8632bfe2f`を固定. `.runtime/worktrees/p120-report`のwatcher `.runtime/await_p120_collect_report_once.py`も一度だけ起動済み. pipelineとwatcherの開始・終了印を確認し、どちらも起動を重ねない. 実図の目視は全閉鎖後に必要.

P120実行中に[P121の診断範囲](configs/P121_checkpoint_inputs_scope_v01.json)を固定した. 既知P118/P119と未読P120の全24枠を含む. 語彙専用binaryで実際の入力と古い履歴の復元入力を比較し、各後続要求での入力差を累積する. 同時出力metadataの非再入力は両入力に維持する. 同じ行動列と実際の予算通知を固定した診断で、別方式の実測経路や成功ではない.

P121は新規９件を含む全1,983テストと構文検査成功、126ソースを固定. 159台帳・1,879指紋を保持する. 準備時に実記録、P120中間成否、課題databaseは読まず、計数と生成は０. 全元条件の閉鎖とこの準備headの両workflow・両job成功後に `measure_checkpoint_realized_inputs.py bind` を一度だけ行う. 束縛した計画を含むheadの両workflow・両job成功後に `count` を一度だけ行い、全24枠の資料を作る. P120の起動済み処理を先に完結させる.

## 2026年10月25日: P120の必須同時出力を閉鎖し、原稿執筆を再開

P120全８条件を閉鎖した. 必須欄の同時出力は写真とCSVで要約を生成・採用した. 写真は両方式成功、139,871→129,374 token（約7.50%減）、17→16モデル要求、APIは両側102だった. 一方、CSVは同時出力がtoken予約制約で未達となり、別呼出し4/4対同時出力3/4で成功損失１. 全167要求の使用量既知、1,774,173 token、422 API、８評価. 全体の採用基準は未達で、成功例だけを一般化しない. P121は全24枠・487保存要求・974入力のbindingを完了し、計数は同一headの両CI成功後. 新規モデル呼出しは０. 10月25日の指示により原稿執筆を再開し、P120とP121で追加実験を区切る. 新規性は未確立、未見12課題は未閲覧.

現在の作業ブランチは `research/p120-results-20261025`. P120のrun、collector、描画、対比較、P121のbindingと登録は一度だけ完了した. 再実行しない. P121計数の専用固定木と同一headのpush/PR両workflow・両job成功を確認後、`.runtime/run_p121_bound_once.py`から一度だけ計数する. 原稿の結果非依存の本文と全件表builderは `.runtime/checkpoint_letter_working_20261025` で準備済み. 新旧の結果を混ぜず、閉じた全件の結果と診断を別版へまとめる. [区切りと原稿再開](docs/letter_experiment_cutoff_20261025.md).

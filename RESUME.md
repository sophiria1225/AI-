# 研究と実行の引き継ぎ

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
目標は性能を維持した全仕事tokenの削減. 最新の閉じたP120比較は別要約4/4対同時要約3/4成功で未達. P122の固定24条件を継続中. 再要約を共有予算付き推論、実課題worker、保存記録監査へ接続し、単発別要約・反復別要約・反復同時要約の12条件比較を準備した. 追加26件を含む全2,037テストと構文検査が成功. 実機の事前計数とP123生成は未実施. P122全件閉鎖と確認後に、有限計画、同一headの両CI、事前計数を確定して進める. 要約の意味保存、品質維持、新規性は未確立. P122の途中成否、原稿、未見12課題は扱いを変えない. [次の比較仕様](docs/experiments/P123_whole_task_rolling_checkpoint.md).
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

## 最新の目的と指示

最終目標は、必要な情報と処理、最終成果の品質を維持し、不要な取得、共有、モデル呼出し、実行、検証を減らすこと. 制御、失敗、再取得を含む全仕事で評価する. 履歴短縮や記録の厳密さ自体を新規性に置き換えない.

ユーザーは停止を指示するまで作業継続を希望している. 停止指示はない. 10月25日にP120/P121で一度区切って原稿を書いた後、「誤差か、特定のパターンだけかを確認して実行を続ける」と指示された. **現在はP122の反復確認を進める.** P120の方法と１条件の予算を固定したまま、同じ設定１組と別seed２組を全４課題で比較する. 過去の区切りはこの新しい反復確認を禁止する指示ではない. [現在の計画](docs/experiments/P122_checkpoint_replication.md).

10月31日までのレター投稿が目標. 著者、所属、著者順は未確認. 教授への送信と学会投稿は行っていない. 過去の原稿保留や実験待機は現在の指示ではない.

## 現在の作業木

| 用途 | 場所 |
|---|---|
| 編集木 | `/Users/tp26013/AI-/.runtime/worktrees/p107-prep` |
| 現在のブランチ | `research/rolling-checkpoint-live-20261025` |
| モデル、AppWorld、私有記録、終了印 | `/Users/tp26013/AI-` |
| Python | `/Users/tp26013/AI-/.runtime/p3_ci_venv/bin/python` |
| PDFと図の環境 | `/Users/tp26013/AI-/.runtime/reporting-venv/bin/python` |
| 原稿 | `papers/202610_letter/checkpoint_cost_v01/` |

ストレージ用checkoutと固定実行木の追跡済みファイルを編集しない. `git status`、現在のbranch、確認済みoriginを確認して作業する. 変更先は `sophiria1225/AI-` と専用[Project 1](https://github.com/users/sophiria1225/projects/1)のみ. Projectの全120件を保持し、部分同期の前後も全件から作業ボードを生成する.

## 終了済み処理を再実行しない

P120の全８条件、所有server、監査、収集、図の生成と目視、全対比較は終了. P121のbinding、全974入力の計数、資料作成、収集も終了. 原稿の生成、全５頁の目視と公開も終了し、PR503はmerge済みである.

| 処理 | 固定head／公開結果 |
|---|---|
| P120モデル比較 | `d2306e6461cf4aaadf739584d724fcdb05247edf`、`p120-run`、[所見](docs/P120_findings.md) |
| P120資料化 | `665aa195383c192beed8cd4da5c383e8632bfe2f`、`p120-report` |
| P121 binding | `e89a9bb39c03d951b819cbe3712c2f6825bee1d5`、`p121-bind` |
| P121計数 | `925b4315e6dc573a6a5f4dd28066ff4e2c764d16`、`p121-run`、[所見](docs/P121_findings.md) |
| 原稿の公開 | [PR503](https://github.com/sophiria1225/AI-/pull/503)、head `f3a2b63c9ec7c603be26ac8b48d7738400ca6525`、merge `263dad32be21463deaf4467a9efe6b7eb4db0fba` |

私有`.runtime`の `P120_closure_once_end.json`、`P120_collection_wait_once_end.json`、`P121_collection_once_end.json`、`P121_editor_artifacts_once_end.json`、`P121_letter_publication_once_end.json`、`P121_letter_merge_once.json`を参照する. 古いwrapper、watcher、collector、publisherをもう一度起動しない. serverの自然な閉鎖はユーザーによる研究停止指示ではない.

最新の私有引き継ぎは `.runtime/checkpoint_letter_writing_handoff_20261025.json`. 公開台帳の一覧は `.runtime/research_ledger_names.json`. 現在169台帳、1,983指紋であり、終了済み結果、固定入力、旧原稿のbytesを保持する. 新しい版が必要な場合は旧版を上書きせず別版にする.

## 主張の範囲

写真の7.50%削減は別呼出し要約との１対比較. P120全体は4/4対3/4成功で採用基準未達. 精算と返金は要約が起動せず差０. 成功３課題の小計、入力差D、要約専用呼出しの省略を、全課題の品質維持や要約費用０へ読み替えない.

P118全保持CSVの不明１要求と、P111の不明２要求を保持する. P121で入力を計数できても終端の総使用量は補完しない. 未見12課題の要求文、データ、正解は未閲覧. 既知４課題の順次開発を未見評価とはしない. 通常の同時生成や構造化状態には先行研究があり、新規性は未確立である. [主張と根拠の点検](docs/checkpoint_letter_review_20261025.md).

原稿の本文と文献は４頁、英文要旨１頁. 公式クラス未使用で、著者情報も未設定. 公式クラスの過去の403や検証画面を別経路で回避しない. 教授用459字案は`.`を使い、中黒なし. 古い456字案と旧原稿は保存する.

## 次に進めること

P122はhead `5ddbba8c8b4614bc9856202942dc28caf5b204f7`、専用の `.runtime/worktrees/p122-run` から一度だけ起動済み. 両CIと初回入力確認は終了. `.runtime/run_close_p122_once.py`が全24条件とserver閉鎖後に監査、session計上、全件資料を作る. 開始印 `.runtime/P122_pipeline_once_start.json` と終了印 `P122_closure_once_end.json`を確認し、再起動しない. 運用状態は `.runtime/read_p122_operational_status.py`、引き継ぎは `.runtime/P122_pending_execution_handoff.json`. 中間の成否や費用を読まない. 全件終了後は `.runtime/collect_p122_closed_once.py`で一度だけ資料を回収する. 停止印は `.runtime/P122.stop`. P120/P121の終了済みwrapperを再起動しない. 詳細は[次の作業](docs/next_actions.md).

再要約候補は共有予算付き推論、実課題worker、全件監査、有限driverまで接続済み. 追加26件を含む全2,037テストが成功した. [比較仕様](docs/experiments/P123_whole_task_rolling_checkpoint.md)と[準備資料](materials/20261025_rolling_checkpoint_connection/README.md)を参照する. 実機事前計数とP123生成は未開始で、実行用configも未作成. P122全件閉鎖と結果確認後、閉鎖記録を結び付けた計画を固定し、同一headの両CIと事前計数を通して12条件へ進む. P122実行木に新部品を読み込ませない.

生のプロンプト、私有推論、完全履歴、正解、モデル重み、認証情報をGitへ登録しない. 停止指示が来た場合は従う. [AGENTS](AGENTS.md)／[現在状態](docs/current_status.md).

詳細な経緯は[整理前RESUMEの固定版](https://github.com/sophiria1225/AI-/blob/263dad32be21463deaf4467a9efe6b7eb4db0fba/RESUME.md)へ保存されている. 各時点の「未開始」「次は」「原稿保留」を現在の状態へ適用しない. [10月22日の引き継ぎ](docs/handoff_20261022_account_switch.md)も履歴として保持する.

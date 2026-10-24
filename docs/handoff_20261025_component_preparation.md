# 2026-10-25 引継ぎ：P103準備時点

## 目的と採否

必要情報と最終品質を保ち、制御・失敗・再取得を含む仕事全体の費用を減らす. 新方式、一般品質維持、採録に足る主貢献はまだ確立していない. 10月25日に追加確認・採否、29〜30日原稿整備、31日投稿が目標. ユーザーは止める指示まで実装継続を許可している. 著者情報は未確認で創作しない. 教授への連絡・投稿は実行しない.

## 現在の作業場所と読み方

編集用作業木は `/Users/tp26013/AI-/.runtime/worktrees/p84-prep`. 元の `/Users/tp26013/AI-` の追跡ファイルを編集しない. Pythonは `.runtime/p3_ci_venv/bin/python`. まず `AGENTS.md`、`RESUME.md`、`docs/current_status.md` の現在欄と最新結果を読む. 古い本文・旧計画を最新状態として扱わない. GitHub変更先はこのrepoと専用Projectのみ.

終了済み結果や固定ソースは変更せず、新版を作る. 台帳一覧 `.runtime/research_ledger_names.json` の全source_sha256、P99初期確認924件、P101初期確認887件を維持する. 実験・merge前に同じ完全SHAのpushとpull_requestの両workflow、および両accounting-and-syntax job成功を確認する.

## 実行中P101

原生成は `.runtime/worktrees/p101-run`、head `879f04696a8129252b47678f92ee4e1031a09ea7`. ６保存入力×通常tool_choice２設定×３反復の36枠. 入力以外の変更や追加反復をせず、結果と費用は閉鎖まで読まない. 進捗確認は編集木の `scripts/inspect_choice_context_operations.py --storage-root /Users/tp26013/AI-` の許可列のみ. 生のstatusや応答、要求、途中集計を出力しない.

旧終了待機処理は報告コマンドの引数不整合があり、監査・報告段階０で終了済み. 旧処理を再開しない. 修正版は `.runtime/worktrees/p101-reporting-v02`、head `f210497f84ab7e8659bdfd2c65f924f6aa7de6a8`、状態 `.runtime/P101_closure_operations_v02/status.json`. 元生成と推論器の終了後に元監査・資料を各一度実行する. 修正は生成開始後・結果未閲覧であり、全報告手順を生成前から不変とは記述しない. 詳細は `materials/20261025_p101_corrected_reporting_started/README.md`.

P101閉鎖後は全36枠・12群・66組の監査結果を確認し、７頁資料を全頁目視する. 不明や失敗を差し替えず保存する. その後P102の最終計画を作り、全既知P101応答と元P94前史をhash固定する. P102 runtime/reportingは準備済みだが、最終計画 `configs/P102_choice_action_execution_v01.json` はまだない. 実行headの両CI前に実行しない. 原runtime・audit・reportを編集しない. 追加モデル０、全36枠を保持し既知出力を元順序で新しい環境に与える. 課題成功評価ではない.

## 並行して準備したP103

現行P98構文hashはPython ASTだけでなく参照指定等も含む. 元33位置・37生成のうち、実際にPython ASTが異なる内訳は未確認. `docs/experiments/P103_submission_components.md` と `configs/P103_submission_components_v01.json` を固定し、10追加検査・全1,658検査成功. 準備をpushし両CI/job成功後に別作業木から `scripts/inspect_submission_components.py --storage-root /Users/tp26013/AI-` を一度だけ実行する. 180秒、追加生成・API・保存コード実行・評価器・DB・予約評価群０. 失敗は保持し自動再試行しない. 結果が主張を弱めても残す.

## 閉じた結果と原稿

P99通常tool_choice対照は両方式3/4成功、成功３課題のtoken差０、CSV双方未達で不採用. P97回復通知も３方式各3/4、成功側差０で不採用. P100はP97欠測の条件付き範囲であり、未知実費の補完ではない. P98は全24実行426生成・60組の実証で、対数を独立標本としない.

原稿候補は `papers/202610_letter/execution_evidence_controls_v02/`、本文４頁＋英文１頁、P99と先行ID修正を反映済み. PDF SHA256は `291f82248bf7e8f12a0f17cc791644d22e479701f20d788d3f98e7f7d1d741a4`. ２件のunderfull警告を残し、はみ出し０、全５頁確認済み. P103の指標解釈を次版で修正する必要があり、現状を投稿可能とはしない. 表題と教授向け456字あらましは保持する.

公式IEICEクラス取得は一度HTTP403で失敗済み. 自動再取得や経路変更をしない. 旧P98稿の3.4aミラー確認は現行稿や公式頁数の確認ではない. Heldout12は未読. プロセスや認証情報、重み、完全履歴、内部推論をGitへ出さない.

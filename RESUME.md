# 再開の入口：継続指示を受け、P133比較を準備

2026-10-27朝、ユーザーは就寝中も実験を続けるよう明示した。以前の06:00目安は作業停止条件ではない。通常の会話で実行を止めず、明示停止に従う。各cohortは条件・有限予算・source・両CIを固定する。原稿本文はユーザーが執筆する。

P133は準備中で、まだモデル生成を開始していない。P123で成功した元のguide/full receipt/API80/rolling separateを共通にし、通常制御対追加要約の実測費用予測による採否を比較する。既知CSV1課題×固定seed57/157×2方式の4条件、各80calls/450000tokens/1800作業秒、所有server4時間・12:30 JSTまで。初回要約は同じ、2回目以降の予測は保証ではない。全失敗・unknown・未実施を保持し、通常校正を新規性と言い換えない。[P133仕様](docs/experiments/P133_whole_task_checkpoint_payback.md)。

直近P132は05:11 JSTに全2評価と所有serverを閉鎖、05:28に結果公開を完了した。offは171013確定token/API上限、onは213642既知token＋unknown1/時間上限、両失敗・共通成功0・gate false。一覧はonで2回提示された。現在所有モデルは停止済み。[P132所見](docs/experiments/P132_findings.md)／[図表](materials/20261027_p132_results/figures/README.md)。

最強の既存positiveはP123通常rolling separateが既知4/4成功を保って単発要約比12.07%の全仕事tokenを削減した観測である。同時反復の新候補は強い通常対照より高費用だった。既存方式の効用と新技術の成立を分け、一般品質維持・新規性の中心主張は未達とする。[P123所見](docs/P123_findings.md)。

並行して、成功API返答に基づく対象ごとの未充足fieldをcheckpoint越しに保持する候補を別に検証する。P132の旧monitorのunknownを維持し、公開契約で正当化できるpartition合成を別versionへ分離する。P133へ途中で機構を混入せず、将来の比較は通常進捗チェックリストと同じ証拠・予算を使う。

既存run/prep・失敗・不明費用は不変。P132開始snapshot186台帳/2231束縛、公開後global189/2290を区別する。新P133も自身の開始snapshotを固定し、将来台帳を遡及適用しない。P130/P131の起動前失敗と約3時間の空白は保存済み。モデルは単一serverで直列、保存生成codeはhost実行しない。未見12課題は別確認計画まで未閲覧。

変更先はsophiria1225/AI-と[専用Project1](https://github.com/users/sophiria1225/projects/1)のみ。生prompt・推論・生成task code・課題値・認証・評価器本文は公開しない。原稿・教授への連絡・投稿は行わない。

[P128所見](docs/experiments/P128_findings.md)／[P129所見](docs/experiments/P129_findings.md)／[P130/P131経過](docs/experiments/P131_execution_status_20261027.md)／[P0–P123履歴](docs/research_history_review_20261026.md)。

# 次の作業：固定比較を実行し、coverage候補を別に検証

2026-10-27朝、ユーザーは就寝中も実験を続けるよう明示した。以前の06:00目安は作業停止条件ではない。通常の会話で実行を止めず、明示停止に従う。各cohortは条件・有限予算・source・両CIを固定する。原稿本文はユーザーが執筆する。

P133は06:46:23.979 JSTに開始し、06:48:09 JSTにrootが最初のactor送信とmodel処理中を確認した。要求・生成本文、usage、task成否は未読。これは時点付きの開始確認であり、全4条件の完了や改善ではない。[開始記録](experiments/P133_execution_start_20261027.md)。P123で成功した元のguide/full receipt/API80/rolling separateを共通にし、通常制御対追加要約の実測費用予測による採否を比較する。既知CSV1課題×固定seed57/157×2方式の4条件、各80calls/450000tokens/1800作業秒、所有server4時間・12:30 JSTまで。初回要約は同じ、2回目以降の予測は保証ではない。全失敗・unknown・未実施を保持し、通常校正を新規性と言い換えない。[P133仕様](experiments/P133_whole_task_checkpoint_payback.md)。

直近P132は05:11 JSTに全2評価と所有serverを閉鎖、05:28に結果公開を完了した。offは171013確定token/API上限、onは213642既知token＋unknown1/時間上限、両失敗・共通成功0・gate false。一覧はonで2回提示された。P132の所有serverは停止済みで、P133は別の所有serverで開始した。[P132所見](experiments/P132_findings.md)／[図表](../materials/20261027_p132_results/figures/README.md)。

最強の既存positiveはP123通常rolling separateが既知4/4成功を保って単発要約比12.07%の全仕事tokenを削減した観測である。同時反復の新候補は強い通常対照より高費用だった。既存方式の効用と新技術の成立を分け、一般品質維持・新規性の中心主張は未達とする。[P123所見](P123_findings.md)。

並行してP134を準備する。成功した型付きAPI返答だけから対象ID×必要fieldの未充足を保持し、accepted checkpointの次actorに一度だけ提示する。従来のraw anchor／残件数のみ／対象と不足field、既知CSV1課題×seed57/157の6条件。主比較の2方式は同じ証拠・明示query・guide、rawはP123元interfaceを維持する。全方式で観測とcaptureを共通化し、unknown/open列挙を残件0にしない。各80calls/450000tokens/1800作業秒/API80、所有server6時間・18:00 JSTまで。P133全4枠とserver閉鎖・collector完了、P134 source固定・両CI成功後にだけ開始する。P133途中効能に基づく条件変更はせず、全失敗・不明費用・未実施を保持する。P134はまだモデル未実行で、有効性・新規性は未確認。[P134仕様](experiments/P134_whole_task_observed_obligations.md)。

既存run/prep・失敗・不明費用は不変。P132開始snapshot186台帳/2231束縛、公開後global189/2290を区別する。P133開始snapshotも189台帳/2290束縛に固定し、後続global190/2300を遡及適用しない。P134は開始前に自身の台帳snapshotを固定する。P130/P131の起動前失敗と約3時間の空白は保存済み。モデルは単一serverで直列、保存生成codeはhost実行しない。未見12課題は別確認計画まで未閲覧。

1. P133はsource・両CIを固定して開始済み。元run/prep・条件・予算を変更せず、通常会話で実験を止めない。
2. 全4条件の完了・所有server閉鎖を監視し、途中効能を見て条件を選び直さない。終了と研究目標達成を混同しない。
3. 全4条件・未知費用・予測の実適用と空振りを回収して監査・図表・専用Projectへ反映する。
4. P134の全worker→trace→cohort→reportを合成境界で確認し、source・両CIを固定する。P133閉鎖後に新6条件を一度実行し、各条件の失敗と不明を含め比較する。成功例のみの選別、seed探索、既存失敗の置換はしない。

変更先はsophiria1225/AI-と[専用Project1](https://github.com/users/sophiria1225/projects/1)のみ。生prompt・推論・生成task code・課題値・認証・評価器本文は公開しない。原稿・教授への連絡・投稿は行わない。

[P128所見](experiments/P128_findings.md)／[P129所見](experiments/P129_findings.md)／[P130/P131経過](experiments/P131_execution_status_20261027.md)／[P0–P123履歴](research_history_review_20261026.md)。

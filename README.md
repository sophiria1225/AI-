# AIハーネス研究

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P122の全24条件を開始した. 既知４課題×２方式×seed基数57/157/257で、方法と各条件の予算はP120のまま. 同じ完全headの両workflow・両job成功、初回24入力と要約関連４入力の確認が完了. 全24枠と所有serverの閉鎖後に全件の成否と費用を読む. P120は別要約4/4対同時出力3/4成功で、全体の性能維持は未達. 写真の7.50%減は両側成功した１対だけである. 今回は全３対の差の範囲と標準偏差、成功損失、要約未起動を併記する. 少数の固定設定を統計的非劣性や未見課題への一般化とは呼ばない. 原稿と未見12課題は保持する. [開始と判定](materials/20261025_p122_running/README.md).
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

必要な情報と処理、最終成果の品質を保ち、不要な取得、共有、モデル呼出し、実行、検証を減らす. 制御、失敗、再取得を含む仕事全体の費用で評価する.

## 現在の作業

2026年10月25日の最新指示により、P120の観測差のばらつきと成功損失をP122で反復確認する. P120/P121と原稿作成は終了済み. P122は同じheadの両CI成功と初回入力確認後、専用固定木で実行中. [準備資料](materials/20261025_p122_preparation/README.md).

| 項目 | 結果と限界 |
|---|---|
| P118: 全保持と別呼出し要約 | 成功3/4対4/4. 共通成功３課題の総tokenは要約側で約0.95%増. 全保持CSVの使用量不明１要求を保持 |
| P119: 別呼出しと任意の同時要約 | 成功4/4対3/4. 同時要約は要求２、採用０ |
| P120: 別呼出しと必須の同時要約 | 成功4/4対3/4. 同時要約は要求２、採用２. 写真で7.50%減、CSVで成功損失 |
| P121: 保存行動列上の入力差 | 全24枠、487保存要求、974入力. 既知486要求で元の入力計数と一致. 不明１要求の総使用量は補完しない |

[全保持との比較](docs/P118_findings.md)／[任意欄](docs/P119_findings.md)／[必須欄](docs/P120_findings.md)／[入力差と要約費用](docs/P121_findings.md). ３群の採用基準は全て未達である.

## 原稿と資料

- [現在のPDFとソース](papers/202610_letter/checkpoint_cost_v01/README.md): 日英題名を維持. 本文・文献４頁、英文１頁の全５頁を目視済み. 公式誌面クラスは未使用.
- [全24条件の表](papers/202610_letter/checkpoint_cost_v01/all_conditions.csv)／[P120全件の図](materials/20261025_p120_figures/README.md)／[P121の全件資料](materials/20261025_p121_results/README.md).
- [教授用459字あらまし](papers/202610_letter/checkpoint_cost_v01/professor_abstract_ja.txt): 句点は`.`、中黒なし. 本文用の短い要旨とは別案.
- [原稿の主張と研究上の残件](docs/checkpoint_letter_review_20261025.md): 数値上の正結果と、未確立の新規性を区別.

著者、所属、公式様式は未完了. 教授への送信や学会投稿は行っていない. 10月31日までのレター投稿を目標とし、採択を保証しない. [投稿情報](papers/202610_letter/checkpoint_cost_v01/submission_metadata.json).

## 継続と保存

[RESUME](RESUME.md)に現在の作業木、終了済み処理、再実行しない処理をまとめた. [現在の状態](docs/current_status.md)／[次の作業](docs/next_actions.md)／[作業ボード](docs/task_board.md)／[専用Project](https://github.com/users/sophiria1225/projects/1).

変更先は `sophiria1225/AI-` と専用Projectのみ. 元の成否、欠測、固定条件、全公開指紋を保持する. 未見12課題は未閲覧. 終了済みの実験を再試行せず、新しいモデル比較には事前の条件と有限予算が必要である.

過去の実行中表示や原稿保留の指示は、[整理前READMEの固定版](https://github.com/sophiria1225/AI-/blob/263dad32be21463deaf4467a9efe6b7eb4db0fba/README.md)に残す. その当時の次の作業を現在の指示として再実行しない. [最終目標](docs/research_objective_20261022.md)と[10月22日のアカウント引き継ぎ](docs/handoff_20261022_account_switch.md)も保持している.

# AIハーネス研究

**10月31日までに、電子情報通信学会へ２段組・４ページのレターを投稿する準備を進めています。** 主要実験とあらましは10月23日、追加確認は25日、原稿は29〜30日が目標です。推薦分野は和文論文誌D、人工知能・D140803「知識の共有・再利用」。採録時期の約束ではありません。[４ページへの変更と最新の構成](docs/letter_four_page_update_20261021.md)／[当初の日程と公式規定](docs/letter_october2026_plan.md)。

## 今どこまで分かったか

**独自方式の新規性・有効性は、まだ確認できていません。** 既存の記憶保持方式の導入・校正と、新しい研究上の貢献を区別しています。

| 状態 | 確認できたこと／残っていること |
|---|---|
| 完了：基準比較 P11〜P14 | 全履歴4/4、直近履歴3/4、FOCUSに基づく保持2/4、通常台帳2/4。今回の４開発課題では品質を保つ総費用削減は未達。原論文の完全再現や一般的な優劣とは扱わない。 |
| 完了：P16・候補を見送り | 24生成、形式適合17出力・160項目を照合。元入力でも未支持の操作完了を確認できず、要求退避の追加価値は示せなかった。[全結果](docs/P16_findings.md)。 |
| 修正中：比較基準の不備 | 宣言する台帳定義は空出典を許し、受取側は拒否していた。入力の要求文にも参照IDがない。P14/P16の不適合に影響しており、旧結果を保存して修正・再校正する。[監査と修正理由](docs/memory_contract_correction_20261021.md)。 |
| 確認済み：修復比較の前提 | 新しい模擬環境から操作直前まで再生し、34 API観測と52 DBファイルが一致。全プロセスや任意の未来動作の同一性を保証するものではない。 |
| 未確定：研究の差 | 状態付き記憶、拒否記録、用途別可視性、修復は既出。P16で追加価値は確認できず、次の主張を検討中。 |
| 準備中：原稿 | あらまし・本文の骨格と原典照合した書誌を保存。日本語PDFの描画は確認済み。結果の確定、著者情報、公式IEICEクラスによる４ページ確認は未完了。 |

進捗は [Project](https://github.com/users/sophiria1225/projects/1)、[新規性 #70](https://github.com/sophiria1225/AI-/issues/70)、[実験 #71](https://github.com/sophiria1225/AI-/issues/71)、[原稿 #72](https://github.com/sophiria1225/AI-/issues/72)へ同期します。
P16の[自動進捗コメント](https://github.com/sophiria1225/AI-/issues/71#issuecomment-6308459958)に完了数と費用を記録しています。

## 今回の判断と次の作業

**拒否要求の用途別表示を、今月のレターの主提案として進める案は見送りました。** 元入力で対象の誤りが確認できず、修復実験へ進める前提を満たさなかったためです。形式不適合は誤り０の成功出力には数えていません。[採否の全記録](docs/P16_findings.md)。

次は、実際に起きた記憶生成の失敗を監査し、基準実装の不整合を修正します。空出典を許すツール定義と拒否する受取側が食い違っていたため、この影響を除いて比較し直す必要があります。**この修正を新規性とは呼びません。** 近接研究との差と有効性が確認できる主張は、まだ確定していません。

[内容判定前の採否基準](docs/letter_candidate_gate_20261021.md)、[近接研究](docs/letter_related_work_addendum_20261021.md)、[実装レベルの重複](docs/letter_implementation_overlap_20261021.md)、[次の校正理由](docs/memory_contract_correction_20261021.md)。

## 最新資料と結果

**P16終了時の資料・７枚：** [PDF](materials/20261021_p16/AI_harness_P16_20261021.pdf)／[編集用PowerPoint](materials/20261021_p16/AI_harness_P16_20261021.pptx)。

**P16の結果：** [全結果と採否理由](docs/P16_findings.md)／[構成図・結果グラフ・CSV](materials/20261021_p16/figures/)。24呼出、471,666トークン、不明費用０。

**P14終了時の資料・11枚：** [PDF](materials/20261021_p14/AI_harness_P11_P14_20261021.pdf)／[編集用PowerPoint](materials/20261021_p14/AI_harness_P11_P14_20261021.pptx)／[図・CSV・出典](materials/20261021_p14/)。目的、構成図、４条件の全結果、既存研究との重複、投稿計画をまとめています。P16の意味判定結果はまだ含みません。

| 読みたいもの | 場所 |
|---|---|
| 通常台帳の結果と費用 | [P14の全結果](docs/P14_findings.md) |
| 直近履歴・保持方式の結果 | [P12](docs/P12_findings.md)、[P13](docs/P13_findings.md) |
| 作業の状態と優先順位 | [作業ボード](docs/task_board.md) |
| 原稿の準備 | [原稿フォルダー](papers/202610_letter/)、[組版の確認範囲](docs/letter_typesetting_20261021.md) |
| 判断理由・採らなかった案・失敗 | [意思決定記録](docs/decision_log.md) |
| 研究方針を選び直した経緯 | [技術的中核の再検討](docs/technical_core_review_20261021.md) |
| モデル選定と実機条件 | [モデル選定](docs/model_selection.md)、[環境手順](docs/repository_setup.md) |
| 過去の実験・資料への一覧 | [整理前のREADMEを保存した履歴](docs/archive/README_before_P16_review_20261021.md) |
| 公開できる集計と検証記録 | [reports](reports/) |

大規模文書のP15は月末投稿への集中のため保留中です。100,195文書の導入結果と準備コードは保存しています。
2027年12月までの研究全体では、情報保持・共有・実行制御を含むハーネス内部の構成原理を対象とします。今月のレターは、実証できる一つの問題へ絞ります。

## 実装と記録の扱い

`scripts/`に実行・計測・評価、`configs/`に固定条件、`tracking/tasks.json`にIssue・Projectの作業定義を置きます。段階ごとにブランチとPRを作り、CIと記録確認を経て反映します。

モデル重み、元データ、模擬資格情報、完全な履歴、独立評価の追加情報はGitへ入れません。原記録は実験機の`records/`、独立評価は`private_eval/`へ分離します。
実験機はM3 Ultra・メモリ256GiB。論理的な担当が増えてもモデル重みを複製せず、一つのモデルを順番に利用します。

GitHubの変更先は **sophiria1225/AI-だけ**です。専用Projectには当リポジトリのIssueだけを登録します。[作業ルール](AGENTS.md)を守ります。

```bash
# 進捗文書の生成（外部への書き込みなし）
python3 scripts/sync_tracking.py
# 許可されたIssueとProjectへ同期
python3 scripts/sync_tracking.py --publish
# 共通の検査
python3 -m unittest discover -s tests -v
```

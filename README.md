# AIハーネス研究

**10月31日までに、電子情報通信学会へ２段組・４ページのレターを投稿する準備を進めています。** 主要実験とあらましは10月23日、追加確認は25日、原稿は29〜30日が目標です。推薦分野は和文論文誌D、人工知能・D140803「知識の共有・再利用」。採録時期の約束ではありません。[４ページへの変更と最新の構成](docs/letter_four_page_update_20261021.md)／[当初の日程と公式規定](docs/letter_october2026_plan.md)。

## 今どこまで分かったか

**独自方式の新規性・有効性は、まだ確認できていません。** 既存の記憶保持方式の導入・校正と、新しい研究上の貢献を区別しています。

| 状態 | 確認できたこと／残っていること |
|---|---|
| 完了：基準比較 P11〜P14 | 全履歴4/4、直近履歴3/4、FOCUSに基づく保持2/4、通常台帳2/4。今回の４開発課題では品質を保つ総費用削減は未達。原論文の完全再現や一般的な優劣とは扱わない。 |
| 完了：P16・候補を見送り | 24生成、形式適合17出力・160項目を照合。元入力でも未支持の操作完了を確認できず、要求退避の追加価値は示せなかった。[全結果](docs/P16_findings.md)。 |
| 完了：P17・比較基準の校正 | 旧版7/8、整合版8/8が形式適合。適合15出力の全140項目を照合し、曖昧な全体完了が旧版１出力・整合版２出力に残った。形式修正は保持するが、意味や最終品質の改善とはしない。[全結果・採否](docs/P17_findings.md)。 |
| 完了：P18・追加の４開発課題 | 全履歴でも2/4成功。１件はAPI上限、別の１件は72曲の情報を取得済みなのにCSVが71曲で完了宣言。公開観測だけで欠落を確認した。[全結果](docs/P18_findings.md)。 |
| 完了：P20・生成上限の制約 | 全６件が4,096出力の上限に達し、CSV・コードの提出なし。80,367トークン、不明０。内容の効果は未判定。追加のP21も完了。[全結果・判断](docs/P20_findings.md)。 |
| 完了：P21・8,192上限 | 直接CSVは2/3、計算コードは1/3が完全な書出。残り３件は未提出。100,107トークン、不明０。唯一の提出コードは４補助検査に適合。コード方式の優位性は未確認。[全結果・次の判断](docs/P21_findings.md)。 |
| 確認済み：修復比較の前提 | 新しい模擬環境から操作直前まで再生し、34 API観測と52 DBファイルが一致。全プロセスや任意の未来動作の同一性を保証するものではない。 |
| 未確定：研究の差 | 状態付き記憶、拒否記録、用途別可視性、修復は既出。P16で追加価値は確認できず、次の主張を検討中。 |
| 準備中：原稿 | あらまし・本文の骨格と原典照合した書誌を保存。日本語PDFの描画は確認済み。結果の確定、著者情報、公式IEICEクラスによる４ページ確認は未完了。 |

進捗は [Project](https://github.com/users/sophiria1225/projects/1)、[新規性 #70](https://github.com/sophiria1225/AI-/issues/70)、[実験 #71](https://github.com/sophiria1225/AI-/issues/71)、[原稿 #72](https://github.com/sophiria1225/AI-/issues/72)へ同期します。
P17は16生成、317,357トークン、使用量不明０で終了しました。[自動進捗記録](https://github.com/sophiria1225/AI-/issues/71#issuecomment-6309957974)。
P18は16:55頃に開始し、17:53頃に全４件を終了しました。49生成・1,017,215トークン・187 API、使用量不明０。[P18の自動進捗](https://github.com/sophiria1225/AI-/issues/86#issuecomment-6310367235)と[終了後の全結果・診断](docs/P18_findings.md)。選定を変えず、成功した課題も含めて記録しています。

18:25頃に開始したP20は[Issue #95](https://github.com/sophiria1225/AI-/issues/95)で追跡します。一般のPythonやCodeActと等価な実装ではなく、取得済みデータからの書出だけを切り分ける診断です。全６件が終了し、形式・予算を照合しました。[生成数と費用の自動進捗](https://github.com/sophiria1225/AI-/issues/95#issuecomment-6312597539)。

P21は19:58 JSTに全６生成を終了し、主評価・補助検査・費用監査を完了しました。[Issue #99の全進捗](https://github.com/sophiria1225/AI-/issues/99#issuecomment-6313411295)／[結果と採否](docs/P21_findings.md)。

## 今回の判断と次の作業

**同じ１件の上限拡張・指示調整を続けず、予約済みの別の６開発課題へ進みます。** P21では提出された３成果物が全て正しく、コード方式の追加価値は示せませんでした。P11・P18と同じ全履歴基準で残る失敗を観察し、必要な機構を絞ります。準備と実行条件は[Issue #102](https://github.com/sophiria1225/AI-/issues/102)へ記録します。

**拒否要求の用途別表示を、今月のレターの主提案として進める案は見送りました。** 元入力で対象の誤りが確認できず、修復実験へ進める前提を満たさなかったためです。形式不適合は誤り０の成功出力には数えていません。[採否の全記録](docs/P16_findings.md)。

実際に起きた記憶生成の失敗を監査し、基準実装の不整合を修正しました。[P17の固定比較](docs/experiments/P17_ledger_contract.md)は同じ４入力×２版×新しい２seed＝16生成を終了。形式の整合は確認できましたが、全対象を確認したという曖昧な完了と、要求側だけの引用が残りました。**この修正を新規性や意味上の安全性とは呼びません。** 全体実行への接続は準備済みですが、新たな台帳性能試験を自動開始する判断はしていません。[採否・代案を選ばなかった理由](docs/P17_findings.md)。

P21の待機中に、以前予約した６開発シナリオの[公開要求だけを確認](docs/experiments/P22_development_preparation.md)しました。P21の全結果に基づき、この６件を維持して次の実行条件を固定します。

確認用の12シナリオは要求文を未閲覧のまま保留しています。[開発との分離](docs/letter_scenario_reservation_20261021.md)と[少数評価で主張できる範囲](docs/letter_evaluation_scope_20261021.md)を記録しました。方式と評価条件を固定してから使います。

[取得後の欠落と既存研究の境界](docs/export_mechanism_review_20261021.md)も確認中です。CodeAct、VeriGuard、AgentTrailsとの重なりと、原典を読んだ範囲を記録しました。

[内容判定前の採否基準](docs/letter_candidate_gate_20261021.md)、[近接研究](docs/letter_related_work_addendum_20261021.md)、[実装レベルの重複](docs/letter_implementation_overlap_20261021.md)、[次の校正理由](docs/memory_contract_correction_20261021.md)。

既存記録の[推論費用の監査](docs/P11_P14_inference_costs.md)も追加しました。入力トークンの減少と、キャッシュを使えず再処理した入力・記憶生成の増加を分けています。異なる実行経路の集計なので、キャッシュの因果効果や新規性の証明にはしません。

## 最新資料と結果

P18補助集計の[パス別名の訂正](docs/P18_path_alias_correction_20261021.md)を保存しました。実験成否・費用・曲の欠落・説明資料の数値は変わりません。

**最新：P20・P21終了時の説明資料・６枚：** [PDF](materials/20261021_p21/AI_harness_P20_P21_20261021.pdf)／[編集用PowerPoint](materials/20261021_p21/AI_harness_P20_P21_20261021.pptx)／[全結果・採否](docs/P21_findings.md)／[図表・CSV](materials/20261021_p21/figures/)。通常計算との比較、全12生成の費用、補助検査、新規性の限界、次の作業をまとめました。投稿原稿の４ページとは別です。

**P18終了時の説明資料・６枚：** [PDF](materials/20261021_p18/AI_harness_P18_20261021.pdf)／[編集用PowerPoint](materials/20261021_p18/AI_harness_P18_20261021.pptx)／[全結果・次の判断](docs/P18_findings.md)／[図表・CSV](materials/20261021_p18/figures/)。目的、構成図、全成否・費用、取得後の欠落、次の対照をまとめました。６枚は進捗説明用で、投稿原稿の４ページとは別です。

**P17終了時の説明資料・６枚：** [PDF](materials/20261021_p17/AI_harness_P17_20261021.pdf)／[編集用PowerPoint](materials/20261021_p17/AI_harness_P17_20261021.pptx)／[全結果・採否・限界](docs/P17_findings.md)。

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

# AIハーネス研究

**12:32 JST：通常台帳P14の比較を開始しました。** [自動進捗](https://github.com/sophiria1225/AI-/issues/54#issuecomment-6307352200)。大規模文書側も固定索引の100,195件全ての原文と検索の正負対照を実機で確認し、事前規則で12問を選定しました。[導入結果と残作業](docs/browsecomp_setup_results_20261021.md)。こちらの回答生成・独立判定は未実施です。

**12:18 JST：復旧後のP13全４件が終了しました。** FOCUS適合版は2/4成功・既知467,047トークン＋使用量不明２呼び出し。全11更新で履歴削除は０回で、保持生成の費用と形式不備・時間上限を分けて記録しました。[全結果・考察・次の判断](docs/P13_findings.md)、[復旧の理由と中断支出](docs/P13_recovery.md)。

**最新資料・12枚：** [PDF](materials/20261021_p13/AI_harness_P11_P13_20261021.pdf)／[編集用PowerPoint](materials/20261021_p13/AI_harness_P11_P13_20261021.pptx)／[図・CSV・出典と検査](materials/20261021_p13/)。目的、構成、全履歴・直近履歴・FOCUSの比較、なぜ再編案を見直したか、独自性の未確定点を含めています。通常の台帳P14と大規模文書環境の導入を続けます。

大規模で相互依存する仕事を、同じモデル・品質条件のもとで、より少ない総入力・出力トークンで完了させるための研究です。現在は情報保持・再取得の既存方式を比較し、追加の内部機構が必要になる条件を検証しています。期限は2027年12月です。

**07:47 JST：P12の全4件が終了しました。** 直近履歴は3/4成功・627,363総トークン。全履歴4/4・440,355に対し今回の総費用は42.5%増え、1件が予算停止しました。[図・全結果・再取得の分析](docs/P12_findings.md)。同じ4件でFOCUSに基づく保持方式を07:49 JSTから実行中です。[P13自動進捗](https://github.com/sophiria1225/AI-/issues/51#issuecomment-6303521526)。全234検査合格。独自機構の新規性・品質維持は未確定です。

**2026年10月21日：独自の技術的中核を選び直しています。** 現案には比較設計がありますが、新しいアルゴリズムはまだ定義できていません。集約を前提に大規模実験へ進む方針を見直し、近接研究が扱う機能と実際の観測を照合しました。[再検討の記録・候補を見送る理由・次の検証](docs/technical_core_review_20261021.md)、[Issue #28](https://github.com/sophiria1225/AI-/issues/28)。

**R18の監査結果：** 12原典の確認範囲とハッシュを保存し、将来の有用性に基づく圧縮、反例による記憶修正、通信への介入、証拠付き完了判定などの重複を記録しました。凍結済みP5の74操作も再監査し、成果物の更新競合や後段表示器による追加の原文欠落は確認できませんでした。これらを失敗原因と決めつけません。[原典と確認範囲](reports/R18_literature_sources.json)、[操作メタデータの集計](reports/R18_P5_evidence_audit.json)。追加モデル呼び出し0回、監査の8検査を含む全130テスト合格。

**P6の全6試行が終了しました。** 開発2課題×3方式、114呼び出し・既知787,520トークン＋費用不明4呼び出し。第1課題の全履歴だけ成功しました。FOCUSの保持生成、台帳の誤完了、入力の再処理を分けて分析しています。[全結果・図・次の判断](docs/P6_findings.md)。品質維持・新手法の有効性は未実証です。

**P6終了時の資料（11枚）：** [PDF](materials/20261021_p6/AI_harness_P6_20261021.pdf) / [編集用PowerPoint](materials/20261021_p6/AI_harness_P6_20261021.pptx) / [数値・出典・生成／検証記録](materials/20261021_p6/)。目的、構成図、全6試行、原因候補と次の比較を示しました。

**P7の記憶生成も終了しました。** 同じ入力から9回・82,412トークンで台帳を生成し、32件の完了項目を公開操作と照合しました。原入力は3出力全て、「未実行」の追記は3出力中2に、実行証拠のない操作完了が残りました。未実行文を退避した条件は適合2出力では確認されず、1出力は形式不備。[結果・図・判定方法・限界](docs/P7_findings.md)。1状態・助手1者の探索的確認で、最終タスク成功や新規性は未検証です。

**P8も2課題とも合格で終了しました。** 16呼び出し・286,306総トークン・27 API要求、使用量不明0、記録監査エラー0。記憶を圧縮せずに、従来失敗した課題を完了できました。一方、課題1では呼び出しが減っても総トークンは増えています。[全結果・比較図・次の判断](docs/P8_findings.md)。接続の複数要素を変えた校正で、独自機構の有効性や一般的な削減率は主張しません。

**P9の8回測定も完了しました。** 同じ17,682入力トークンで、一覧の後置により再処理が15,392→1,206、入力処理は平均135.969→11.960秒。総トークンや品質の改善とは分けます。[図と監査](docs/P9_findings.md)。[P10：標準会話の全履歴2試行](https://github.com/sophiria1225/AI-/issues/42#issuecomment-6301595852)が終了しました。P10の条件は[PR #43](https://github.com/sophiria1225/AI-/pull/43)に固定済み。次の4シナリオは、本文を読む前にID順の規則で選びました。[追加課題と不採用案](docs/experiments/P11_public_task_selection.md)。接続基準を固定して同じ基盤で記憶方式を比較する準備を進めています。

**P10も2課題とも合格で終了しました。** 19呼び出し・338,251トークン・35 API要求、費用不明0・履歴と順序の監査エラー0。P8より総トークンは多く、実時間は短くなりました。[全結果・この基準を選ぶ理由](docs/P10_findings.md)。以後はこの会話形式を固定し、[選定済み4シナリオのP11](docs/experiments/P11_additional_baseline.md)へ進みます。途中のDB差分と履歴を保存する機構を加え、モデル生成なしの実環境確認と全211検査が合格しました。

**この比較で決めること：** 既存の防御的確認や単純な台帳で足りるなら、追加の独自方式は提案しません。原論文の完全再現や新手法の完成ではなく、必要な技術を絞るための導入比較です。[優先順位](docs/next_actions.md)。

**10月20日時点の説明資料（16枚）：** [PDF](materials/20261020_revised/AI_harness_research_20261020.pdf) / [編集できるPowerPoint](materials/20261020_revised/AI_harness_research_20261020.pptx) / [図表・CSV・出典](materials/20261020_revised/)。[当時のアプローチ](docs/research_contribution.md)と[四条件の比較仕様](docs/experiments/E1_intervention_contract.md)を含め、構想の履歴として保持します。現在の新規性が確定した資料ではありません。

実装済みの状態保存契約は、会話・一時領域・予算等の**宣言された**保存物を検査します。実コンテナの完全保存・復元は未実装です。研究の中核が必要とする範囲を決めてから拡張します。[検査記録](reports/E1_checkpoint_contract_controls.json)。

**進捗は[Project](https://github.com/users/sophiria1225/projects/1)と[Issues](https://github.com/sophiria1225/AI-/issues)で確認できます。** 10月20日、MiniMax M3 IQ4_XS・KV q8_0の単一／固定2担当の4試行が完了しました。15380は両方式合格、15957は両方式未解決。計105呼び出し・1,113,881トークン、記録監査エラー0でした。全件が予算停止で、品質を保った費用削減や再編の有効性はまだ実証していません。[結果と次の判断](docs/P3_findings.md)、[試行ごとの記録](docs/P3_progress.md)。

**以前の進捗資料（P4終了時点・29枚）：** [PDF](materials/20261020/AI_harness_research_20261020.pdf) / [PowerPoint](materials/20261020/AI_harness_research_20261020.pptx) / [出典・図表CSV](materials/20261020/)。過去の区切りとして保存しています。現在の研究方針は上の10月21日の再検討記録を参照してください。

**P5のモデル比較結果：** [P5の共通条件比較](docs/P5_findings.md)を10月20日20:51 JSTに独立評価まで完了しました。Ansibleの固定2担当は580,169トークン、単一は571,839トークンで、双方とも修正差分0・要求0/4合格の未解決でした。計74呼び出し・監査エラー0。[Issue #24](https://github.com/sophiria1225/AI-/issues/24)、[PR #25](https://github.com/sophiria1225/AI-/pull/25)。この結果から担当変更の有効性は示せません。追加の基準試行を成功まで続ける方針にはしません。

**最新の追加観察：** [PR #21](https://github.com/sophiria1225/AI-/pull/21)でAnsible候補を共通実行器へ接続し、単一試行`P4_PRO_01`を独立評価まで完了しました。38呼び出し・586,166トークン、調査と一時的な再現確認を行いましたが、修正パッチは0バイト。要求4テストは未達、既存21テストは合格です。記録監査エラー0。自動再編の有効性はまだ確認していません。[結果と考察](docs/P4_findings.md)、[条件と選択理由](docs/experiments/Pro_first_pilot.md)、[集計](reports/P4_pro_measurements.json)。

主課題の選定では、最初の公開12候補の調査に加え、[PR #17](https://github.com/sophiria1225/AI-/pull/17)でPro V2の別の12候補・基点コード21ファイルを点検しました。理由を残してAnsibleのYAML処理を追加環境候補に選び、[PR #19](https://github.com/sophiria1225/AI-/pull/19)で起動・正負対照を確認しました。空差分は対象4件不合格・既存21件合格、参照修正は25件全合格です。終了1を誤って基盤エラーにした記録も保存し、残した出力から訂正しました。[Issue #20](https://github.com/sophiria1225/AI-/issues/20)の公開ツール・検査・初回単一観察も完了しました。正式な主課題の採用は未確定です。

| 読みたいもの | 場所 |
|---|---|
| 新規性の現在地と候補の採否 | [10月21日の技術再検討](docs/technical_core_review_20261021.md) |
| 最新の作業状況と次の順序 | [作業ボード](docs/task_board.md)、[現在の状態](docs/current_status.md) |
| なぜこのモデルか、他候補を後順位にした理由 | [モデル選定](docs/model_selection.md) |
| 判断と失敗の履歴 | [意思決定記録](docs/decision_log.md) |
| 今回の実験条件 | [P2計画](docs/experiments/P2_minimax_baseline.md) |
| 単一・固定分担比較 | [P3実行記録](docs/P3_progress.md)、[P3仕様](docs/experiments/P3_fixed_partition.md)、[制御検証](reports/P3_controls.json) |
| MiniMaxの実機測定 | [検証の経過](docs/P2_progress.md)、[費用・容量の集計](reports/P2_measurements.json) |
| 研究の背景・目的 | [研究仕様](docs/research_brief.md) |
| 以前の実測結果 | [P1検証](docs/P1_verification_results.md)、[初期検証](docs/initial_verification_results.md) |
| 公開する集計・検証証跡 | [reports](reports/) |
| このMacでの再開と環境の構成 | [環境手順](docs/repository_setup.md) |

## 実装と記録

`scripts/`に実行・計測・評価・進捗同期、`configs/`に固定条件、`tracking/tasks.json`にIssueとProjectへ同期する作業定義を置きます。研究段階ごとにブランチを切り、検証結果を添えて変更を残します。

モデル重み、元データ、コンテナ、仮想環境、完全な会話履歴はローカルに保持します。`records/`は実験機上の原記録で、過去の文書にある同ディレクトリへのリンクは実験機で閲覧できます。独立評価の正解・追加テストは`private_eval/`へ分離し、生成側のコンテナには渡しません。配布元のライセンスと引用条件は、それぞれのモデル・データに従います。

GitHubの変更先は **sophiria1225/AI-だけ**です。専用ProjectにはこのリポジトリのIssueだけを登録します。[作業ルール](AGENTS.md)と同期処理の制限を共通に守り、検証結果と次の作業を更新します。

```bash
# 進捗文書を生成する（ネットワーク書き込みなし）
python3 scripts/sync_tracking.py
# AI-のIssueと専用Projectを更新する（GitHub認証が必要）
python3 scripts/sync_tracking.py --publish
# 固定版モデルを取得し、SHA-256を照合する
.venv/bin/python scripts/download_research_model.py
```

実験機はM3 Ultra・メモリ256GiBです。論理上の複数担当は一つのモデルを順番に利用し、担当数だけモデル重みを複製しません。メモリ適合、利用できる入力長、生成速度は実測値で判断します。

# AIハーネス研究

大規模で相互依存する仕事を、同じモデル・品質条件のもとで、より少ない総入力・出力トークンで完了させるための研究です。分担、情報共有、作業状態の移管、実行単位の再編を比較します。期限は2027年12月です。

**研究の中心を具体化しました：** 情報共有や共同方針だけで十分か、それでも残る負担を減らすために、関連する判断・実行を一担当へ移す必要があるかを、同じ途中状態から比べます。動的な担当変更そのものは既出であり、その追加価値・選択方法・成立条件を狙う研究です。有効性は未実証です。[アプローチと狙う新規性](docs/research_contribution.md)、[四条件の比較仕様](docs/experiments/E1_intervention_contract.md)。

**最初に読む資料（改訂16枚）：** [PDF](materials/20261020_revised/AI_harness_research_20261020.pdf) / [編集できるPowerPoint](materials/20261020_revised/AI_harness_research_20261020.pptx) / [図表・CSV・出典](materials/20261020_revised/)。問い、先行研究との重なり、提案機構、比較設計、実測の意味、反証条件を順に説明します。[Issue #26](https://github.com/sophiria1225/AI-/issues/26)。

実装は状態保存の契約検査を追加しました。一時領域・会話・予算・環境などの宣言された保存物を照合し、不一致を拒否します。12の追加検査、全122テストが合格。実コンテナの完全保存・復元と四条件のLLM実験は次段階で、手法の改善とは数えていません。[検査記録](reports/E1_checkpoint_contract_controls.json)。

**進捗は[Project](https://github.com/users/sophiria1225/projects/1)と[Issues](https://github.com/sophiria1225/AI-/issues)で確認できます。** 10月20日、MiniMax M3 IQ4_XS・KV q8_0の単一／固定2担当の4試行が完了しました。15380は両方式合格、15957は両方式未解決。計105呼び出し・1,113,881トークン、記録監査エラー0でした。全件が予算停止で、品質を保った費用削減や再編の有効性はまだ実証していません。[結果と次の判断](docs/P3_findings.md)、[試行ごとの記録](docs/P3_progress.md)。

**以前の進捗資料（P4終了時点・29枚）：** [PDF](materials/20261020/AI_harness_research_20261020.pdf) / [PowerPoint](materials/20261020/AI_harness_research_20261020.pptx) / [出典・図表CSV](materials/20261020/)。過去の区切りとして保存しています。研究の狙いと差分は上の改訂版を先に参照してください。

**最新の比較結果：** [P5の共通条件比較](docs/P5_findings.md)を20:51 JSTに独立評価まで完了しました。Ansibleの固定2担当は580,169トークン、単一は571,839トークンで、双方とも修正差分0・要求0/4合格の未解決でした。計74呼び出し・監査エラー0。[Issue #24](https://github.com/sophiria1225/AI-/issues/24)、[PR #25](https://github.com/sophiria1225/AI-/pull/25)。この結果から担当変更の有効性は示せません。次は研究の差分と、それを検証する比較・状態保存の仕様を明確にします。

**最新の追加観察：** [PR #21](https://github.com/sophiria1225/AI-/pull/21)でAnsible候補を共通実行器へ接続し、単一試行`P4_PRO_01`を独立評価まで完了しました。38呼び出し・586,166トークン、調査と一時的な再現確認を行いましたが、修正パッチは0バイト。要求4テストは未達、既存21テストは合格です。記録監査エラー0。自動再編の有効性はまだ確認していません。[結果と考察](docs/P4_findings.md)、[条件と選択理由](docs/experiments/Pro_first_pilot.md)、[集計](reports/P4_pro_measurements.json)。

主課題の選定では、最初の公開12候補の調査に加え、[PR #17](https://github.com/sophiria1225/AI-/pull/17)でPro V2の別の12候補・基点コード21ファイルを点検しました。理由を残してAnsibleのYAML処理を追加環境候補に選び、[PR #19](https://github.com/sophiria1225/AI-/pull/19)で起動・正負対照を確認しました。空差分は対象4件不合格・既存21件合格、参照修正は25件全合格です。終了1を誤って基盤エラーにした記録も保存し、残した出力から訂正しました。[Issue #20](https://github.com/sophiria1225/AI-/issues/20)の公開ツール・検査・初回単一観察も完了しました。正式な主課題の採用は未確定です。

| 読みたいもの | 場所 |
|---|---|
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

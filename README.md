# AIハーネス研究

大規模で相互依存する仕事を、同じモデル・品質条件のもとで、より少ない総入力・出力トークンで完了させるための研究です。分担、情報共有、作業状態の移管、実行単位の再編を比較します。期限は2027年12月です。

**2026年10月21日：独自の技術的中核を選び直しています。** 現案には比較設計がありますが、新しいアルゴリズムはまだ定義できていません。集約を前提に大規模実験へ進む方針を見直し、近接研究が扱う機能と実際の観測を照合しました。[再検討の記録・候補を見送る理由・次の検証](docs/technical_core_review_20261021.md)、[Issue #28](https://github.com/sophiria1225/AI-/issues/28)。

**今回の成果：** 12原典の確認範囲とハッシュを保存し、将来の有用性に基づく圧縮、反例による記憶修正、通信への介入、証拠付き完了判定などの重複を記録しました。凍結済みP5の74操作も再監査し、成果物の更新競合や後段表示器による追加の原文欠落は確認できませんでした。これらを失敗原因と決めつけません。[原典と確認範囲](reports/R18_literature_sources.json)、[操作メタデータの集計](reports/R18_P5_evidence_audit.json)。追加モデル呼び出し0回、監査の8検査を含む全130テスト合格。

**次の優先作業：** 原著者が報告した「対象全体への計画は残るが、個々の作業対象を落とす」失敗について、既存の防御的検証や単純な対象台帳で解決できる範囲を確認します。これは新手法の採用ではなく、追加技術が必要な問題を絞るための検証候補です。[優先順位](docs/next_actions.md)。

**10月20日時点の説明資料（16枚）：** [PDF](materials/20261020_revised/AI_harness_research_20261020.pdf) / [編集できるPowerPoint](materials/20261020_revised/AI_harness_research_20261020.pptx) / [図表・CSV・出典](materials/20261020_revised/)。[当時のアプローチ](docs/research_contribution.md)と[四条件の比較仕様](docs/experiments/E1_intervention_contract.md)を含め、構想の履歴として保持します。現在の新規性が確定した資料ではありません。

実装済みの状態保存契約は、会話・一時領域・予算等の**宣言された**保存物を検査します。実コンテナの完全保存・復元は未実装です。研究の中核が必要とする範囲を決めてから拡張します。[検査記録](reports/E1_checkpoint_contract_controls.json)。

**進捗は[Project](https://github.com/users/sophiria1225/projects/1)と[Issues](https://github.com/sophiria1225/AI-/issues)で確認できます。** 10月20日、MiniMax M3 IQ4_XS・KV q8_0の単一／固定2担当の4試行が完了しました。15380は両方式合格、15957は両方式未解決。計105呼び出し・1,113,881トークン、記録監査エラー0でした。全件が予算停止で、品質を保った費用削減や再編の有効性はまだ実証していません。[結果と次の判断](docs/P3_findings.md)、[試行ごとの記録](docs/P3_progress.md)。

**以前の進捗資料（P4終了時点・29枚）：** [PDF](materials/20261020/AI_harness_research_20261020.pdf) / [PowerPoint](materials/20261020/AI_harness_research_20261020.pptx) / [出典・図表CSV](materials/20261020/)。過去の区切りとして保存しています。現在の研究方針は上の10月21日の再検討記録を参照してください。

**最新のモデル比較結果：** [P5の共通条件比較](docs/P5_findings.md)を10月20日20:51 JSTに独立評価まで完了しました。Ansibleの固定2担当は580,169トークン、単一は571,839トークンで、双方とも修正差分0・要求0/4合格の未解決でした。計74呼び出し・監査エラー0。[Issue #24](https://github.com/sophiria1225/AI-/issues/24)、[PR #25](https://github.com/sophiria1225/AI-/pull/25)。この結果から担当変更の有効性は示せません。追加の基準試行を成功まで続ける方針にはしません。

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

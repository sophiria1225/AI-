# AIハーネス研究

大規模で相互依存する仕事を、同じモデル・品質条件のもとで、より少ない総入力・出力トークンで完了させるための研究です。分担、情報共有、作業状態の移管、実行単位の再編を比較します。期限は2027年12月です。

**進捗は[Project](https://github.com/users/sophiria1225/projects/1)と[Issues](https://github.com/sophiria1225/AI-/issues)で確認できます。** 10月20日、MiniMax M3 IQ4_XS・KV q8_0で、単一と固定2担当の4試行中3試行を完了しました。15380は単一283,176・固定2担当275,008トークンで両方合格。15957の固定2担当は275,531トークンで未解決でした。現在は最後の単一担当を実行しています。各1回の開発観察であり、時間・キャッシュ条件も区別します。再編方式の有効性と、品質を保った費用削減はまだ実証していません。[最新結果](docs/P3_progress.md)。

主課題の選定では、最初の公開12候補の調査に加え、[PR #17](https://github.com/sophiria1225/AI-/pull/17)でPro V2の別の12候補・基点コード21ファイルを点検しました。理由を残してAnsibleのYAML処理を最初の追加環境候補に選び、[PR #19](https://github.com/sophiria1225/AI-/pull/19)で起動・評価器の正負対照を準備しています。正式な主課題の採用は未確定です。

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

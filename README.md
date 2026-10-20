# AIハーネス研究

大規模で相互依存する仕事を、同じモデル・品質条件のもとで、より少ない総入力・出力トークンで完了させるための研究です。分担、情報共有、作業状態の移管、実行単位の再編を比較します。期限は2027年12月です。

**現在は強い単一エージェントの校正段階です。** MiniMax M3 Q3_K_Lを最初の非Flash候補として導入しています。既存の2モデル×2開発課題の結果は、いずれも1課題成功・1課題失敗でした。再編方式の有効性はまだ実証していません。

| 読みたいもの | 場所 |
|---|---|
| 最新の作業状況と次の順序 | [作業ボード](docs/task_board.md)、[現在の状態](docs/current_status.md) |
| なぜこのモデルか、他候補を後順位にした理由 | [モデル選定](docs/model_selection.md) |
| 判断と失敗の履歴 | [意思決定記録](docs/decision_log.md) |
| 今回の実験条件 | [P2計画](docs/experiments/P2_minimax_baseline.md) |
| 研究の背景・目的 | [研究仕様](docs/research_brief.md) |
| 以前の実測結果 | [P1検証](docs/P1_verification_results.md)、[初期検証](docs/initial_verification_results.md) |
| 公開する集計・検証証跡 | [reports](reports/) |
| このMacでの再開と環境の構成 | [環境手順](docs/repository_setup.md) |

## 実装と記録

`scripts/`に実行・計測・評価・進捗同期、`configs/`に固定条件、`tracking/tasks.json`にIssueとProjectへ同期する作業定義を置きます。研究段階ごとにブランチを切り、検証結果を添えて変更を残します。

モデル重み、元データ、コンテナ、仮想環境、完全な会話履歴はローカルに保持します。`records/`は実験機上の原記録で、過去の文書にある同ディレクトリへのリンクは実験機で閲覧できます。独立評価の正解・追加テストは`private_eval/`へ分離し、生成側のコンテナには渡しません。配布元のライセンスと引用条件は、それぞれのモデル・データに従います。

GitHubのIssue・Projectは認証後に同期します。未同期の作業を作成済みとして表示しません。

```bash
# 進捗文書を生成する（ネットワーク書き込みなし）
python3 scripts/sync_tracking.py
# GitHub認証後、IssueとProjectを更新する
python3 scripts/sync_tracking.py --publish
# 固定版モデルを取得し、SHA-256を照合する
.venv/bin/python scripts/download_research_model.py
```

実験機はM3 Ultra・メモリ256GiBです。論理上の複数担当は一つのモデルを順番に利用し、担当数だけモデル重みを複製しません。メモリ適合、利用できる入力長、生成速度は実測値で判断します。

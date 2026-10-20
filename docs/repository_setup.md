# リポジトリと実験環境

新しい実装・設定・実験記録の基点はこのリポジトリです。既存の研究環境から移管した時点では、容量の重複と版の変更を避けるため、仮想環境・固定ソース・データ・コンテナCLIをローカルのシンボリックリンクで再利用しています。Gitへこのリンクは登録しません。旧作業フォルダーを消す前に実体の移設が必要です。

## 既存の実験機で確認する

```bash
.venv/bin/python scripts/check_dependencies.py
.venv/bin/python -m unittest discover -s tests -v
sh scripts/with_container_env.sh .tools/bin/colima start --profile harness-e0
sh scripts/with_container_env.sh .venv/bin/python scripts/check_visible_controls.py
```

依存ソースのコミットとデータの版は`configs/dependencies.json`、Python環境は`requirements.lock.txt`に保存しています。正解を含む原本は`private_eval/`、生成用の公開入力は`data/verified_public_inputs.jsonl`です。後者は公開課題の許可した列だけを取り出しています。

新しいチェックアウトでは、Python 3.12系の仮想環境、固定版の3リポジトリ、固定版データ、コンテナ環境が必要です。現在のシンボリックリンクに対して仮想環境を作り直すコマンドは実行しないでください。`install_local_container_tools.py`は以前取得した配布メタデータを使う初回導入用のスクリプトで、Gitからの単独cloneだけでは完結しません。完全な新規環境の自動構築は今後の作業です。

## MiniMax M3を起動する

```bash
.venv/bin/python scripts/install_llama_runtime.py
.venv/bin/python scripts/download_research_model.py
.venv/bin/python scripts/serve_research_model.py --ctx-size 8192
```

実行基盤と重みのハッシュを検証してからロードします。サーバーは127.0.0.1:8011、同時処理1枠で起動します。公開サービスや外部APIには接続しません。監視ログにreadyが出た後、別のターミナルから接続試験を実行できます。

```bash
.venv/bin/python scripts/probe_llama.py --mode enabled
.venv/bin/python scripts/probe_context_capacity.py --target-tokens 6000
```

長い入力の試験は、異なる架空レコードを使った容量確認です。大規模実問題の研究成果には数えません。実コード課題は設定を固定して`run_mini_pilot.py`で実行し、終了後の凍結成果物だけを`evaluate_frozen_run.py --run records/p2/実行ID`へ渡します。

## GitHubで進捗を公開する

`tracking/tasks.json`がIssueとProjectの更新元です。`sync_tracking.py`は既存Issueを固定IDで照合し、重複作成を避けます。人の補足コメントを削除しません。既存Projectの項目や他のIssueには触れません。

GitHub CLIのログインは利用者がブラウザーで行います。ログイン後に作業ブランチをpushし、`python3 scripts/sync_tracking.py --publish`を実行します。認証情報はリポジトリに保存しません。

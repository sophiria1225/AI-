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

## 新しいチェックアウトで準備する

Python 3.12.13を前提とします。以下は新しいチェックアウト用です。既存の実験機では先の確認手順を使い、シンボリックリンクの仮想環境を作り直さないでください。

```bash
python3.12 scripts/bootstrap_repositories.py
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python scripts/install_local_container_tools.py
.venv/bin/python scripts/prepare_fixed_data.py
sh scripts/with_container_env.sh .tools/bin/colima start --profile harness-e0 --cpus 4 --memory 8 --disk 40 --arch aarch64 --vm-type vz --mount none --binfmt --activate=false --ssh-config=false
sh scripts/with_container_env.sh .venv/bin/python scripts/prepare_fixed_data.py --pull-images
.venv/bin/python scripts/check_dependencies.py
```

依存ソースはコミットを指定して取得し、既存の異なる作業ツリーをresetしません。コンテナ用CLIは`configs/container_tools.json`で配布URL・サイズ・ハッシュを固定し、新しいディレクトリへ導入します。Docker CLIのハッシュは初回取得物の内容固定で、配布元チェックサムとの照合とは区別しています。既存ツールの上書きは拒否します。

データ準備は500件の公開入力を許可した7列へ限定し、2開発課題の正解・評価スクリプトは`private_eval/`へ保存します。参照するtask-repoの版と、パッチ・検査ラベルの対応を機械照合します。`--pull-images`を付けた場合だけ、2件の固定ダイジェストのイメージを取得します。

別の空ディレクトリへの依存ソース1件の取得、4 CLIの照合・展開・版表示、全公開入力と2評価ファイルの再構成を実機で確認しました。既存データとの構造的一致も確認しています。この検証は新しいVMとPython環境を含む全工程の再実行ではありません。VMのOS・エンジン版も新しい実験機で記録してください。

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

同期はIssueを先に保存してからProjectへ登録します。Projectの権限だけが不足した場合も、作成済みIssueのリンクを保持して再開できます。`--publish --issues-only`はIssueだけを同期します。同じ固定IDが複数Issueに見つかった場合は停止します。Project権限失敗後の再試行で重複しない対照検査を実装済みですが、2026年10月20日時点では未認証のため実際のリモート同期は未検証です。

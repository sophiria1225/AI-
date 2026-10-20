# 初回検証を再確認する手順

この作業フォルダでは、インストール済みの研究専用Python・コンテナCLIを使う。参照データやモデルの再取得は不要。コマンドはプロジェクトのルートで実行する。

```sh
cd /Users/tp26013/harness_research
sh scripts/with_container_env.sh .tools/bin/colima start --profile harness-e0
sh scripts/with_container_env.sh docker info
.venv/bin/python scripts/audit_records.py
```

監査は保存済みの使用量とハッシュだけを再計算し、モデルや最終評価を呼ばない。VM停止中でもこの監査はできる。

## 使用した版

- Python 3.12.13。依存一覧は`records/environment/python_requirements_locked.txt`。
- SWE-benchのコミット`02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`。
- swe-bench-tasksのコミット`3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`。
- データ、モデル、課題イメージは各設定のリビジョン・ダイジェストに固定。
- CLIの由来とダウンロード検証は`records/environment/local_container_tools.json`。

## 新たに実行する場合

実行は新規試行となり費用が発生する。単なる閲覧・監査とは別に扱う。2026年10月13日のP1で現在の`run_e0_pilot.py`を修正したため、旧設定v0.3を現在のスクリプトへ渡しても当時の条件の再現にはならない。旧実行器は各E0記録内の`runner_snapshot.py`、旧コンテナ設定は`container_policy_snapshot.py`に保存している。当時のルートディレクトリの解決と依存を復元してから使用すること。

以下は旧設定を新しい共通実行処理へ適用する**新規の開発試行**の例であり、旧結果と同じ集計にはしない。

```sh
sh scripts/with_container_env.sh .venv/bin/python scripts/run_e0_pilot.py --strategy single --config configs/E0_pilot_v03.json
sh scripts/with_container_env.sh .venv/bin/python scripts/run_e0_pilot.py --strategy fixed_pair --config configs/E0_pilot_v03.json
```

生成中は`private_eval/`や`logs/`をコンテナへマウントしない。最終評価用のスクリプトは、生成が終わり最終パッチを凍結した後にのみ使う。初回の最終評価スクリプトは保存済み試行を列挙するため、無条件に繰り返すと不要な再評価になる。追加実験へ拡張する前に、対象実行IDを指定できるようにする。

```sh
sh scripts/with_container_env.sh .venv/bin/python scripts/evaluate_candidates.py
sh scripts/with_container_env.sh .tools/bin/colima stop --profile harness-e0
```

公式評価器の既定コンテナ生成を、ネットワーク無効・マウント無し等の共通設定へ置き換えている。公式のすべての既定条件を再現したスコアとは表記しない。モデルの推論も含め、乱数設定だけで完全な同一出力になるとは保証しない。

## P1の記録を確認する場合

```sh
.venv/bin/python scripts/audit_p1.py
```

これも保存済みの記録だけの監査で、モデルを呼ばない。P1の実行仕様は[校正の計画](experiments/P1_baseline_calibration.md)、上流との差は[接続仕様](mini_baseline_adapter.md)にまとめた。依存一覧は`records/environment/P1_python_requirements_locked.txt`。

新規のP1試行を行うコマンドは以下。最大30呼び出し・総300,000トークンを使い得るため、既に済んだ4試行の閲覧のために実行する必要はない。

```sh
sh scripts/with_container_env.sh .tools/bin/colima start --profile harness-e0
sh scripts/with_container_env.sh .venv/bin/python scripts/run_mini_pilot.py --config configs/P1_small_15380.json
```

`evaluate_p1.py`は生成をすべて終え、成果物を凍結した後の独立評価用。評価済みの試行を上書きしない。今回の4試行を超えて追加した場合は、評価対象の選択を明示的に拡張する必要がある。秘密の評価結果をモデルへ返す再修正には使わない。

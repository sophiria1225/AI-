# アカウント変更後の研究引き継ぎ

**2026年10月22日14:27 JST、ユーザーの指示で一時停止。新しい実験を自動で始めない。** モデルサーバーは正常終了し、データ・重み・原記録は保存してある。最新のユーザーが再開を指示した場合に、この文書から引き継ぐ。

## 同じMacで開くフォルダ

```text
/Users/tp26013/AI-/.runtime/worktrees/p21-prep
```

ここが編集用の作業木。データ・モデル・仮想環境の保存先は `/Users/tp26013/AI-`。新しくcloneしたコードだけでは、Git管理外の実験記録やモデルは復元されない。フォルダを消さない。

## 新しい会話に貼る文

```text
/Users/tp26013/AI-/.runtime/worktrees/p21-prep/RESUME.md と
docs/handoff_20261022_account_switch.md、AGENTS.md を読んで研究を引き継いで。
まず現在のブランチ、GitHubの公開状態、停止状態を確認して、次にすることを短く説明して。
GitHubで変更してよいのは sophiria1225/AI- とその専用Projectだけ。
過去の実験を上書きせず、新規性・性能維持がまだ未確立であることを引き継いで。
```

その後、実験も再開したい場合は「確認できたら実装・実験を再開して」と伝える。

## 最初に読むもの

1. [詳しい引き継ぎ](docs/handoff_20261022_account_switch.md)：目的、期限、実装、結果、未完了、再開手順。
2. [現在の状態](docs/current_status.md)／[ユーザーと確認した研究目的](docs/research_objective_20261022.md)。
3. [最新P42の結果](docs/P42_findings.md)／[判断理由の記録](docs/decision_log.md)。
4. [GitHub Project](https://github.com/users/sophiria1225/projects/1)／[最新の資料PDF](materials/20261022_p40/AI_harness_budget_20261022.pdf)。

`/init`で新しい方針を作り直す必要はない。既存のAGENTS.mdとこの引き継ぎを読むことを優先する。アカウントをまたいだ同一会話の自動移行は確認できていないため、それを前提にしない。

# アカウント変更後の研究引き継ぎ

**2026年10月22日、アカウント変更後のユーザー指示で再開済み。** 停止するまで実装を継続する指示を受け、P45の全予定条件の終了監査とP46の全保存記録照合を完了し、P47の３条件比較を準備している。[再開の根拠と次の計測](docs/resumption_20261022.md)／[現在の状態](docs/current_status.md)。14:27 JSTの停止記録、モデル・データ・原記録は保存した。以下の会話例は停止時に準備した引き継ぎ手順で、再度の許可を求める意味ではない。

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
3. [最新P45の結果](docs/P45_findings.md)／[判断理由の記録](docs/decision_log.md)。
4. [GitHub Project](https://github.com/users/sophiria1225/projects/1)／[最新の資料PDF](materials/20261022_p45/AI_harness_documentation_cost_20261022.pdf)。

`/init`で新しい方針を作り直す必要はない。既存のAGENTS.mdとこの引き継ぎを読むことを優先する。アカウントをまたいだ同一会話の自動移行は確認できていないため、それを前提にしない。

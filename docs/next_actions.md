# 次の作業

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P118の通常要約対全保持、既知４課題×２方式の８条件を開始した。同じ完全headの両workflow・両job成功、８初回入力の課題内一致、空tool要約経路１入力の計数を確認済み。要約も共有する80呼出し・450,000 token・1,800仕事秒の各上限で計上する。全条件と所有serverが閉じてから成否と総費用を読む。途中の成否で方式を変更しない。SJCの要約出典判定、TypeCompactの型別保持、SelfCompactの適応判断も既存方式として照合した。P111〜P117と未知使用量２、P111採用基準未達を保持。原稿と未見12課題は保留、新規性と一般的品質維持は未確立。 [固定計画](experiments/P118_whole_task_single_checkpoint.md)。
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

ユーザーは停止を指示するまで実行継続を希望している. 原稿の逐次更新は保留し、実験を優先する. 最終目標、期限、実行木、保存印は[RESUME](../RESUME.md)を参照する. [整理前の計画と経緯](https://github.com/sophiria1225/AI-/blob/20c14641da3bcf34fb827ef85735e2197311d5ce/docs/next_actions.md)を現在の待機指示として再実行しない.

1. P111〜P117の全結果、未知使用量２、採用基準未達を保持する. 終了済み処理を再実行しない.
2. P118の固定８条件の実行を継続する. 同一headの両workflow・両job成功、８初回入力と要約経路の事前確認は完了. 計画や固定実行木を途中変更せず、起動を重ねない.
3. 中間の成否や要約本文を読まず、運用状態だけを確認する. `.runtime/P118_closure_once_end.json`でpipeline・監査・session・全件資料の終了を確認してから一度だけ回収する. 処理が止まった場合は開始印と失敗記録を保ち、自動再試行しない. ユーザー停止を優先する.
4. 全８枠とserverが閉じてから成否を読む. 実行役と要約役の全要求、未知・失敗・未実行・未評価、共有予算、入力投影を照合し、session費用と全件資料を作る. 停止指示があれば直ちに従う.
5. 通常要約の効果を新提案の新規性や一般的品質維持へ読み替えない. PAIR、P14、P111〜P117との範囲差を保持する. 原稿と未見12課題は保留、Projectとmaterialsはまとまった結果ごとに更新する. 教授への送信や投稿は行わない.

閉じた実験と監査を再実行しない. 各作業は同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功を確認してから進める. `.runtime/research_ledger_names.json`の全台帳と固定計画の指紋を保持する. 変更先は自分の研究リポジトリと専用Projectのみ.

# 次の作業

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P114の通常対照を固定。今の持続Python・auto構成で、直前や失敗時を含む過去の内部推論を次回入力へ渡さない４既知課題を準備した。公開情報・Python状態・完全保存履歴と生成予算は共通。全1,828検査成功、生成未開始。初回要求と計数をP111の３方式すべてと照合する。P111全12条件は過去参照として保持し、同時対照・独立確認とは呼ばない。P111採用基準未達と使用量不明２は変更せず、未見12課題未閲覧・原稿保留。 [固定計画](experiments/P114_whole_task_public_only_history.md)。
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

ユーザーは停止を指示するまで実行継続を希望している. 原稿の逐次更新は保留し、実験を優先する. 最終目標、期限、実行木、保存印は[RESUME](../RESUME.md)を参照する. [整理前の計画と経緯](https://github.com/sophiria1225/AI-/blob/20c14641da3bcf34fb827ef85735e2197311d5ce/docs/next_actions.md)を現在の待機指示として再実行しない.

1. [P111](P111_findings.md)、[P112](P112_findings.md)、[P113](P113_findings.md)の閉鎖と全結果を保持する. 使用量不明２とP111採用基準未達を変更しない.
2. [P114の固定計画](experiments/P114_whole_task_public_only_history.md)の同じ完全headでpush・pull_request両workflowと両jobの成功を確認する. 全1,828検査はローカルで成功、生成は未開始.
3. 固定実行木から所有serverを起動し、初回４要求をP111の全３方式の初回完全要求・計数・通知・モデル設定と照合する. 合格後、４既知課題を固定順に各１回だけ実行する.
4. 全条件、全試行、不明、未達、未実行、未評価を保持し、所有server閉鎖・全記録監査・時間と資源費用の点検後に資料を作る. P111全12条件は過去参照として別出典・別費用にする.
5. 通常対照の校正を新手法や独立確認と呼ばない. 原稿保留と未見12課題の分離を維持し、Projectとmaterialsは結果がまとまってから更新する.

閉じた実験と監査を再実行しない. 各作業は同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功を確認してから進める. `.runtime/research_ledger_names.json`の全台帳と固定計画の指紋を保持する. 変更先は自分の研究リポジトリと専用Projectのみ.

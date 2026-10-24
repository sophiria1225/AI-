# 次の作業

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P114を固定headから開始。初回４要求はP111の各３方式と完全要求・native入力数・予算・モデル設定がすべて一致。既知４課題の通常public_only対照を固定順で実行中。全４条件と所有server閉鎖後に結果を比較する。P111全12条件は過去参照、採用基準未達と不明使用量２を保持。全1,828検査・両workflow・両job成功済み。原稿保留、未見12課題未閲覧、実結果の図は未生成。 [開始記録](../materials/20261025_p114_running/README.md)。
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

ユーザーは停止を指示するまで実行継続を希望している. 原稿の逐次更新は保留し、実験を優先する. 最終目標、期限、実行木、保存印は[RESUME](../RESUME.md)を参照する. [整理前の計画と経緯](https://github.com/sophiria1225/AI-/blob/20c14641da3bcf34fb827ef85735e2197311d5ce/docs/next_actions.md)を現在の待機指示として再実行しない.

1. [P111](P111_findings.md)、[P112](P112_findings.md)、[P113](P113_findings.md)の閉鎖と全結果を保持する. 使用量不明２とP111採用基準未達を変更しない.
2. P114の固定４条件の実行を継続する. 初回要求の照合、両workflow・両job成功は確認済み. 計画や実行木を途中変更せず、起動を重ねない.
3. `.runtime/P114_closure_once_end.json`でpipeline、監査、server費用点検、全件reportの一度だけの完了を確認する. 実行中は中間の成否・比較結果を読まず、運用状態だけを確認する. ユーザーの停止指示には直ちに従う.
4. 全条件、全試行、不明、未達、未実行、未評価を保持し、所有server閉鎖・全記録監査・時間と資源費用の点検後に資料を作る. P111全12条件は過去参照として別出典・別費用にする.
5. 通常対照の校正を新手法や独立確認と呼ばない. 原稿保留と未見12課題の分離を維持し、Projectとmaterialsは結果がまとまってから更新する.

閉じた実験と監査を再実行しない. 各作業は同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功を確認してから進める. `.runtime/research_ledger_names.json`の全台帳と固定計画の指紋を保持する. 変更先は自分の研究リポジトリと専用Projectのみ.

# 次の作業

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P114は既知４課題の通常public_only対照を実行中。全件成否を読む前にP115の入力差診断を準備した。全４条件の全保存要求を４表示で計数し、表示の省略量と過去P111を参照した全仕事の費用差を区別する。11追加検査を含む全1,839検査成功。P114の途中成否は未閲覧。閉鎖・監査・全記録の指紋固定・計画の両CI成功後にのみ計数する。新規生成、API、評価０。新規性と一般的品質維持は未確立。原稿保留、未見12課題未閲覧を維持。 [診断の準備](../materials/20261025_p115_preparation/README.md)。
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

ユーザーは停止を指示するまで実行継続を希望している. 原稿の逐次更新は保留し、実験を優先する. 最終目標、期限、実行木、保存印は[RESUME](../RESUME.md)を参照する. [整理前の計画と経緯](https://github.com/sophiria1225/AI-/blob/20c14641da3bcf34fb827ef85735e2197311d5ce/docs/next_actions.md)を現在の待機指示として再実行しない.

1. [P111](P111_findings.md)、[P112](P112_findings.md)、[P113](P113_findings.md)の閉鎖と全結果を保持する. 使用量不明２とP111採用基準未達を変更しない.
2. P114の固定４条件の実行を継続する. 初回要求の照合、両workflow・両job成功は確認済み. 計画や実行木を途中変更せず、起動を重ねない.
3. `.runtime/P114_closure_once_end.json`でpipeline、監査、server費用点検、全件reportの一度だけの完了を確認する. 実行中は中間の成否・比較結果を読まず、運用状態だけを確認する. ユーザーの停止指示には直ちに従う.
4. 全条件、全試行、不明、未達、未実行、未評価を保持し、所有server閉鎖・全記録監査・時間と資源費用の点検後に資料を作る. P111全12条件は過去参照として別出典・別費用にする.
5. 通常対照の校正を新手法や独立確認と呼ばない. 原稿保留と未見12課題の分離を維持し、Projectとmaterialsは結果がまとまってから更新する.

閉じた実験と監査を再実行しない. 各作業は同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功を確認してから進める. `.runtime/research_ledger_names.json`の全台帳と固定計画の指紋を保持する. 変更先は自分の研究リポジトリと専用Projectのみ.

# 次の作業

<!-- CURRENT_EVIDENCE_SNAPSHOT -->
P118の通常対照比較を固定。既知４課題で全保持と１回要約を各１回、計８条件を準備した。16,384 native token以上の最初の機会に古い完結ターンを要約し、元指示と直近２ターン、Python状態、完全保存履歴を保持する。要約と実行役は80呼出し・450,000 token・1,800仕事秒の同じ枠を使い、不正・打切り・不採用要約の費用も含める。全1,880テスト成功、444ソース固定、生成未開始。現構成での通常要約の比較であり、新提案やPAIR再現ではない。P111〜P117と未知使用量２、P111採用基準未達を保持。原稿保留、未見12課題未閲覧、新規性と一般的品質維持は未確立。 [固定計画](experiments/P118_whole_task_single_checkpoint.md)。
<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->

ユーザーは停止を指示するまで実行継続を希望している. 原稿の逐次更新は保留し、実験を優先する. 最終目標、期限、実行木、保存印は[RESUME](../RESUME.md)を参照する. [整理前の計画と経緯](https://github.com/sophiria1225/AI-/blob/20c14641da3bcf34fb827ef85735e2197311d5ce/docs/next_actions.md)を現在の待機指示として再実行しない.

1. P111〜P117の全結果、未知使用量２、採用基準未達を保持する. 終了済み処理を再実行しない.
2. [P118の固定計画](experiments/P118_whole_task_single_checkpoint.md)の同じ完全headでpush・pull_request両workflowと両accounting-and-syntax job成功を確認する. 全1,880テストは成功、444ソースを固定、モデル生成は未開始.
3. 新しい固定実行木から所有serverを起動し、８初回入力の課題内同一性と空tool要約経路１入力を計数する. 合格後、既知４課題×全保持・１回要約の８条件を固定順で各１回実行する. 要約も同じ呼出し・token・時間の予算内に含める.
4. 全８枠とserverが閉じてから成否を読む. 実行役と要約役の全要求、未知・失敗・未実行・未評価、共有予算、入力投影を照合し、session費用と全件資料を作る. 停止指示があれば直ちに従う.
5. 通常要約の効果を新提案の新規性や一般的品質維持へ読み替えない. PAIR、P14、P111〜P117との範囲差を保持する. 原稿と未見12課題は保留、Projectとmaterialsはまとまった結果ごとに更新する. 教授への送信や投稿は行わない.

閉じた実験と監査を再実行しない. 各作業は同じ完全headのpush・pull_request両workflowと両accounting-and-syntax job成功を確認してから進める. `.runtime/research_ledger_names.json`の全台帳と固定計画の指紋を保持する. 変更先は自分の研究リポジトリと専用Projectのみ.

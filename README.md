# AIハーネス研究

必要な情報と最終成果の品質を保ち、要約・制御・失敗・再取得を含む仕事全体のlogical入力＋出力トークンを減らすハーネス制御を研究する。

## 現在の状態：2026年10月26日

P123は全12条件を終了し、3方式とも既知4課題で4/4成功、使用量不明0、監査エラー0。総logical入力＋出力tokenは単発893,529、別呼出し反復785,656、同時反復836,922。別呼出し反復は単発より12.07%少ない。同時反復は別呼出し反復より6.53%多いため、事前の採用判定はfalseを保持する。

[P123全結果](docs/P123_findings.md)／[全12条件の資料](materials/20261025_p123_results/README.md)／[参考図](materials/20261026_p123_figures/README.md)／[独立再計算](docs/P123_independent_audit.md)。

P124の固定応答再生は全20programの出力・方式間境界が一致し、通常完全cache68対提案57の保存backend応答だった。これは実API/model0の局所検証で、全仕事の品質・tokenの実測ではない（[P124所見](docs/P124_findings.md)）。

次はP125の既知4課題×2方式・seed157で、自動field projectionの追加効果を全仕事で測る。[準備PR517](https://github.com/sophiria1225/AI-/pull/517)。P125の有限計画を1,125 source filesとP123/P124閉鎖証拠へ固定済み。既知4課題×2方式・seed157、各80 model呼出/450,000 tokens/1,800作業秒、全体8評価・800 API・server6時間。最終headのpush/PR両CI後に一度開始する。モデルはまだ未開始。単発checkpointを共通にした事前比較であり、今回最小だった別反復を上回ったと解釈しない。

## 目的と継続方針

新規機構による精度維持と全仕事token削減、一般化、新規性はまだ未確立。P123は既知4課題・1seedの通常方式比較で、非劣性の証明や新規手法の成立とはしない。[最終目標までの方針](docs/research_execution_route_20261026.md)／[P0–P123履歴レビュー](docs/research_history_review_20261026.md)。

ユーザーは約24時間（10/27 06時頃まで）で主要実験をまとめる方針を指定した。原稿はユーザーが執筆し、こちらは実験と全件結果・再現根拠の整理を担当する。普通のメッセージには応答しながら実験を継続し、停止指示に従う。バッチ完了後も次の有限な判断へ進む。

[現在の状態](docs/current_status.md)／[再開手順](RESUME.md)／[次の作業](docs/next_actions.md)／[作業ボード](docs/task_board.md)／[専用Project](https://github.com/users/sophiria1225/projects/1)。

## 保存と作業範囲

変更先は `sophiria1225/AI-` と専用Projectのみ。全旧試行、失敗、不明費用、固定source、[旧原稿](papers/202610_letter/checkpoint_cost_v01/README.md)を保持する。P122のCSV成功損失・不明1要求も保存。未見12課題は確認計画を固定するまで開かない。生のprompt、推論、生成task code、課題値、認証情報は公開しない。[AGENTS](AGENTS.md)。

10月31日までのレター投稿が目標。採択は保証しない。過去の運用状態は履歴資料・各commitへ残し、現在の開始/停止状態に再適用しない。

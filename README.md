# AIハーネス研究

必要な情報と最終成果の品質を保ち、要約・制御・失敗・再取得を含む仕事全体のlogical入力＋出力トークンを減らすハーネス制御を研究する。

## 現在の状態：2026年10月26日、P127全8条件閉鎖

P127は2026-10-26 13:08 JSTに全8条件・所有server・collector・後処理を閉鎖した。両方式とも3/4成功、全仕事logical入力＋出力695,217 token、共通成功352,584 tokenで差0。全132 programで静的受理・変換・automatic partial hit・明示field要求は0、CSVの通常完全cache hitは各72。使用量不明0、契約停止0、監査エラー0、固定gateはfalse。CSVは両方式とも117 APIで完了宣言したが独立評価は失敗した。

[全件所見](docs/experiments/P127_findings.md)／[全8条件資料](materials/20261026_p127_results/README.md)／[実図](materials/20261026_p127_results/figures/README.md)／[会計注記](materials/20261026_p127_results/INTERPRETATION.md)。

全条件合計1,390,434 token・136 model呼出し・490実API・8独立評価を保存した。閉鎖後独立監査は67,270 checksでPASS。実行head `0219f774326e7e4e2fdacc6aaaf0c45ea381cfc0` と1,142 sourcesを固定したまま、元wrapper・collector・監査・描画を再起動しない。後処理v01の待機制御修正来歴も保持し、model再実験と混同しない。

[全132 sourceのAST診断](docs/experiments/P127_admission_diagnosis.md)も終了した。対象取得は完全応答を永続dictへ保存するため拒否され、構文を緩めるだけで安全に取得を省ける根拠はなかった。追加seedや同条件反復を自動開始しない。限定した機構差と強い通常対照に対する効果経路が見つかった場合だけ、別の有限比較を固定する。新規機構によるtoken削減、一般的品質維持、新規性は未確立。

## 以前の結果との区別

- [P126](docs/experiments/P126_findings.md)は保存prefix再生48件が一致、13取得省略×2記録、control bytes増加。実model/API/評価0で、online品質・token効果ではない。
- [P125](docs/P125_findings.md)は両3/4成功・各766,875 token、全146 programで機構未発動。CSVはAPI80で失敗しgate false。
- [P123](docs/P123_findings.md)は3方式各4/4成功。単発893,529、別反復785,656、同時反復836,922 token。強い通常対照である別反復より同時反復は多く、固定gate false。
- [P124](docs/P124_findings.md)は保存再生20 program一致、通常cache68対提案57。実API/model0の局所検証。

seed・checkpoint・guide・cache・API上限が異なる旧phaseを一因子比較や同じ反復として混ぜない。P122の成功損失・不明1要求を含む全旧試行を保持する。[P0–P123履歴レビュー](docs/research_history_review_20261026.md)。

## 目的と継続方針

ユーザーは約24時間（10/27 06時頃まで）で主要実験をまとめる方針を指定した。原稿はユーザーが執筆し、こちらは実験と全件結果・再現根拠の整理を担当する。普通のメッセージには応答しながら作業を続け、明示停止に従う。バッチ完了を研究目標の達成としない。[最終目標までの方針](docs/research_execution_route_20261026.md)。

[現在の状態](docs/current_status.md)／[再開手順](RESUME.md)／[次の作業](docs/next_actions.md)／[作業ボード](docs/task_board.md)／[専用Project](https://github.com/users/sophiria1225/projects/1)。

変更先は `sophiria1225/AI-` と専用Projectのみ。固定source、失敗、不明費用、[旧原稿](papers/202610_letter/checkpoint_cost_v01/README.md)を保持する。未見12課題は確認計画固定前に開かない。生のprompt、推論、生成task code、課題値、認証情報は公開しない。[AGENTS](AGENTS.md)。10月31日までのレター投稿を目指すが、採択を保証しない。

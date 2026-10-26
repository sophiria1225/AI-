# AIハーネス研究

必要な情報と最終成果の品質を保ち、要約・制御・失敗・再取得を含む仕事全体のlogical入力＋出力トークンを減らすハーネス制御を研究する。

## 現在の状態：P128全16条件閉鎖、P129実行・P130予約を継続

P128は2026-10-26 22:20 JSTに全16評価・所有server停止・回収・独立監査・図生成を完了。full/discloseは各6/8成功だが、seed57で成功損失1、seed157で改善1。unknown usageは各1（計2）で全体token差は不明、固定gateはfalse。独立監査109,295 checks PASS、監査エラー0・契約停止0。成功件数の合計一致と既知費用小計の減少を、品質維持・全仕事削減の成立とは扱わない。

[全件所見](docs/experiments/P128_findings.md)／[全16条件](materials/20261026_p128_results/README.md)／[実図](materials/20261026_p128_results/figures/README.md)／[解釈](materials/20261026_p128_results/INTERPRETATION.md)。共通成功5対の費用は1,078,497→936,656。seed157単独では3/4→4/4、全849,469→833,441だが、seed57の脱落・未知を含む全体へ一般化しない。通常receipt disclosureの効率校正で、新規性は未成立。

P129の固定6条件は22:20 JSTに既存queueから開始し、P130固定4条件の予約も維持する。普通の質問で止めず、明示停止へ従う。旧run/prepと元wrapperを編集・再起動しない。[現在の状態](docs/current_status.md)に固定予算・snapshot・後続条件を記録する。

## 以前の結果との区別

- [P127](docs/experiments/P127_findings.md)は各3/4成功・695,217 tokenで差0、全132 programで自動機構未発動、gate false。
- [P126](docs/experiments/P126_findings.md)は保存prefix再生48件が一致、13取得省略×2記録、control bytes増加。実model/API/評価0で、online品質・token効果ではない。
- [P125](docs/P125_findings.md)は両3/4成功・各766,875 token、全146 programで機構未発動。CSVはAPI80で失敗しgate false。
- [P123](docs/P123_findings.md)は3方式各4/4成功。単発893,529、別反復785,656、同時反復836,922 token。強い通常対照である別反復より同時反復は多く、固定gate false。
- [P124](docs/P124_findings.md)は保存再生20 program一致、通常cache68対提案57。実API/model0の局所検証。

seed・checkpoint・guide・cache・API上限が異なる旧phaseを一因子比較や同じ反復として混ぜない。P122の成功損失・不明1要求を含む全旧試行を保持する。[P0–P123履歴レビュー](docs/research_history_review_20261026.md)。

## 目的と継続方針

ユーザーは約24時間（10/27 06時頃まで）で主要実験をまとめる方針を指定した。原稿はユーザーが執筆し、こちらは実験と全件結果・再現根拠の整理を担当する。普通のメッセージには応答しながら作業を続け、明示停止に従う。バッチ完了を研究目標の達成としない。[最終目標までの方針](docs/research_execution_route_20261026.md)。

[現在の状態](docs/current_status.md)／[再開手順](RESUME.md)／[次の作業](docs/next_actions.md)／[作業ボード](docs/task_board.md)／[専用Project](https://github.com/users/sophiria1225/projects/1)。

変更先は `sophiria1225/AI-` と専用Projectのみ。固定source、失敗、不明費用、[旧原稿](papers/202610_letter/checkpoint_cost_v01/README.md)を保持する。未見12課題は確認計画固定前に開かない。生のprompt、推論、生成task code、課題値、認証情報は公開しない。[AGENTS](AGENTS.md)。10月31日までのレター投稿を目指すが、採択を保証しない。

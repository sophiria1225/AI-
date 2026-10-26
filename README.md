# AIハーネス研究

## 最新運用：P130起動前失敗、P131は開始後の停止を確認

P130は01:07 JSTにport検査でmodel本体・task処理前に停止した。約3時間8分の空白後、P131固定2条件を04:15:31 JSTに起動したが、開始後の運用metadataは`stopped`である。全条件完了やactor生成を断定せず、元記録を保持して停止原因・実行範囲を確認する。途中の成否・usage・生成内容は未読。

閉鎖済み原稿資料はP129まで整備済み。新規性、一般的な精度維持と全仕事token削減の最終目標は未達。P128の片seedや共通成功subsetを全体効果へ一般化しない。原稿はユーザー担当。通常会話で作業を止めず、明示停止へ従う。[時点付き経過](docs/experiments/P131_execution_status_20261027.md)。

以下はP129公開時点の記録。P130の未確認事項は上記の起動前失敗診断で更新し、元失敗を保持する。

必要な情報と最終成果の品質を保ち、要約・制御・失敗・再取得を含む仕事全体のlogical入力＋出力トークンを減らすハーネス制御を研究する。

## 現在の状態：P129全6条件閉鎖、出力修復は未発動

P129は2026-10-27 01:07 JSTに全6評価・所有server停止・回収・独立監査・図生成を完了。off/feedback/repairは各1/2成功。seed57は全方式で作業時間切れ・219,344既知token＋usage1件不明、seed157は全方式成功・295,152 token。feedback拒否・修復提案・実送信修復・保存確認済み修復は全0、固定gate false。共通成功の費用差は0、未知3件を含む総費用差は未確定。独立監査79,576 checks PASSは方式採用と別である。

[全件所見](docs/experiments/P129_findings.md)／[全6条件](materials/20261026_p129_results/README.md)／[実図](materials/20261026_p129_results/figures/README.md)／[会計・再現](materials/20261026_p129_results/INTERPRETATION.md)。通常の出力根拠検証の校正で、新規性・一般品質維持・全仕事削減は未成立。

後続P130の予約queueは01:07 JSTに起動試行1回後 `failed_no_retry` で終了した。全4条件の閉鎖は確認されておらず、原因と実行範囲を運用metadataから確認する。元失敗記録・固定sourceを保持し、元queue/prepare/wrapperを重複起動しない。普通の質問は停止扱いにせず、明示停止へ従う。[現在の状態](docs/current_status.md)。

## 以前の結果との区別

- [P128](docs/experiments/P128_findings.md)は各6/8成功でも成功損失1/改善1、unknown2で総費用差不明・gate false。共通成功5対の減少とseed157単独の改善を全体へ一般化しない。
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

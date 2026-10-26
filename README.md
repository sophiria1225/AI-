# AIハーネス研究

## 最新：P132全2条件閉鎖、実提示2回でも両失敗

P132は2026-10-27 05:11 JSTに全2評価・所有server・collector・独立監査を閉鎖した。offは171,013 token・API120上限で失敗、onは213,642既知token＋usage1件不明・API47・時間上限で失敗した。共通成功0、正確な総費用差null、固定gate false。inventory捕捉/実提示はoff1/0・on2/2。契約停止・元監査エラー0、独立監査56,861 checks PASSを方式採用と混同しない。[全件所見](docs/experiments/P132_findings.md)／[全2条件・図](materials/20261027_p132_results/figures/README.md)。

所有modelは停止済みで、追加model cohortは未起動。開始186台帳/2,231束縛と後続globalを分離し、元run/prep・P130/P131失敗・unknownを保持する。一般品質維持と全仕事token削減、新規性の最終目標は未達。通常会話を停止指示と扱わず、次は閉鎖証拠の有限診断と主張範囲の整理を進める。新model比較は別の有限計画・source/CI・全件採否を固定する。原稿はユーザー担当。

## 以下は過去時点の運用記録

## 最新運用：P132の最初のactor送信を04:27 JST頃に確認

P132は04:26:12 JSTに開始し、preflight/activationを通過。rootが最初のactor要求ファイルの作成とmodel slot処理中を確認した。時点付きの進行確認であり、全2条件の完了や品質・費用の改善ではない。要求本文・生成内容・task成否・usageは未読。同じ既知CSV1課題×seed57×inventory off/on、server最大5,400秒・06:00 JSTまでの固定比較を進める。[開始記録](docs/experiments/P132_execution_start_20261027.md)。

P132開始snapshot186台帳/2,231束縛と、その後のglobal台帳を区別する。P130/P131の失敗と約3時間の空白を保持し、凍結run/prepを変更しない。閉鎖後は全枠・unknownを残して監査・図・費用比較をまとめる。原稿はユーザー担当で、新規性、一般精度維持と全仕事token削減の最終目標は未達。通常会話で止めず明示停止へ従う。

## 過去の運用記録：P130/P131の生成前失敗

P130は01:07 JSTにport検査でmodel本体・task処理前に停止した。約3時間8分の空白後、P131固定2条件を04:15:31 JSTに起動したが、04:16 JSTに旧lease検査が新supervisor名を拒否してpreflightで停止した。所有serverは停止済み、actor生成・tokenizer count・task API・評価は0。元記録を保持し、新P132 attemptの修正を別に準備する。task成否・usage・生成内容は未読。

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

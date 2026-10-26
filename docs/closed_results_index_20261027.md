# 引継ぎ後の実験結果と主張可能範囲

P123以降の指定した7モデル比較、全56予定条件を整理する入口。原稿本文ではなく、既存の公開監査・結果資料を参照するための一覧である。P0以降の全研究成果を網羅するものではない。P111等の以前の結果と採否は[研究史](research_history_review_20261026.md)へ残す。

**[方式別・共通成功・再生・運用失敗の一覧](../materials/20261027_closed_results_index/README.md)**／[全56条件CSV](../materials/20261027_closed_results_index/conditions.csv)／[方式別CSV](../materials/20261027_closed_results_index/arms.csv)／[seed別CSV](../materials/20261027_closed_results_index/arm_seeds.csv)／[比較CSV](../materials/20261027_closed_results_index/comparisons.csv)／[JSON](../materials/20261027_closed_results_index/summary.json)／[依存hash](../materials/20261027_closed_results_index/source_manifest.json)。

## モデル比較

| Phase | 同一phaseの比較・範囲 | 観測した結果 | 主張の限界 |
|---|---|---|---|
| [P123](P123_findings.md) | 単発／別呼出し反復／同時反復、既知4課題×seed57 | 各4/4成功。普通の別反復785,656は単発893,529より12.07%減。同時反復836,922は強い別反復対照より6.53%増。反復採用あり、固定gate false | 普通rollingの既知cohort改善。同時反復の追加効果・新規性・一般品質維持は未成立 |
| [P125](P125_findings.md) | 通常cache／自動field projection、既知4課題×seed157 | 各3/4成功・766,875、全体/共通成功差0。自動partial0、gate false | 単発checkpoint共通。P123の強いrollingを上回った比較ではなく、機構の実利用もない |
| [P127](experiments/P127_findings.md) | 通常join＋明示field／自動region、既知4課題×seed157 | 各3/4成功・695,217、全体/共通成功差0。自動/明示field要求0、gate false | 通常cache各72hitを自動方式の効果へ数えない。保存再生の13取得差を移して計上しない |
| [P128](experiments/P128_findings.md) | full／receipt disclosure、既知4課題×seeds57/157 | 各6/8成功だが損失1・改善1。各unknown1で全体差null。共通成功5対は1,078,497→936,656。実有料入力に109固有turn、gate false | 共通成功部分集合の13.15%減は、成功損失と未知費用を含む全体改善ではない。seed57 gate false／157 trueを別々に残す |
| [P129](experiments/P129_findings.md) | off／feedback／deterministic repair、既知CSV×seeds57/157 | 各1/2成功、各514,496既知小計＋unknown1。共通成功seed157は各295,152で差0。拒否/修復0、gate false | 主対照は通常feedback、offは補助。全体差は0と断定せずnull、修復の効果未測定 |
| [P132](experiments/P132_findings.md) | 同じfeedback下のinventory off/on、既知CSV×seed57 | 各0/1成功。off171,013確定、on213,642既知＋unknown1。onは実提示2回、共通成功0、gate false | 未知を0とせず全体差null。共通成功差もnull。単一seedの通常機能比較で、提示タイミング優位や新規性を示さない |
| [P133](experiments/P133_findings.md) | P123通常rolling／費用回収予測、既知CSV×seeds57/157 | 各1/2成功・434,623、unknown0、全体/共通成功差0。実拒否/影の拒否0、gate false | 規則が拒否したときの効果を示さない。P123と同額のseed57を新しい独立反復としてプールしない |

## 比較の読み方

56は予定条件の件数で、56独立標本ではない。同じ既知課題とseedが反復される。各phase内の固定cohort合計とseed別結果を示し、phase間やseed間を独立な効果推定へプールしない。CSVのAPI上限はP123/P125/P133が80、P127/P128/P129/P132が120。単発/反復checkpoint、通常cache、join、明示field、receipt表示、guide、feedbackも異なるため、別phaseの総token差を一因子の効果としない。

費用はactor＋focusのlogical入力出力。knownは既知小計であり、unknown呼出しが残る全体の厳密費用・差はnull。cached inputを控除せず、失敗・要約・修復の費用を残す。共通成功は同じ成功を達成した対だけの記述的集計で、成功改善・損失・両失敗を置換しない。P128/P129の正式gate用の共通成功差は、全cohort既知を要求する元定義に従いnullを保持し、計算できる部分集合差とは別列にした。

全7cohortのphase全体の固定gateはfalse。P123の普通rolling改善を、新規技術の成立や統計的非劣性へ言い換えない。監査PASSは会計・記録の整合確認で、意味保存の一般証明や採用判定とは別である。元の共有formatter/producer監査への依存などは各独立監査の限界を参照する。

## 保存再生と運用記録

P124/P126は[別表](../materials/20261027_closed_results_index/replays.csv)。P124は保存backend68→57・partial22、P126は旧2記録で各80→67・partial計26。実環境API/model/evalは0であり、実API削減、最終品質、全仕事token改善は未測定。P126は通常prefix境界44件（正常終了40＋既知エラー4）とfrontier4件を分け、未知の続きは実行していない。frontierで真の最終full-root同値を主張しない。

P130のport検査失敗、P131のsupervisor識別失敗、P134の前件queue失敗も[別行](../materials/20261027_closed_results_index/operational_attempts.csv)に保持する。いずれもtask生成・評価未開始で、課題失敗や0tokenの成功試行へ変換しない。P133は元audit/session/reportの0/0/1を保存し、原source `66d9eb7` と別data-only回収source `309e2eb`、独立回収監査の系譜を区別する。追加model/API/eval/tokenizerは0。

P135は[公開開始記録](experiments/P135_execution_start_20261027.md)の2026-10-27 08:15:47 JST開始・08:18:19 JST処理確認だけを参照する。この一覧に閉鎖結果は未収録で、予定6以外の費用・評価数・成否は空欄。途中成果を読んでいない。この時点記録を将来も「現在実行中」という主張には使わない。

未見12シナリオはこの資料作成でも閲覧していない。保存生成code・原監査・model/API/evaluator/tokenizerの再実行、旧台帳や原稿本文の変更はない。

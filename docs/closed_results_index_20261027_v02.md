# 引継ぎ後の実験結果と主張可能範囲 v02

P123以降の指定9モデルcohort、全68予定条件・63評価を参照する入口。元の[7cohort・56条件のv01](closed_results_index_20261027.md)は凍結保持し、P135/P136の正規公開値12行を追補した。全研究成果の網羅でも原稿本文でもない。P111等の以前の結果・採否は[研究史](research_history_review_20261026.md)へ残す。

**[追加方式・比較と費用欠測の一覧](../materials/20261027_closed_results_index_v02/README.md)**／[全68条件CSV](../materials/20261027_closed_results_index_v02/conditions_68.csv)／[追加方式CSV](../materials/20261027_closed_results_index_v02/added_arms.csv)／[追加比較CSV](../materials/20261027_closed_results_index_v02/added_comparisons.csv)／[公開JSON](../materials/20261027_closed_results_index_v02/publication_summary.json)／[公開依存hash](../materials/20261027_closed_results_index_v02/publication_manifest.json)。既存7cohortの方式・seed・比較表は元v01の資料をそのまま参照する。

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
| [P135](experiments/P135_findings.md) | raw／counts／entity fields、既知CSV×seeds57/157 | raw1/2成功・434,623確定。counts/fieldsは各0/2成功、既知274,986/302,737＋各unknown1。主共通成功0、rawへの損失1、entity行/query0、gate false | 全体・共通成功差null。主2方式のseed57は通知前にAPI上限、seed157は通知時unknownで詳細非開示。行0をfield不要や義務なしとしない。初期interface差・handle差がありfield対応の効果を分離できない |
| [P136](experiments/P136_findings.md) | raw／IDs／IDs＋fields、既知CSV×seeds57/157、予定6 | raw57だけ評価済成功332,588、worker未完1、未実施4。usage欠測5、比較・厳密総費用null、gate false | 記録unknown0は全費用既知ではない。途中workerの別補足223,145を加算しない。全6実行済み・品質喪失0・field効果なしと断定しない |


## 比較の読み方

68は予定条件の件数で、68独立標本ではない。元56行と新12行に由来する。同じ既知課題とseedが反復される。各phase内の固定cohort合計とseed別結果を示し、phase間やseed間を独立な効果推定へプールしない。CSVのAPI上限はP123/P125/P133/P135/P136が80、P127/P128/P129/P132が120。単発/反復checkpoint、通常cache、join、明示field、receipt表示、guide、feedbackも異なるため、別phaseの総token差を一因子の効果としない。

費用はactor＋focusのlogical入力出力。knownは既知小計であり、unknown呼出しが残る全体の厳密費用・差はnull。cached inputを控除せず、失敗・要約・修復の費用を残す。共通成功は同じ成功を達成した対だけの記述的集計で、成功改善・損失・両失敗を置換しない。P128/P129の正式gate用の共通成功差は、全cohort既知を要求する元定義に従いnullを保持し、計算できる部分集合差とは別列にした。

全9cohortのphase全体の固定gateはfalse。P136は一部未実施のまま記録を閉鎖しており、全条件の評価完了を意味しない。P123の普通rolling改善を、新規技術の成立や統計的非劣性へ言い換えない。監査PASSは会計・記録の整合確認で、意味保存の一般証明や採用判定とは別である。元の共有formatter/producer監査への依存などは各独立監査の限界を参照する。

## 保存再生と運用記録

P124/P126は[別表](../materials/20261027_closed_results_index/replays.csv)。P124は保存backend68→57・partial22、P126は旧2記録で各80→67・partial計26。実環境API/model/evalは0であり、実API削減、最終品質、全仕事token改善は未測定。P126は通常prefix境界44件（正常終了40＋既知エラー4）とfrontier4件を分け、未知の続きは実行していない。frontierで真の最終full-root同値を主張しない。

P130のport検査失敗、P131のsupervisor識別失敗、P134の前件queue失敗も[別行](../materials/20261027_closed_results_index/operational_attempts.csv)に保持する。いずれもtask生成・評価未開始で、課題失敗や0tokenの成功試行へ変換しない。P133は元audit/session/reportの0/0/1を保存し、原source `66d9eb7` と別data-only回収source `309e2eb`、独立回収監査の系譜を区別する。追加model/API/eval/tokenizerは0。


## unknownと欠測

全68行で記録済unknownは8呼出し、usage件数欠測は別の5条件。CSV空欄はnullであり、0へ補完しない。既知小計を足せても厳密総費用はnullで、phase横断の合計を方式の効果や独立標本の統計へ使わない。P136の別診断223,145 tokensは認証済み集計に加算していない。未計測のP135 field行をentity行から推定することもしない。

## P137の位置付け

P137は[2026-10-27 12:29:26 JST開始・12:31:46 JST処理確認の固定記録](experiments/P137_execution_start_20261027.md)と[予定4・本一覧に未収録のplaceholder](../materials/20261027_closed_results_index_v02/P137_placeholder.csv)だけを参照する。現在の進捗・成否・費用を表さず、68行にも加えない。実成果・usage・payloadは読んでいない。P137のseed57は単独、seed157だけが記述的比較という固定範囲を、P136の元欠測・gateを置換するために用いない。

## 出所

[準備資料の独立検算](../reports/closed_results_index_v02_preparation_review_20261027.json)は2,437項目PASS。原CSV・準備summary・manifestは同byteコピーし、公開statusと出所の追加は別`publication_summary.json`に明示した。元producer監査・モデル・API・評価器・tokenizer・保存生成codeの再実行、未見12シナリオの閲覧、旧台帳・原稿本文の変更はない。

# 引継ぎ後の閉鎖実験結果一覧

対象はP123以降の指定7モデル比較・全56条件。これは全研究成果の網羅でも56独立標本でもない。
以前のP111等を含む経緯は[研究史](../../docs/research_history_review_20261026.md)、主張と比較条件は[入口](../../docs/closed_results_index_20261027.md)を参照。

## 方式別の固定cohort集計

複数seedの行は元の固定cohortの記述的合計。seed別値は[arm_seeds.csv](arm_seeds.csv)、全56行は[conditions.csv](conditions.csv)。
knownは既知小計。unknownが1件でも全費用は不明。cached inputを差し引かず、actor/focus・失敗・修復費用を含む。

| Phase | Arm | seed | 予定/評価/成功 | known input | known output | known total | unknown呼出し | exact total | 実機構回数 | 固定gate |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| P123 | single_checkpoint | 57 | 4/4/4 | 868,760 | 24,769 | 893,529 | 0 | 893,529 | 2 | false |
| P123 | rolling_separate | 57 | 4/4/4 | 760,248 | 25,408 | 785,656 | 0 | 785,656 | 3 | false |
| P123 | rolling_inline | 57 | 4/4/4 | 808,686 | 28,236 | 836,922 | 0 | 836,922 | 3 | false |
| P125 | eager_cached | 157 | 4/4/3 | 743,463 | 23,412 | 766,875 | 0 | 766,875 | 0 | false |
| P125 | automatic_projection_cached | 157 | 4/4/3 | 743,463 | 23,412 | 766,875 | 0 | 766,875 | 0 | false |
| P127 | explicit_joined_fields | 157 | 4/4/3 | 673,911 | 21,306 | 695,217 | 0 | 695,217 | 0 | false |
| P127 | automatic_region_joined_fields | 157 | 4/4/3 | 673,911 | 21,306 | 695,217 | 0 | 695,217 | 0 | false |
| P128 | full | 57;157 | 8/8/6 | 1,661,794 | 58,782 | 1,720,576 | 1 | — | 0 | false |
| P128 | disclose | 57;157 | 8/8/6 | 1,550,089 | 58,786 | 1,608,875 | 1 | — | 109 | false |
| P129 | off | 57;157 | 2/2/1 | 486,896 | 27,600 | 514,496 | 1 | — | 0 | false |
| P129 | feedback | 57;157 | 2/2/1 | 486,896 | 27,600 | 514,496 | 1 | — | 0 | false |
| P129 | repair | 57;157 | 2/2/1 | 486,896 | 27,600 | 514,496 | 1 | — | 0 | false |
| P132 | off | 57 | 1/1/0 | 164,442 | 6,571 | 171,013 | 0 | 171,013 | 0 | false |
| P132 | checkpoint_inventory | 57 | 1/1/0 | 197,899 | 15,743 | 213,642 | 1 | — | 2 | false |
| P133 | rolling_separate | 57;157 | 2/2/1 | 417,694 | 16,929 | 434,623 | 0 | 434,623 | 0 | false |
| P133 | empirical_payback | 57;157 | 2/2/1 | 417,694 | 16,929 | 434,623 | 0 | 434,623 | 0 | false |

実機構回数の定義: P123: checkpoint採用回数／P125: 自動projection partial hit／P127: 自動region partial hit／P128: 有料入力に含まれた固有disclosed turn数／P129: 保存根拠まで確認した修復数／P132: inventory実actor提示回数／P133: 予測に基づく実focus拒否回数。
P123の採用回数、P128の固有turn数、P132のactor提示回数は相互に同じ単位ではない。通常cache/明示fieldの回数はconditions.csvに別列で保存。

## 同一phase内の比較

差はtreatment−baseline。共通成功は記述的部分集合で、品質損失・unknownを含む全体gateを上書きしない。

| Phase / 比較 | baseline → treatment | 共通成功対 | 全体exact差 | 共通成功B/A | 共通成功の記述的差 | 元gate用の共通成功差 | 成功損失/改善 |
|---|---|---:|---:|---|---:|---:|---|
| P123 / ordinary_anchor | single_checkpoint → rolling_separate | 4 | -107,873 | 893,529 / 785,656 | -107,873 | — | 0/0 |
| P123 / inline_vs_single | single_checkpoint → rolling_inline | 4 | -56,607 | 893,529 / 836,922 | -56,607 | — | 0/0 |
| P123 / inline_vs_strong_ordinary | rolling_separate → rolling_inline | 4 | 51,266 | 785,656 / 836,922 | 51,266 | — | 0/0 |
| P125 / primary | eager_cached → automatic_projection_cached | 3 | 0 | 618,487 / 618,487 | 0 | 0 | 0/0 |
| P127 / primary | explicit_joined_fields → automatic_region_joined_fields | 3 | 0 | 352,584 / 352,584 | 0 | 0 | 0/0 |
| P128 / primary | full → disclose | 5 | — | 1,078,497 / 936,656 | -141,841 | — | 1/1 |
| P129 / primary | feedback → repair | 1 | — | 295,152 / 295,152 | 0 | — | 0/0 |
| P129 / auxiliary | off → repair | 1 | — | 295,152 / 295,152 | 0 | — | 0/0 |
| P132 / primary | off → checkpoint_inventory | 0 | — | — / — | — | — | 0/0 |
| P133 / primary | rolling_separate → empirical_payback | 1 | 0 | 332,588 / 332,588 | 0 | 0 | 0/0 |

P123普通rolling対単発は記述的anchorで専用gate欄はない。P123 inlineの正式gateは両通常対照を上回ることを要求しfalse。
P128/P129の元gate用の共通成功差nullと、費用が既知の共通成功部分集合の計算値は区別する。P132共通成功0の費用差は0でなくnull。
seed別の全比較・P128各seedの固定gateも[comparisons.csv](comparisons.csv)と[summary.json](summary.json)へ保持。

## 保存応答再生と未開始・未閉鎖

| Phase | 種類 | 範囲 | 観測 | 全仕事token/課題品質効果 |
|---|---|---|---|---|
| P124 | 保存prefix再生 | 1旧記録×2arm×10program=20 | 境界20・方式間10一致、保存backend68→57、partial22 | 未測定。実環境API/model/eval0 |
| P126 | 保存frontier再生 | 2旧記録×2arm×12program=48 | 通常prefix境界44（正常終了40＋既知エラー4）・方式間22一致、frontier4、各記録保存backend80→67、partial計26 | 未測定。実環境API/model/eval0 |
| P130 | not_started_operational_failure | 予定4・評価0 | server port検査でmodel subprocess前に停止 | 課題実験未開始、運用失敗を保持。課題成否/費用効果は未測定 |
| P131 | not_started_operational_failure | 予定2・評価0 | 旧supervisor識別が新basenameを拒否し計数・生成前に停止 | 課題実験未開始、運用失敗を保持。課題成否/費用効果は未測定 |
| P134 | not_started_operational_failure | 予定6・評価0 | P133 report障害で前件queueが停止、model/server/preflight/task未開始 | 課題実験未開始、運用失敗を保持。課題成否/費用効果は未測定 |
| P135 | start_record_only_no_closed_results_in_index | 予定6・評価— | 08:15:47 JST開始、08:18:19 JST処理確認。この一覧に閉鎖結果未収録、途中成果未読 | この一覧に閉鎖結果未収録、費用/成否は未記載 |

保存backend件数は固定応答再生の計数で、実API削減・最終成功・全仕事token改善ではない。P126は未知suffixを実行せず、frontierで真の最終full-root同値を主張しない。
P133元reportのexit1と別data-only回収を保持し、同phaseを再実行したと数えない。P130/P131/P134の未開始失敗も一覧から除かない。

## 再生成と根拠

`python scripts/build_closed_results_index_20261027.py --check` は公開JSONだけを再集計して保存資料へ照合する。
`--output-dir NEW_DIRECTORY` は既存資料を上書きせず別ディレクトリへ生成する。
[source_manifest.json](source_manifest.json)は入力資料・generator・出力のSHA256を保存する。
この固定対象では全56条件が評価済み。予定行の欠落・未評価・根拠不一致があれば補完せず生成を停止する。元監査や生成code、model/API/tokenizer/evaluatorは再実行しない。

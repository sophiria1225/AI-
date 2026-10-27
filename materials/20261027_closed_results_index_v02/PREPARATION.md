# 公開済み結果一覧の私用追補準備

既存の7cohort・56予定条件は変更していない。P135/P136の正規公開audit、summary、CSV、build manifestを突合し、別ファイルに12予定条件を追補した。準備一覧は9cohort・68予定条件、63評価である。予定件数は独立標本数ではなく、phaseをまたぐ合計費用を方式効果として比較しない。

P135は6評価・成功1、既知1,012,346 tokens、未知usage2、厳密総量null。rawは1/2成功・434,623確定、counts/fieldsは各0/2成功・274,986/302,737既知小計＋各未知1。主比較の共通成功0、raw対fieldsはseed57で成功損失1。全費用差・共通成功差はnull、gate false。

P136は6予定のうち評価1（raw57成功332,588）、未完worker1、未実施4。usage欠測5なので厳密総量はnull。記録済unknown呼出し0を、未知費用がないという意味に使わない。両主要比較は未成立で、成功損失・共通成功数はnull。元gate falseを保持した。別診断の223,145 tokensは本表にも認証合計にも加えていない。

P137は予定4・未収録のplaceholderのみ。実際の成否、usage、payload、進捗記録は読んでいない。閉鎖後に元4行を新しい別版で追加できるが、P136の未完・未実施行を置換したり、同一cohortへ合算してgateを通したりしない。将来P137を含める場合の72は複数cohortの予定行数であり、独立試行数や現在の完了数ではない。

この準備では既存indexのP135開始時placeholderを新たな閉鎖行と重複計数しない。保存再生P124/P126、未開始P130/P131/P134、P133の元report失敗と別data-only回収の系譜はそのまま残す。古いindexの時点記録は上書きしない。

`conditions_68.csv`は元56＋新12、`added_arms.csv`は新6方式、`added_comparisons.csv`は新2cohortの主/補助×全体/seed57/seed157。CSV空欄はnull。P135に存在しないfield-row計測欄は推定せずnull。集約のknown subtotal 0とaccounted 0は空の既知小計であり、実行費用0ではない。

元監査・生成Python・model/API/tokenizer/evaluatorの再実行、repo編集、PR、台帳更新、原稿作成はいずれも0。入力hashをbefore/after照合した。

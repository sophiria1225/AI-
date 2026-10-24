# P114: 初回入力の確認と実行開始

2026年10月25日. 固定head `c74c579c1addad248cffcdb9639178b20d5b46b6` のpushとpull_request両workflow、両accounting-and-syntax jobが成功し、PR #483をmergeした. 別の固定実行木から所有serverを起動し、public_only対照４条件の有限実行を開始した. 結果の比較は未完了.

初回４要求はP111の各課題３方式と、完全要求、モデルとruntime、context、native入力token、公開予算通知、入力受入条件がすべて一致した. [全４入力](initial_checks.csv)は3,115／3,104／3,077／3,123 token. これは初回入力の一致であり、後続の行動・最終品質・費用削減を意味しない. サーバーのPIDと開始時刻は新しい実行なので一致条件に含めない. 初回実生成のcacheは各実行の返答で別途確認する.

全４条件を固定順で実行し、終了後に全12過去条件と併記する図のコードを準備した. 合成値のpreviewだけで未知表示・未実行表示・全16条件のラベルを目視し、実結果の図はまだ生成していない. 合成図は公開資料に含めない. 図は閉鎖済みの新旧監査、server停止とplan指紋を要求する.

[固定計画](../../docs/experiments/P114_whole_task_public_only_history.md)／[初回確認](../../reports/P114_initial_checks.json)／[実行固定](../../reports/P114_activation_v01.json)／[図のコード](../../scripts/plot_public_only_history_results.py).

P111の採用基準未達と不明使用量２件、未見12課題の分離、原稿保留を維持する. 通常対照を新手法や独立確認と呼ばず、途中結果による条件変更をしない.

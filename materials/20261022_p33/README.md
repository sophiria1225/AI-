# P33：入力削減と実行費用の分析

[７枚のPDF](AI_harness_P33_20261022.pdf)／[スライドHTML](index.html)／[説明・原記録への対応](../../docs/P33_findings.md)。2026年10月22日10:23に閉じた全12条件の追加資料。朝の資料を上書きせず、目的と今回の局所比較を冒頭で区別した。

全履歴／出力省略／省略＋一覧はいずれも４既知課題中２件成功。初回入力の減少と、継続全体の総トークン増加を別の図にした。品質維持・独自方式の成立は未確認。失敗時の停止理由と課題別結果を省略しない。

生成器は `scripts/build_output_view_report.py`。集計・生成器のSHAは [build_manifest.json](build_manifest.json)、全12条件の数値はCSV、図は `figures/` に保存。PDF７ページの表紙・全ページを描画して確認し、枠外・重なりの機械検査は０件。[layout_checks.json](layout_checks.json)。PDFの確認記録は [visual_review.json](visual_review.json)。

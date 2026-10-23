# 残時間表示の全８条件：P80

[PDF４枚](AI_harness_budget_visibility_20261024.pdf)／[画面表示](index.html)／[結果と限界](../../docs/P80_findings.md)／[全条件CSV](all_conditions.csv)／[全４対CSV](all_pairs.csv)／[全143生成CSV](all_model_calls.csv)／[全142プログラムCSV](all_python_program_results.csv)。

表示M・非表示Hはいずれも3/4成功。全tokenはMが787,092、Hが既知780,394＋不明１生成。Hの書出しは時間切れで未達となり、全体の採用基準は未達。確定分だけの差を削減としない。作業時間合計はMが1,897.7秒、Hが2,975.3秒。

全８条件を評価し、監査不一致０。所有推論器停止とPID不在を確認した。論理tokenにはcache入力、推論、通知、失敗・回復を含む。全143生成・437 API・８評価、保留12課題閲覧０。新規手法、一般的品質維持、採録に足る貢献は未確立。

図は既知全４課題を同じ軸で表示し、使用量不明を右向き三角と「＋不明」で明示する。全４頁を目視し、機械的な配置検査も不一致０。生成源・CSV・PDFのhashは[manifest](build_manifest.json)へ保存した。

# P139 図表

- [全仕事の既知費用 PNG](whole_job_cost.png)／[PDF](whole_job_cost.pdf)
- [全20対応行と固定比較 PNG](paired_comparisons.png)／[PDF](paired_comparisons.pdf)
- [作図データ](figure_data.json)、[出力hash](output_manifest.json)、[実際に一度使用したrenderer](draw_p139_results_20261027.py)

4既知課題×2時点×2表現の全16条件を含む。T/Rは閾値＋再帰要約、T/Dは閾値＋delta、E/Rは累積再提示量＋再帰要約、E/Dは累積再提示量＋delta。費用は全roleの論理入力＋出力で、cached inputを控除しない。斜線とunknownは費用の下界を示し、確定総費用でも削減の証拠でもない。全方式の固定総費用欄nullと比較のnullを保持する。

表現比較の`Actual intervention`はdelta配信と厳密な介入前prefix一致をともに要求する判定である。第4課題T/D−T/Rはdelta採用1回・既知actor露出9回だがprefix不一致のためfalseになる。falseを「delta未配信」と解釈しない。E/Dではdelta採用と露出がともに0であり、両者を区別する。

T/D−T/Rの+18,567 tokensは記述的な全仕事の増加で、表現だけの因果効果とは分離できない。全5比較gate false。独立確認は[こちら](../../../reports/P139_actual_figures_review_20261027.json)。PNG/PDF・データ・rendererは閉鎖後に一度作成された元bytesをそのまま保存し、公開用に再描画していない。

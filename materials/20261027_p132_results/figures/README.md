# P132: 全2条件の図

[全仕事tokenと公式成否](v01/p132_tokens_quality.png)／[PDF](v01/p132_tokens_quality.pdf)／[捕捉・実提示と捕捉費用](v01/p132_inventory_exposure_cost.png)／[PDF](v01/p132_inventory_exposure_cost.pdf)。元のv01全byteを保持している。

両条件は公式失敗。offは171,013 token、onは213,642既知小計＋usage1件不明。onは棒で確定総量を描かず、既知小計の位置に三角を置く。共通成功0はゼロ費用ではない。捕捉1/2と実提示0/2を別表示し、API47対120や捕捉bytesをtoken削減としない。

## 公開データからの再描画

元の閉鎖監査はprivate記録を含むため、公開版で再認証したとは扱わない。以下はhashで固定した図データの再描画専用である。Python 3.12とmatplotlib 3.11.2で確認した。元rendererとdata/manifestを保持し、新しい出力dirを使う。

```sh
python scripts/redraw_p132_public_figures_20261027.py \
  --figure-data materials/20261027_p132_results/figures/v01/figure_data.json \
  --original-manifest materials/20261027_p132_results/figures/v01/output_manifest.json \
  --manifest-sha256 ee31efb13d1779fb459872452a0adf40cff9e36b17cb09f08daab3e1bd9127f1 \
  --renderer-source scripts/draw_p132_results_20261027.py \
  --output-dir /tmp/P132_public_redraw_NEW
```

公開manifest SHA: `ee31efb13d1779fb459872452a0adf40cff9e36b17cb09f08daab3e1bd9127f1`。この公開digestが信頼起点であり、任意のデータとその自己計算digestだけでは実験の認証にならない。データの一致を検査するが、PDFの作成日時やfont環境により画像byteの一般的一致は保証しない。元図・元dataは上書きしない。[図データ](v01/figure_data.json)／[元manifest](v01/output_manifest.json)。

[実図の独立確認](../../../reports/P132_actual_figures_review_20261027.json)は5,239 checks PASS。公開データだけの[再描画確認](../../../reports/P132_public_redraw_verification_20261027.json)では、この環境のPNG2件とfigure_dataが元byteに一致した。実験・閉鎖監査・private loaderは再実行していない。

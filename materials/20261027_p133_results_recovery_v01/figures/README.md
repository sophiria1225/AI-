# P133 全4条件の図

[全仕事token・公式成否](v01/whole_job_cost.png)／[PDF](v01/whole_job_cost.pdf)／[actor・paid focus・実拒否](v01/paid_focus_and_control.png)／[PDF](v01/paid_focus_and_control.pdf)。全4条件・unknown0を保持。両方式は同じ1/2成功・434,623 tokens、全体差0・共通成功差0・実拒否0・gate falseである。

元plotterの表示・計算を変更せず、別recovery loaderで閉鎖proof、元audit、回収manifest、独立reviewを照合して1回描画した。元collector完了を捏造せず、report-only回収をdataのlineageへ残している。元の2PNG/SVG/PDFとdata/manifestは同bytesで保存した。

## 公開dataからの再描画

```sh
python scripts/draw_p133_results_20261027.py --redraw \
  --figure-data materials/20261027_p133_results_recovery_v01/figures/v01/figure_data.json \
  --original-manifest materials/20261027_p133_results_recovery_v01/figures/v01/output_manifest.json \
  --manifest-sha256 63c71a2d92dcfabfd81df7ee33f1b502c7ed4b9a72fc819855cbe1ceb5d08fed \
  --output-dir /tmp/P133_public_redraw_NEW
```

公開manifest SHAは `63c71a2d92dcfabfd81df7ee33f1b502c7ed4b9a72fc819855cbe1ceb5d08fed`。この出版digestを信頼起点にdataと元plotterのhashを検査する。これは公開データの再描画であり、private記録を使った閉鎖監査を再認証したものではない。PDF作成日時・font環境等により出力byteの一般的一致は保証しない。元filesを上書きしない。

[独立した図・公開算術の確認](../../../reports/P133_recovered_figures_peer_review_20261027.json)は全4と実2PNGを確認した限定reviewであり、元private監査の再実行ではない。[公開再描画の確認](../../../reports/P133_public_redraw_check_20261027.json)では同じ環境でdataと2PNGのbyte一致を確認した。

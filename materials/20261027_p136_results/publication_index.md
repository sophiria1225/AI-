# P136 閉鎖資料の入口

予定6行のうち評価完了1、worker未完1、未実施4をすべて保持した資料である。raw seed57は成功・332,588 tokens。主比較/補助比較は未成立、全仕事総費用と比較差はnull、固定gate false。欠測を課題失敗や費用0としない。[所見と限界](../../docs/experiments/P136_findings.md)を参照。

- [元builder README](README.md)、[全6予定行CSV](conditions.csv)、[元集計JSON](summary.json)、[build manifest](build_manifest.json)
- [元監査](../../reports/P136_comparison.json)、[server会計](../../reports/P136_server_session.json)、[独立検算の公開投影](../../reports/P136_closed_independent_audit_20261027.json)
- [全仕事費用PNG](figures/whole_job_cost.png)／[SVG](figures/whole_job_cost.svg)／[PDF](figures/whole_job_cost.pdf)
- [actor・focusと機構計数PNG](figures/paid_work_and_obligations.png)／[SVG](figures/paid_work_and_obligations.svg)／[PDF](figures/paid_work_and_obligations.pdf)
- [図データ](figures/figure_data.json)、[figure manifest](figures/output_manifest.json)、[元図README](figures/README.md)、[固定renderer](figures/draw_p136_results_20261027.py)
- [コピー来歴](../../reports/P136_results_copy_manifest_20261027.json)、[公開依存hash](../../reports/P136_results_provenance_20261027.json)
- [未完workerの限定補足](../../reports/P136_incomplete_worker_public_20261027.json)、[first-notice診断の公開投影](../../reports/P136_first_notice_diagnostic_public_20261027.json)、[rootの閉鎖解釈と別cleanup](../../reports/P136_closed_root_interpretation_public_20261027.json)
- 別証拠：[P135 rawのAPI上限補足](../../docs/experiments/P135_raw_API_frontier_public_note_20261027.md)、[公開集約](../../reports/P135_raw_API_frontier_public_20261027.json)、[root review](../../reports/P135_raw_API_frontier_public_root_review_20261027.json)

## 費用とbytesの解釈

元summaryの認証済み小計332,588は1件からの和である。残り5件は使用量計数が欠測で、全条件費用はnull。各方式の`reported_conditions=0`に対応する小計0を、実際の費用0の測定と扱わない。途中workerの別診断を元の認証済み全仕事表に加算しない。

通知JSON body上限2,048 UTF-8 bytesと、改行込みの固定heading43 bytesは別であり、追加system contentの上限は2,091 bytes。HTTP全payload/token上限ではない。native count/admission/sendはheading込み全message viewを使う。元builder READMEは変更せず、この範囲補足を分離した。

## 公開データからの再描画

公開figure data・manifest・同じrendererとMatplotlibだけで新出力先に再描画できる。raw履歴やprivate reviewは不要。元実験や監査の再認証ではなく、今回の公開で再描画は行っていない。

```sh
python figures/draw_p136_results_20261027.py --redraw \
  --figure-data figures/figure_data.json \
  --original-manifest figures/output_manifest.json \
  --manifest-sha256 MANIFEST_SHA256 \
  --output-dir NEW_OUTPUT_DIRECTORY
```

`MANIFEST_SHA256`はcopy manifestの`materials/20261027_p136_results/figures/output_manifest.json`の値を使う。Python 3.10以上とMatplotlibが必要。font/library/date metadataによって画像bytesが変わっても、元科学データはhashで束縛される。既存出力先は上書きしない。

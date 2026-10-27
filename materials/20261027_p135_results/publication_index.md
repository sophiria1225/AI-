# P135 閉鎖結果の入口

全6条件を保持した資料である。raw 1/2成功、counts/entity各0/2成功、unknown2件、詳細entity行/query0、固定gate false。未知費用を含む方式間の全仕事差はnull。詳細は[所見と限界](../../docs/experiments/P135_findings.md)を参照。

- [元builderのREADME](README.md)、[全6条件CSV](conditions.csv)、[集計JSON](summary.json)、[build manifest](build_manifest.json)
- [元監査](../../reports/P135_comparison.json)、[server会計](../../reports/P135_server_session.json)、[独立検算の公開投影](../../reports/P135_closed_independent_audit_20261027.json)
- [全仕事費用PNG](figures/whole_job_cost.png)／[SVG](figures/whole_job_cost.svg)／[PDF](figures/whole_job_cost.pdf)
- [actor・focusと介入PNG](figures/paid_work_and_obligations.png)／[SVG](figures/paid_work_and_obligations.svg)／[PDF](figures/paid_work_and_obligations.pdf)
- [図の元データ](figures/figure_data.json)、[figure manifest](figures/output_manifest.json)、[図の説明](figures/README.md)、[固定renderer](figures/draw_p135_results_20261027.py)
- [別担当の科学レビュー](../../reports/P135_closed_scientific_review_20261027.json)
- [閉鎖後の3補助診断](../../reports/P135_postclose_diagnostics_public_summary_20261027.json)
- [コピーの系譜](../../reports/P135_results_copy_manifest_20261027.json)、[公開資料の依存hash](../../reports/P135_results_provenance_20261027.json)

## 公開データだけからの再描画

必要なのは公開figure data・manifest・同じrendererとMatplotlibであり、raw履歴や私有reviewは不要である。下記は再描画用で、元実験や元監査の再認証ではない。既存出力先を上書きしない。

```sh
python figures/draw_p135_results_20261027.py --redraw \
  --figure-data figures/figure_data.json \
  --original-manifest figures/output_manifest.json \
  --manifest-sha256 MANIFEST_SHA256 \
  --output-dir NEW_OUTPUT_DIRECTORY
```

`MANIFEST_SHA256`にはcopy manifest内の`materials/20261027_p135_results/figures/output_manifest.json`のSHA256を使う。Python 3.10以上とMatplotlibが必要。font/library/date metadataによりPNG/SVG/PDFのbytesは変わり得るが、元科学データはSHAで束縛される。今回の公開では再描画していない。

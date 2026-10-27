# P137 閉鎖資料の入口

P136で未実施だった4条件を別cohortで観測し、全4評価・成功0。seed57 fieldsは368,024既知tokens＋unknown1、seed157のfields/IDs/rawは各102,035確定tokensで双方失敗の差0、共通成功は0組・費用差null。全体既知小計674,129、unknown1、usage件数欠測0、厳密総費用null。model64/API311/評価4を保持する。

seed57 fieldsは単独、主/補助比較は同P137のseed157各1組だけ。方式別1/1/2条件の総和を効果比較しない。採用を評価しない設計なので`development_gate_met=false`と`scientific_adoption_evaluated=false`は固定。P136の元6行・欠測・gateを補修・合算しない。[所見と限界](../../docs/experiments/P137_findings.md)を参照。

- [元builder README](README.md)、[全4行CSV](conditions.csv)、[元集計JSON](summary.json)、[build manifest](build_manifest.json)
- [元監査](../../reports/P137_comparison.json)、[server会計](../../reports/P137_server_session.json)、[独立検算の公開投影](../../reports/P137_closed_independent_audit_20261027.json)
- 表示用v02：[全仕事PNG](figures_v02/whole_job_cost.png)／[SVG](figures_v02/whole_job_cost.svg)／[PDF](figures_v02/whole_job_cost.pdf)、[actor/focus・通知PNG](figures_v02/paid_work_and_obligations.png)／[SVG](figures_v02/paid_work_and_obligations.svg)／[PDF](figures_v02/paid_work_and_obligations.pdf)
- [v02図データ](figures_v02/figure_data.json)、[v02 manifest](figures_v02/output_manifest.json)、[v02 README](figures_v02/README.md)、[v02 renderer](figures_v02/draw_p137_results_20261027_v02.py)、[layout限定検証](../../reports/P137_layout_v02_verification_20261027.json)
- 元v01：[全仕事図](figures/whole_job_cost.png)、[actor/focus・通知図](figures/paid_work_and_obligations.png)、[元図README](figures/README.md)、[元manifest](figures/output_manifest.json)、[固定renderer](figures/draw_p137_results_20261027.py)
- [seed57のfield完備後の限定補足](../../reports/P137_seed57_field_completion_gap_20261027_v02.json)
- [prefix補足の公開投影](../../reports/P137_first_notice_prefix_public_20261027.json)、[copy manifest](../../reports/P137_results_copy_manifest_20261027.json)、[公開依存hash](../../reports/P137_results_provenance_20261027.json)

## 読み方

unknown呼出しとusage件数欠測を別々に保持し、空欄/nullを0へ補完しない。seed157は主・補助とも双方失敗1組。空common groupのtoken差0は空和の帳簿値で、共通成功での効果測定はnullである。cached inputを控除せず、通知・focus・失敗の費用も含める。累積ID/field行はunique entity数ではなく、観測field完備も公式課題成功ではない。

通知JSON body最大2048 UTF-8 bytes＋固定heading43 bytesで、追加system content最大2091 bytes。HTTP全payloadやtoken上限ではない。native count/sendにはheading込み全messageを使い、bytesをtokensへ換算しない。

prefix補足のprimaryは同P137 seed157に限定する。別cohort P136未完IDs57対P137 fields57は探索的照合で、seed57をpairedへ変更せず、旧call019終端unknown・元費用nullを埋めない。組合せ計数をentropyや情報効果へ読み替えない。

## 公開dataだけからの再描画

v01は元18件同bytes保持。v02は同じfigure_dataでlegend位置だけを改善した別版である。公開data・manifest・同じrendererから新しい出力先へ再描画でき、raw履歴や私有reviewは不要。元監査の再認証ではない。

```sh
python figures_v02/draw_p137_results_20261027_v02.py --redraw \
  --figure-data figures_v02/figure_data.json \
  --original-manifest figures_v02/output_manifest.json \
  --manifest-sha256 9d3721f02b12f696856bb8e078f1fcf650b604c190892a3e3a295193612e6ac0 \
  --output-dir NEW_OUTPUT_DIRECTORY
```

Python 3.10以上とMatplotlibが必要。font/library/date metadataでPNG/SVG/PDFのbytesは変わり得るが、科学データをhashに結ぶ。元出力先は上書きしない。

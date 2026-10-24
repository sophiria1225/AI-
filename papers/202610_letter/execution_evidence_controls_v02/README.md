# 通常設定対照と先行実装を加えた実証稿

[PDF](draft.pdf)／[TeX](draft.tex). 本文４頁＋英文１頁、全５頁を目視確認済み. 和文105字・英文47語、５キーワード、16文献. はみ出し・未定義参照・ページ外描画０. 設定名の段落にunderfull警告２件は残るが、欠落や重なりはない.

P98の全24実行・426生成の対応解析を主軸に、P99の通常auto/required全８条件を加えた. 両設定3/4成功、成功３課題の費用差は各０、CSVは両方未達. 使用量不明１生成を残し、全仕事費用差は未確定とする. 固定版smolagentsの履歴本文と既存ID修正も先行実装として記した. 外部性能追試はしていない.

[反映内容と限界](../../../docs/letter_closed_controls_integration_20261025.md)／[出典](build_manifest.json)／[全頁確認](visual_review.json)／[公開ファイル検証](../../../reports/letter_closed_controls_public_verification_20261025.json)／[追加数値照合](../../../reports/letter_closed_controls_numeric_verification_20261025.json).

P98数値ファイルはbyte単位で保存し、反復間と旧群間の補助照合を紙面から公開資料への参照に回した. [初回組版の不合格記録](../execution_evidence_controls_v01/README.md)を保持し、この版ではURLの改行だけを修正した.

日英題名と教授用あらましは維持. P101途中結果は未使用. 新手法・一般品質維持・全仕事削減は未確立. 著者・公式様式は未確認であり投稿最終版ではない.

公開資料の再照合はリポジトリルートで実行できる. 非公開履歴や評価器を再実行する検証ではない.

```sh
python3.12 -S scripts/verify_public_letter_evidence.py --folder papers/202610_letter/execution_evidence_controls_v02
```

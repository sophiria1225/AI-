# 電子情報通信学会・和文Dレター原稿 v23

ユーザーが題名・著者情報を入力したWord原稿を基準に、冒頭の2段落だけを150字短縮しました。前回のローカル修正版で削った530字のうち380字を戻しています。あらまし120字、題名・著者欄・所属・連絡先、その他の本文、図表、式、実測値・条件・12文献、Word書式は元のユーザー原稿から変更していません。

- [Word原稿・編集用ソース](manuscript.docx) / [参考校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [Excel結果表](results_tables.xlsx) / [図1](figures/control_points.png)
- [一式ZIP](source_bundle.zip)
- [変更内容](REVISION.md) / [段落の差分](revision_changes.json) / [組版条件](FORMAT.md)
- [実測の根拠と記録先](EVIDENCE.md) / [改訂検査](revision_validation.json)

同じLibreOffice校正環境で元原稿と比較すると、はじめにの第1段落は9行から7行、提案手法の比較説明は10行から6行となり、合計6行短くなりました。Microsoft Word本体の行位置は未検証です。ユーザーの「元原稿から6行分だけ減らす」という指定を優先し、校正環境で図前の本文を1頁へ押し込むための追加削減は行っていません。参考校正PDFとTeX版は、それぞれ本文・文献6頁と英文要旨1頁です。

Word版はmanuscript.docxを直接編集します。ユーザーが変更した書式を再生成で失わないよう、旧版のWord生成スクリプトと中間JSONを本版から除いています。main.texは同じ本文と著者情報を持つ別組版用ソースです。WordとTeXの改ページは同一ではなく、編集後の文章同期は自動ではありません。

## 再生成

Wordを編集後、LibreOfficeとPyMuPDFのある環境で参考PDFを生成できます。Microsoft Wordを用いる場合は、WordからPDFを書き出して最終改ページを確認してください。

```sh
python render_word.py --soffice /path/to/soffice --docx manuscript.docx --outdir build/word-proof --mac-font-fallback
```

未作成の出力先へPDF・全頁PNG・描画記録を作ります。MacでMSフォントがない場合の代替指定を明示しています。DOCXのフォント指定と配布済みmanuscript.pdfは自動変更しません。

```sh
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
python create_results_tables.py --data results_data.json --output-dir build/results-tables
python figures/render_control_points.py --output-dir build/architecture
```

TeXは固定ieicej.clsとuplatex等を用います。Excel表と図にはそれぞれXlsxWriter、Matplotlib等が必要です。追加実験や新しいデータの追加は行っていません。過去の実験・原稿は変更していません。

コード公開先は https://github.com/sophiria1225/AI- です。末尾のハイフンまでがリポジトリ名です。本文脚注も同じURLを保持しています。投稿は未実施であり、巻号などテンプレート由来の未確定表示と提出先の頁数条件は提出時に確認する必要があります。

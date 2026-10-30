# 電子情報通信学会・和文Dレター原稿 v25

参考文献が8行はみ出すという指摘に対応し、図1より後の本文4段落から重複する説明を197字削減しました。参考文献そのもの、あらまし、1頁目の説明と図1・3.1の順序、文字サイズ・余白・行間は変更していません。

- [Word原稿・編集用ソース](manuscript.docx) / [参考校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [Excel結果表](results_tables.xlsx) / [図1](figures/control_points.png)
- [一式ZIP](source_bundle.zip)
- [変更内容](REVISION.md) / [段落の差分](revision_changes.json) / [組版条件](FORMAT.md)
- [実測の根拠と記録先](EVIDENCE.md) / [改訂検査](revision_validation.json)

同じLibreOffice校正環境で、変更した4段落は4→3行、8→5行、7→6行、9→7行となり、本文が計7行短くなりました。本文と参考文献は文字サイズ・行高が異なるため、指摘された参考文献8行と本文7行を同じ行数とは扱いません。参考校正PDFは8頁から7頁へ減り、全12文献が本文末尾の6頁目に収まりました。英文要旨は7頁目です。TeX版も7頁から6頁へ減り、本文・文献5頁と英文要旨1頁になりました。

あらまし120字、題名・著者・所属・連絡先、実測値・条件・12文献、図1と結果表は維持しました。終了制御の照合内容と根拠、実験AとBの独立性、課題別の増減、完全一致基準の不成立、事後整理と少数試行という範囲も維持しています。

Word版はmanuscript.docxを直接編集します。main.texは同じ本文と著者情報を持つ別組版用ソースです。WordとTeXの編集後の文章同期は自動ではありません。Microsoft Word本体での改ページは未検証です。参考校正PDFは代替フォントを用いたLibreOffice出力であり、Word本体と同じページ配置を保証しません。

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

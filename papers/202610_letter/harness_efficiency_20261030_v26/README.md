# 電子情報通信学会・和文Dレター原稿 v26

4.2と5.2の末尾を観測した成果で締め、実験A・Bの後へ「6．考察」を追加しました。結果の解釈と適用範囲を考察に整理し、「7．むすび」は成果のまとめに続く今後の発展予定で終えています。

- [Word原稿・編集用ソース](manuscript.docx) / [参考校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [Excel結果表](results_tables.xlsx) / [図1](figures/control_points.png)
- [一式ZIP](source_bundle.zip)
- [変更内容](REVISION.md) / [段落の差分](revision_changes.json) / [組版条件](FORMAT.md)
- [実測の根拠と記録先](EVIDENCE.md) / [改訂検査](revision_validation.json)

あらまし120字、1頁目と図1・3.1の順序、題名・著者情報、実験結果の数値と条件、図表・数式・12文献を維持しています。完全一致基準の不成立、既知課題・単一モデルと量子化設定・少数試行・事後整理という評価範囲は考察へ移しています。未見課題や統計的非劣性などの追加検証は今後の課題として述べ、新しい実験結果として扱っていません。

参考校正PDFは本文・文献6頁と英文要旨1頁、TeX版は本文・文献5頁と英文要旨1頁です。文献のみのはみ出し頁はありません。Microsoft Word本体での最終改ページは未確認です。参考校正PDFは代替フォントを用いたLibreOffice出力であり、Word本体とページ位置が異なる場合があります。

Word版はmanuscript.docxを直接編集します。main.texは同じ本文と著者情報を持つ別組版用ソースです。WordとTeXの編集後の文章同期は自動ではありません。

## 再生成

```sh
python render_word.py --soffice /path/to/soffice --docx manuscript.docx --outdir build/word-proof --mac-font-fallback
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
python create_results_tables.py --data results_data.json --output-dir build/results-tables
python figures/render_control_points.py --output-dir build/architecture
```

Word参考PDFの出力先は未作成のディレクトリを指定します。DOCXのフォント指定と配布PDFは自動変更しません。TeXは固定ieicej.clsとuplatex等、Excel表と図はXlsxWriter・Matplotlib等を用います。

コード公開先は https://github.com/sophiria1225/AI- です。末尾のハイフンまでがリポジトリ名です。投稿は未実施です。巻号などのテンプレート由来の未確定表示と提出先の頁数条件は提出時に確認する必要があります。

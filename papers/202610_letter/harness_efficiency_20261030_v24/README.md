# 電子情報通信学会・和文Dレター原稿 v24

提案手法の概要を図1の前にまとめ、図1・図題の直後から3.1を始める構成へ変更しました。従来の3.1冒頭にあった行動生成・実行・記録と1ターンの説明を、78字に整理して3節概要へ移しています。図を挟んでも自然に読めるよう、3.1冒頭の指示語も調整しました。

- [Word原稿・編集用ソース](manuscript.docx) / [参考校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [Excel結果表](results_tables.xlsx) / [図1](figures/control_points.png)
- [一式ZIP](source_bundle.zip)
- [変更内容](REVISION.md) / [段落の差分](revision_changes.json) / [組版条件](FORMAT.md)
- [実測の根拠と記録先](EVIDENCE.md) / [改訂検査](revision_validation.json)

あらまし120字、題名・著者・所属・連絡先、実測値・条件・12文献、図1の内容と結果表は維持しました。3節概要は78字増え、3.1は冒頭の移動と接続表現の整理で短くなっています。フォント・余白・字間は変更していません。本文の追加・削除はこの段落移動に伴う推敲の範囲です。

TeX版では、1頁目を3節概要までとし、2頁目上端の図1の下に3.1が続くことを確認しました。Word版も文書内の順序を「概要→図1→3.1」としていますが、Microsoft Word本体での改ページは未検証です。参考校正PDFは代替フォントを用いたLibreOffice出力であり、Word本体と同じページ配置を保証しません。参考校正PDFは本文・文献7頁と英文要旨1頁、TeX版は本文・文献6頁と英文要旨1頁です。

Word版はmanuscript.docxを直接編集します。ユーザーが変更した書式を再生成で失わないよう、旧版のWord生成スクリプトと中間JSONは用いません。main.texは同じ本文と著者情報を持つ別組版用ソースです。WordとTeXの編集後の文章同期は自動ではありません。

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

# 電子情報通信学会・和文Dレター原稿 v22

ユーザーの文章案をもとに、接続詞、語順、文の区切り、処理の主体を推敲しました。既存の段落の順序と書式を保ち、Wordの公式テンプレート、図表、数式、実験条件、実測値、文献は維持しています。文章案に含まれる一般化や強調は、既存の結果が示す範囲に合わせて調整しました。

- [Word原稿](manuscript.docx) / [Word校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [編集用Excel：結果表と集計式](results_tables.xlsx)
- [図1：履歴要約方式と終了制御](figures/control_points.png)
- [ソース一式ZIP](source_bundle.zip)
- [変更内容と残る確認事項](REVISION.md) / [組版条件](FORMAT.md)
- [根拠と記録先](EVIDENCE.md) / [追加比較の全12実行](supplemental_results.pdf)
- [改訂検査](revision_validation.json) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

既知4課題で成功を保ち、専用反復方式の総トークン数は専用1回方式より12.07%少なくなりました。この差はCSV処理で生じ、残る3課題は同じ値でした。独立に評価した同じ写真課題の2つのAPI条件では、終了制御を用いた実行で成功を保ち、通常継続より26.00〜30.15%少なくなりました。行動併記方式の課題別の利点と合計での増加も残しています。本文とあらましの言い回しを変更しました。題名・著者欄、図1、図表題、表1・表2、数式、実測値、全実行条件、12文献、Excel表はv21と同じで、新しい実験や再評価は行っていません。

日本語あらましは120字、英文要旨は39語です。Wordは編集可能な2表、1画像、1個のOMML数式を含みます。Excelブックは編集可能な表と集計式を持ち、結果グラフを含みません。表の日本語見出しと元データを保持しています。公式Wordテンプレートの部品、本文8.5 pt・表7 ptを保持しています。LibreOfficeで出力した参考校正PDFは本文・文献6頁と英文1頁、TeX版は本文・文献6頁と英文1頁です。文章量による自然な改ページと、書式設定の変更を区別しています。Microsoft Word本体での改ページと1頁目の不足行の解消は未確認です。参考校正PDFには図前の本文が短く続く頁があり、これを解消するための段落移動や字体・字間・余白の変更は行っていません。初回投稿の頁数条件は提出する原稿で確認し、本文・文献が5頁以上の場合は超過理由書が必要です。

著者・所属・連絡先は未設定です。既知課題と少数の試行を事後に整理した評価であり、未見課題の品質保証や統計的非劣性は示していません。実験Bで要求・応答全文の先頭部分の完全一致が成立しなかった事実も残しています。実験AとBの組合せ効果は測定していません。

## 再生成

Python、python-docx、lxmlと[公式Wordテンプレート](https://www.ieice.org/jpn/shiori/jd/iss_lettertemplete.docx?download=1)を用意します。テンプレート自体は再配布せず、スクリプトで固定SHA-256を照合します。

```sh
python build_word.py --template /path/to/iss_lettertemplete.docx
python render_word.py --soffice /path/to/soffice --outdir build/word-proof --mac-font-fallback
```

第2コマンドはLibreOfficeとPyMuPDFを使い、未作成の出力先へPDF・全頁PNG・描画記録を作ります。MacでMSフォントを持たない場合の代替設定を明示しています。配布済みのmanuscript.pdfは自動上書きしません。TeX版は固定ieicej.clsとuplatex等のある環境で再生成できます。

```sh
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
```

Excel結果表はXlsxWriter、図1はMatplotlibなどを用いて再生成します。Excel表には画像書出し工程がないため、LibreOfficeは不要です。未作成の出力先を指定します。

```sh
python create_results_tables.py --data results_data.json --output-dir build/results-tables
python figures/render_control_points.py --output-dir build/architecture
```

グラフ作成・書出しの旧コマンドは本版では使用しません。Excel編集後に原稿の表を更新する場合は、数値を確認してword_content.jsonとtables.texにも反映し、Word・TeXを再生成します。Excelと原稿の表は自動同期しません。

公開コードのURLは https://github.com/sophiria1225/AI- です。末尾のハイフンはリポジトリ名の一部です。原稿脚注にも同じ全文を表示し、リンク先を設定しています。

ローカルの見本は図注や文章構成の確認に限って参照し、見本の文書、文章、個人情報を本リポジトリや配布ZIPへ含めていません。

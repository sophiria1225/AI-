# 電子情報通信学会・和文Dレター原稿 v21

Wordでの1頁目の文章量を増やすため、提案手法の冒頭へ216字を追加しました。三方式を比較する二つの対応関係、要約機会の上限と候補生成の配置、モデルとハーネスの役割分担を説明しています。既存の文章と3.1節の位置を保持し、公式テンプレートの字体・字間・余白・グリッドは変更していません。

- [Word原稿](manuscript.docx) / [Word校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [編集用Excel：結果表と集計式](results_tables.xlsx)
- [図1：履歴要約方式と終了制御](figures/control_points.png)
- [ソース一式ZIP](source_bundle.zip)
- [変更内容と残る確認事項](REVISION.md) / [組版条件](FORMAT.md)
- [根拠と記録先](EVIDENCE.md) / [追加比較の全12実行](supplemental_results.pdf)
- [改訂検査](revision_validation.json) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

既知4課題で成功を保ち、専用反復方式の総トークン数は専用1回方式より12.07%少なくなりました。この差はCSV処理で生じ、残る3課題は同じ値でした。独立に評価した同じ写真課題の2つのAPI条件では、終了制御を用いた実行で成功を保ち、通常継続より26.00〜30.15%少なくなりました。行動併記方式の課題別の利点と合計での増加も残しています。追加段落以外の本文、図1、図表題、あらまし、表1・表2、実測値、全実行条件、12文献、Excel表はv20と同じで、新しい実験や再評価は行っていません。

日本語あらましは115字、英文要旨は39語です。Wordは編集可能な2表、1画像、1個のOMML数式を含みます。Excelブックは編集可能な表と集計式を持ち、結果グラフを含みません。表の日本語見出しと元データを保持しています。公式Wordテンプレートの部品、本文8.5 pt・表7 ptを保持しています。LibreOfficeで出力した参考校正PDFは本文・文献6頁と英文1頁、TeX版は本文・文献5頁と英文1頁です。Microsoft Word本体では改ページと1頁目の不足行の解消を確認できていません。代替フォントを用いるLibreOfficeでは図前の本文が2頁目へ続くため、Word用の追加を戻したり、既存本文を移動したりしていません。参考校正PDFの頁数をWord本体の頁数と同一視しないでください。初回投稿の頁数条件は使用する提出原稿で確認し、5頁以上の場合は超過理由書が必要です。

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

# 電子情報通信学会・和文Dレター原稿 v20

図1の役割を色で見分けやすくしました。行動生成は淡い青、要約専用の呼出しは淡いオレンジ、ハーネス処理は白とし、黒い枠・文字・矢印を維持しました。円形の繰返し記号と下段の説明を外し、反復する2方式は「要約機会：条件成立時，最大3回」と明記しています。呼出し順序、採否判定の時点、破線のターン境界、実験Bの分岐は維持しています。

- [Word原稿](manuscript.docx) / [Word校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [編集用Excel：結果表と集計式](results_tables.xlsx)
- [図1：履歴要約方式と終了制御](figures/control_points.png)
- [ソース一式ZIP](source_bundle.zip)
- [変更内容と残る確認事項](REVISION.md) / [組版条件](FORMAT.md)
- [根拠と記録先](EVIDENCE.md) / [追加比較の全12実行](supplemental_results.pdf)
- [改訂検査](revision_validation.json) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

既知4課題で成功を保ち、専用反復方式の総トークン数は専用1回方式より12.07%少なくなりました。この差はCSV処理で生じ、残る3課題は同じ値でした。独立に評価した同じ写真課題の2つのAPI条件では、終了制御を用いた実行で成功を保ち、通常継続より26.00〜30.15%少なくなりました。行動併記方式の課題別の利点と合計での増加も残しています。本文、図表題、あらまし、表1・表2、実測値、全実行条件、12文献、Excel表はv19と同じで、新しい実験や再評価は行っていません。

日本語あらましは115字、英文要旨は39語です。Wordは編集可能な2表、1画像、1個のOMML数式を含みます。Excelブックは編集可能な表と集計式を持ち、結果グラフを含みません。表の日本語見出しと元データを保持しています。公式Wordテンプレートの部品、本文8.5 pt・表7 ptを保持しています。Word校正PDFとTeX版はいずれも本文・文献5頁と英文要旨1頁で、初回投稿には超過理由書が必要です。頁数とフォントは組版検査記録にも示し、Microsoft Word・Excel本体での描画とは区別しています。

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

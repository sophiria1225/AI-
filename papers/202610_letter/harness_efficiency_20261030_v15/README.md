# 電子情報通信学会・和文Dレター原稿 v15

方式名を「単回要約」「反復要約」「同時要約」にそろえ、行動を生成して実行結果を履歴へ追加する基本の流れから、各方式の要約手順を説明しました。本文の括弧内の補足は文章へ組み込みました。あらましは119字、英文要旨は43語です。

実験Aの図は、写真操作・精算・返金・CSV処理の4図に分けました。各図は同じ縦軸範囲で3方式を比較し、棒の上にも実測値を表示します。実験Bは独立した図6です。図1は上段の入力履歴更新と下段の終了判断を日本語の見出しで示します。図表のキャプションは番号と短い和文名のみです。

- [編集用Excel：結果表と5点のグラフ](results_charts.xlsx)
- [Word原稿](manuscript.docx) / [Word校正PDF](manuscript.pdf)
- [TeX原稿](main.tex) / [TeX版PDF](manuscript_tex.pdf)
- [ソース一式ZIP](source_bundle.zip)
- [図1：履歴要約と終了制御](figures/control_points.png)
- [図2：写真操作](figures/result_photo.png) / [図3：精算](figures/result_settlement.png) / [図4：返金](figures/result_refund.png) / [図5：CSV処理](figures/result_csv.png)
- [図6：実験Bの終了制御](figures/result_termination.png)
- [追加比較の全12実行](supplemental_results.pdf) / [根拠と記録先](EVIDENCE.md)
- [改訂対応表](revision_validation.json) / [組版条件](FORMAT.md) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

反復要約は既知4課題の成功を保ち、単回要約に比べ4課題合計を12.07%削減しました。同じ写真課題の2つのAPI条件では、完了判定により成功を保ち、26.00〜30.15%削減しました。全実測値・課題数・実行回数・採用回数・モデル条件・12文献はv14と同じです。同時要約の比較結果、要求・応答全文の先頭部分完全一致が不成立だった事実、少数の既知開発実験を事後に整理した範囲も残しています。実験の追加・再評価は行っていません。

Wordは編集可能な2表、6画像、1個のOMML数式を含みます。結果の5グラフはExcelのネイティブグラフとして編集でき、Wordには同じブックからLibreOfficeで出力したPNGを、TeXにはPDFを挿入しています。Microsoft Word・Excel本体の描画との完全一致は確認していません。公式Wordテンプレートの部品、本文8.5pt・表7ptを保持し、字体や字間を縮めて頁数を合わせていません。著者・所属・連絡先は未設定です。

提案の対象は実装・評価した制御構成と終了判断手順です。既存の反復要約を新しい要約アルゴリズムとは扱いません。実験AとBは独立で、組合せ効果は測定していません。図の旧版はv14以前のディレクトリに保存しています。

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

固定した集計データからExcelブックと結果図を作るには、XlsxWriter、LibreOffice、PyMuPDF等を用意し、未作成の出力先を指定します。

```sh
python create_excel_charts.py --data results_data.json --output-dir build/excel-charts --soffice /path/to/soffice
```

Excelで編集して保存したブックを出し直す場合は、保存済みブックを指定します。

```sh
python create_excel_charts.py --workbook results_charts.xlsx --output-dir build/edited-charts --soffice /path/to/soffice
```

グラフのシートは先頭5枚のままにしてください。棒と集計値はセル参照で更新されます。図6の削減率注記は描画互換性のため文字ラベルを使っているので、数値を編集する場合は集計表のD13:E14に合わせて注記も更新してください。出力先にExcelブック・検証情報・figuresが生成されます。採用するPNG/PDFを原稿のfiguresへ反映した後、Word/TeXを再生成します。図1の生成元はfigures/render_control_points.pyです。

ローカルの見本は図注や文章構成の確認に限って参照し、見本の文書、文章、個人情報を本リポジトリや配布ZIPへ含めていません。

最終出力はWord・TeXとも本文と文献が5頁、末尾の英文要旨が1頁である。本文5頁の初回投稿には超過理由書の添付と審議が必要となる。図を課題別に分けた説明版として作成し、文字サイズや字間は縮小していない。

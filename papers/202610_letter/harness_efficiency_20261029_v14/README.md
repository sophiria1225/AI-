# 電子情報通信学会・和文Dレター原稿 v14

[編集用 Excel](results_charts.xlsx) に、実験結果の表と、セル値から更新できる2点のグラフを収録しました。図2はCSV処理とその他3課題、図3は通常継続と完了判定を、青とオレンジで区別します。[Word原稿](manuscript.docx) とPDFには、このExcelブックの同じグラフをLibreOfficeで出力した画像を挿入しました。Excel側は編集可能なネイティブグラフ、Word側はその書出し画像です。

本文・119字のあらまし・43語の英文要旨・図1はv13と同じです。第3章でハーネスの役割を先に説明し、入力を短くする制御と、作業完了後の生成を省く制御を別々に評価しています。図表キャプションは番号と短い和文名のみです。

反復要約は既知4課題の成功を保ち、単回要約に比べ4課題合計を12.07%削減しました。同じ写真課題の2つのAPI条件では、完了判定により成功を保ち、26.00〜30.15%削減しました。全表数値・条件・正式文献12件・図1はv13と同じです。図2と図3のみ、同じ値をExcelグラフとして色付きで描き直しました。Inlineの比較結果、厳密な要求・応答先頭部分一致の不成立、少数の既知開発実験を事後に整理した範囲も本文に残しています。

- [編集用 Excel：実験結果とグラフ](results_charts.xlsx)
- [ソース一式 ZIP](source_bundle.zip)
- [Word 原稿](manuscript.docx) / [Word 校正 PDF](manuscript.pdf)：本文・文献4頁＋英文1頁
- [TeX 原稿](main.tex) / [TeX 版 PDF](manuscript_tex.pdf)：本文・文献4頁＋英文1頁
- [図1：独立な制御（PNG）](figures/control_points.png) / [PDF](figures/control_points.pdf) / [SVG](figures/control_points.svg)
- [図2：実験A（PNG）](figures/result_summary.png) / [PDF](figures/result_summary.pdf) / [SVG](figures/result_summary.svg)
- [図3：実験B（PNG）](figures/result_termination.png) / [PDF](figures/result_termination.pdf) / [SVG](figures/result_termination.svg)
- [追加比較の全12実行](supplemental_results.pdf) / [根拠・採否理由・記録先](EVIDENCE.md)
- [改訂対応表](revision_validation.json) / [組版条件](FORMAT.md) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

Word校正PDF・別組版のTeX版とも本文・文献4頁＋英文1頁です。各出力を実測しており、フォント縮小や字間圧縮で頁数を合わせていません。著者・所属・連絡先は未設定です。公式の投稿条件と確認範囲は [FORMAT.md](FORMAT.md) に示します。

Wordは編集可能な2表・3画像・1個のOMML数式を含みます。図2・図3のグラフ編集は別添のExcelブックで行えます。公式 styles/font/settings/header/footer の部品を保持し、本文8.5 pt、表7 ptを使用します。本文入力は `word_content.json`、対応するTeX表現は `main.tex` と `word_source.tex` です。提案の対象は本稿で実装・評価した制御構成と終了判断手順です。既存のSeparateを新しい要約アルゴリズムとするものではありません。実験AとBは独立で、組合せ効果は測定していません。今回の改稿では実験を追加・再評価していません。

旧結合図・選択用4案は本版へ混在させず、[v08](../harness_efficiency_20261029_v08/README.md) に保存しています。本版で使用する図は上記3点です。

## 再生成

Python、python-docx、lxml と[公式 Word テンプレート](https://www.ieice.org/jpn/shiori/jd/iss_lettertemplete.docx?download=1)を用意します。テンプレート自体は再配布せず、スクリプトで固定SHA-256を照合します。

```sh
python build_word.py --template /path/to/iss_lettertemplete.docx
python render_word.py --soffice /path/to/soffice --outdir build/word-proof --mac-font-fallback
```

第2コマンドはLibreOfficeとPyMuPDFを使い、新しい出力ディレクトリへPDF・全頁PNG・描画記録を作ります。MacでMSフォントを持たない場合の代替設定を明示しており、Microsoft Wordそのものの改ページ一致は確認していません。配布済みの `manuscript.pdf` は自動上書きしません。

TeX版は固定 `ieicej.cls` とuplatex等のある環境で再生成できます。Word校正PDFとは別の組版です。

```sh
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
```

図2・図3はExcelブックのネイティブグラフから出力します。Excelブックの作成にはXlsxWriter、描画にはLibreOffice、PDFと画像の書出しにはPyMuPDF等を使用します。Microsoft Excel本体による描画との完全一致は確認していません。固定した集計データからExcelブックと図を作る場合は、未作成の出力先を指定します。

```sh
python create_excel_charts.py --data results_data.json --output-dir build/excel-charts --soffice /path/to/soffice
```

Excelで保存したブックから図を出し直す場合は、データからの新規生成ではなく、保存済みブックを指定します。

```sh
python create_excel_charts.py --workbook results_charts.xlsx --output-dir build/edited-charts --soffice /path/to/soffice
```

図2・図3のシートは先頭2枚のままにしてください。棒の高さと集計値はセル参照で更新されます。図3の削減率注記は描画互換性のため文字ラベルを使っているので、数値を編集する場合は集計表のD/E列に合わせて注記も更新してください。出力先にExcelブック・検証情報・figuresが生成されます。採用する図2・図3のPNG/PDFを原稿のfiguresへ反映した後、上記のWord/TeX再生成を行えます。図1は従来のままです。

ユーザー提示の原稿は図注の形式と文章構成の確認に限ってローカル参照しました。見本の文書、文章、個人情報を本リポジトリや配布ZIPへ含めていません。

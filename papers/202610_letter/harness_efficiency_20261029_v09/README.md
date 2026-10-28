# 電子情報通信学会・和文Dレター原稿 v09

[編集用 Word](manuscript.docx) は、学会公式の和文論文誌D・レター用 Word テンプレートを用いた改稿です。あらましを108字へ改め、用語・方法の説明・考察を整理しました。図1は独立な二つの制御を示す130 mmの両段図として2頁上端へ置き、実験AとBの結果図はそれぞれ65 mmの片段図2・図3に分けました。式の導入と説明、図表とキャプション、見出しと本文をまとめています。実測値・対照・限界・正式文献12件は保持しています。

- [ソース一式 ZIP](source_bundle.zip)
- [Word 原稿](manuscript.docx) / [Word 校正 PDF](manuscript.pdf)：本文・文献4頁＋英文1頁
- [TeX 原稿](main.tex) / [TeX 版 PDF](manuscript_tex.pdf)：本文・文献5頁＋英文1頁
- [図1：独立な制御（PNG）](figures/control_points.png) / [PDF](figures/control_points.pdf) / [SVG](figures/control_points.svg)
- [図2：実験A（PNG）](figures/result_summary.png) / [PDF](figures/result_summary.pdf) / [SVG](figures/result_summary.svg)
- [図3：実験B（PNG）](figures/result_termination.png) / [PDF](figures/result_termination.pdf) / [SVG](figures/result_termination.svg)
- [追加比較の全12実行](supplemental_results.pdf) / [根拠・採否理由・記録先](EVIDENCE.md)
- [改訂対応表](revision_validation.json) / [組版条件](FORMAT.md) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

頁数はWordとTeXの各出力を実測し、同じ頁数へ縮めていません。著者・所属・連絡先は未設定です。TeX版のように初回投稿が本文5頁以上の場合は、現行しおり2.3に従い超過理由書が必要です。英文要旨はこの頁数から除きます。組版規程と確認範囲は [FORMAT.md](FORMAT.md) に示します。

Wordは編集可能な2表・3画像・1個のOMML数式を含みます。公式 styles/font/settings/header/footer の部品を保持し、本文8.5 pt、表7 ptを使用します。本文入力は `word_content.json`、対応するTeX表現は `main.tex` と `word_source.tex` です。今回の改稿では実験を追加・再評価していません。

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

3図の再生成はMatplotlib・Pillow・CairoSVG・PyMuPDFを用います。出力先は未作成のディレクトリを指定します。Mac以外では `JAPANESE_FONT` に日本語フォントを指定します。PDF/SVG/EPSは日本語字形をベクタ輪郭として保存します。

```sh
python figures/render_figures.py --data results_data.json --output-dir build/regenerated-figures
```

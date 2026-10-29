# 電子情報通信学会・和文Dレター原稿 v13

[編集用 Word](manuscript.docx) は、学会公式の和文論文誌D・レター用 Word テンプレートを用いた原稿です。あらましは119字、意味を合わせた英文は43語です。第3章ではハーネスの役割を先に説明し、「入力履歴を短くする制御」と「作業完了後の生成を省く制御」を、目的・判断材料・処理の順に記述しました。本文の補足ファイルへの誘導を外し、方法・条件・結果を原稿内で追える構成にしています。図表は短い和文の番号と名称のみです。

反復要約は既知4課題の成功を保ち、単回要約に比べ4課題合計を12.07%削減しました。同じ写真課題の2つのAPI条件では、完了判定により成功を保ち、26.00〜30.15%削減しました。全表数値・条件・正式文献12件・図3点の画像はv12と同じです。Inlineの比較結果、厳密な要求・応答先頭部分一致の不成立、少数の既知開発実験を事後に整理した範囲も本文に残しています。

- [ソース一式 ZIP](source_bundle.zip)
- [Word 原稿](manuscript.docx) / [Word 校正 PDF](manuscript.pdf)：本文・文献4頁＋英文1頁
- [TeX 原稿](main.tex) / [TeX 版 PDF](manuscript_tex.pdf)：本文・文献4頁＋英文1頁
- [図1：独立な制御（PNG）](figures/control_points.png) / [PDF](figures/control_points.pdf) / [SVG](figures/control_points.svg)
- [図2：実験A（PNG）](figures/result_summary.png) / [PDF](figures/result_summary.pdf) / [SVG](figures/result_summary.svg)
- [図3：実験B（PNG）](figures/result_termination.png) / [PDF](figures/result_termination.pdf) / [SVG](figures/result_termination.svg)
- [追加比較の全12実行](supplemental_results.pdf) / [根拠・採否理由・記録先](EVIDENCE.md)
- [改訂対応表](revision_validation.json) / [組版条件](FORMAT.md) / [描画検査](word_render_validation.json) / [XML・本文検査](word_validation.json) / [再構築検査](word_rebuild_validation.json)

Word校正PDF・別組版のTeX版とも本文・文献4頁＋英文1頁です。各出力を実測しており、フォント縮小や字間圧縮で頁数を合わせていません。著者・所属・連絡先は未設定です。公式の投稿条件と確認範囲は [FORMAT.md](FORMAT.md) に示します。

Wordは編集可能な2表・3画像・1個のOMML数式を含みます。公式 styles/font/settings/header/footer の部品を保持し、本文8.5 pt、表7 ptを使用します。本文入力は `word_content.json`、対応するTeX表現は `main.tex` と `word_source.tex` です。提案の対象は本稿で実装・評価した制御構成と終了判断手順です。既存のSeparateを新しい要約アルゴリズムとするものではありません。実験AとBは独立で、組合せ効果は測定していません。今回の改稿では実験を追加・再評価していません。

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

ユーザー提示の原稿は図注の形式と文章構成の確認に限ってローカル参照しました。見本の文書、文章、個人情報を本リポジトリや配布ZIPへ含めていません。

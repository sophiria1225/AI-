# 電子情報通信学会・和文Dレター原稿 v07

[編集用 Word](manuscript.docx) は、学会公式の **和文論文誌D・レター用 Word テンプレート**から作り直した原稿です。公式の本文・見出し・文献スタイルと B5 の2段組を継承しています。和文あらましを115字で整理し、図1を日本語で描き直しました。両段図の幅130 mmと実験値・対照条件・12件の参考文献を維持しています。本文・文献4頁＋末尾英文1頁の全5頁を描画し、各頁を確認済みです。著者・所属・連絡先は未設定です。

- [ソース一式 ZIP](source_bundle.zip)
- [Word 原稿](manuscript.docx)
- [Word から出力した校正 PDF](manuscript.pdf)
- [新しい日本語図1（PNG）](figures/control_points.png) / [ベクタ PDF](figures/control_points.pdf) / [SVG](figures/control_points.svg)
- [TeX 原稿](main.tex) / [TeX 版 PDF](manuscript_tex.pdf)（Word とは別の組版）
- [全12条件の補足表](supplemental_results.pdf) / [結果と範囲](EVIDENCE.md)
- [公式テンプレートの来歴](official_template_provenance.json) / [XML・本文検査](word_validation.json) / [全ページ描画検査](word_render_validation.json) / [Git外再構築検査](word_rebuild_validation.json) / [組版条件](FORMAT.md)

日本語図の4候補は全案を別添し、本文への採用は未選択です。[一覧](architecture_candidates/contact_sheet.png)、[案1](architecture_candidates/candidate_01_two_studies.png)、[案2](architecture_candidates/candidate_02_summary_comparison.png)、[案3](architecture_candidates/candidate_03_execution_boundary.png)、[案4](architecture_candidates/candidate_04_single_column.png)。v07 の図1はこれらとは別に新しく描き直した日本語図を採用し、図2は従来のままです。

Word の再生成には Python、python-docx、lxml と、[学会公式 Word テンプレート](https://www.ieice.org/jpn/shiori/jd/iss_lettertemplete.docx?download=1)が必要です。テンプレート自体は再配布せず、取得したファイルの SHA-256 をスクリプトで照合します。

```sh
python build_word.py --template /path/to/iss_lettertemplete.docx
```

`word_content.json` は v07 の本文入力です。v06 の科学的内容・編集可能な表・数式を継承し、あらまし・図1とその説明を更新しています。`build_word.py` は公式テンプレートを読み込み、内容を配置し、公式 styles/font/settings/header/footer の bytes 一致と科学的な本文・表の保持を確認します。

TeX 版は `TEX_BIN`（uplatex 等のあるディレクトリ）と `IEICEJ_DIR`（固定 ieicej.cls のあるディレクトリ）を指定して `bash build.sh` で再生成できます。出力は `manuscript_tex.pdf` であり、Word 校正 PDF の `manuscript.pdf` を上書きしません。

Word 校正 PDF を再生成する場合は、LibreOffice と PyMuPDF を用意して次を実行します。Mac で公式 MS フォントを持たない場合に限り、明示的な代替フォント設定を加えます。

```sh
python render_word.py --soffice /path/to/soffice --outdir build/word-proof --mac-font-fallback
```

このコマンドは新しい出力ディレクトリへ PDF・全頁 PNG・描画記録を作り、配布済みの校正 PDF を自動上書きしません。フォント代替と Microsoft Word での再表示に関する範囲は `FORMAT.md` に記載しています。

図1は `python figures/render_control_points.py --output-dir figures --variant split_documents --update-manifest` で再生成できます。Matplotlib・Pillow・CairoSVG・PyMuPDFを使用し、Mac以外では `JAPANESE_FONT` に日本語フォントを指定します。PDF/EPSは字形をベクタの輪郭として保存し、埋込みフォントによる日本語の欠落を防ぎます。

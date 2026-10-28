# 和文論文誌Dレターの組版

投稿先の第一候補は電子情報通信学会・和文論文誌Dのレター（研究速報）である。このフォルダは閉鎖済みP143の全8条件を反映したv02校正稿であり、投稿済み・投稿準備完了を意味しない。著者、所属、会員種別、住所は確認済み情報だけを記入する。

## 現在のクラスと実行方法

既存の `ieicej.cls` は公開ミラーの固定commit `09affdda87853ac52313ec92ae90e0f14a43a20d` から取得したもので、クラス宣言は **2023/11/21 v3.4a**。SHA-256は `36b2731a97ecbb86f02b1aff50cf38d10ae57c6f1a6448f5fc9956226412a56a`。クラスを改変・再配布せず、研究用 `.runtime/letter_tex/mirror_09affdda/` の外部ファイルを参照する。

[現公式配布一覧](https://www.ieice.org/ftp/tex/ieicej/LaTeX2e/)は [ieicej3.4b.zip](https://www.ieice.org/ftp/tex/ieicej/LaTeX2e/ieicej3.4b.zip)（2026-01-19）を掲示している。2026-10-28の通常HTTPS取得はHTTP403で、現版との同一性は未確認である。今回のPDFを「現公式クラス準拠確認済み」とは扱わない。

リポジトリ内の既存TinyTeX v2026.10と、日本語・フォント追加済み環境を使う。既定の実行ファイルは `.runtime/letter_tex/v2026.10/portable/TinyTeX/bin/universal-darwin/`。システムのPATHは変更しない。

```sh
cd papers/202610_letter/threshold_object_20261028_v02
bash build.sh
```

`main.tex` から `build/main.pdf` を生成する。処理は、既存 `figures/*.pdf` の寸法を `extractbb -x -O` で同名 `.xbb` へ保存した後、`uplatex` → 必要な場合だけ `upbibtex` → `uplatex` 2回 → `dvipdfmx`。各ログと依存入力の `.fls` を `build/` に残す。shell escapeは無効。別名の入力・出力は `bash build.sh manuscript.tex build-v02` と指定できる。`TEX_BIN`、`IEICEJ_DIR`、`IEICEJ_SHA256` は検証済み環境への明示切替用であり、変更だけで公式認証を意味しない。

2026-10-28の支援作業で、日本語・数式・表・図・文献参照だけの合成文書をこの経路で組版した。本文1頁＋末尾英文1頁の2頁を目視し、全フォント埋込み、未解決引用・参照とoverfull/underfullがないことを確認した。仮著者名に空白がない旨のclass warningのみ残った。これは実原稿の頁数・文献内容の検証ではない。

クラスはpLaTeX2e用でupTeX判別を備え、同梱sampleに従う次の設定でupLaTeXが利用できる。本文の文字サイズ、行間、段幅、クラスは変更しない。

```tex
\documentclass[letter]{ieicej}
\usepackage[dvipdfmx]{graphicx,xcolor}
\usepackage[fleqn]{amsmath}
\usepackage{newtxtext}
\usepackage[varg]{newtxmath}
\typeofletter{研究速報}
```

sampleのレター順序は `\begin{document}`、`\maketitle`、和文abstract/keyword、eabstract/ekeyword、本文。英文はクラスが末尾に配置する。`graphicx`、`xcolor`、`amsmath`、`newtxtext`、`newtxmath`、`booktabs`、`url` は現環境で利用可能。

## 文献とページ確認

同梱sampleのBibTeX指定は `sieicej` だが、その `.bst` は取得済みミラーにも現TeX環境にもない。確実な経路は、全著者・年月・番号引用を整えた `thebibliography` を本文または `\input` する方法。`unsrt.bst` は利用できるが、和文Dの文献書式へ適合したものとは扱わない。不足styleの自動取得は行わない。

[和文D規程2.1–2.6](https://www.ieice.org/jpn/shiori/iss_2.html)では、標準は2頁、初回5頁以上は超過理由書が必要。本稿は本文・図表・文献を合わせて2段組4頁を目標とし、末尾の英文abstract（50語以内）と英訳keywordsは別に数える。和文あらましは120字以内、和文keywordsは4～5語。レターでは著者紹介・写真は不要。

図表は和英captionを備え、仕上がり片段6.5cm・両段13cm、文字は7ptを目安に判読可能にする。[TeX原稿規程](https://www.ieice.org/jpn/shiori/iss_3.html)はUTF-8、最終線幅0.1mm以上、表をTeXで作成すること、クラス・行間等を変えないことを求める。正式電子原稿では外部図のEPS提出規程も確認する。PDF生成だけで完了とせず、本文/英文の頁数、全図表、引用・参照、フォント埋込み、はみ出しを目視とログで確認する。

## 最新の公式配布確認

2026-10-28 09:34頃、公式一覧にv3.4bが掲載されていることを再確認した。通常のurllibとcurlによるarchive取得はいずれもHTTP403で、取得archive bytesは0。root確認記録のSHA-256は `f8b6e7b13a01512ceaec9ea5108837db74a3511f2416deb030784c9674f0e57a`。したがってv3.4a固定ミラーでの校正と、公式最新版の未照合を区別する。最終PDFは本文・図表・文献4頁＋末尾英文1頁。和文あらまし104字、英文43語（空白区切り。ハイフン等を分割する保守計数48語）、keywordsは各5件。全頁目視とログで引用・参照の未解決、overfull/underfullがないことを確認した。著者名仮欄に空白がない旨のclass warningのみ残る。全フォント埋込み・図130mm幅・図内7pt以上を確認し、最終ファイルhashは別の検証記録へ束縛する。

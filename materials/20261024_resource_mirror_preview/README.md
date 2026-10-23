# 資源別統合稿のミラークラスによる組版予行

2026-10-24。[予行PDF](preview.pdf)／[予行TeX](preview.tex)／[出典と表示検査](../../reports/resource_ieice_mirror_preview_20261024.json)。[資源別統合稿](../../papers/202610_letter/resource_measurement/README.md)の本文・全件表・文献・あらましを変更せず、確認済みミラーの`letter`形式で組版した。

本文・文献４頁＋英文末尾１頁を全５頁目視確認。Overfull、Underfull、頁外文字、未定義引用・参照０。和文115字、英文47語、日英各５キーワードを保持し、英文要旨とキーワードはクラスの末尾出力を使用した。PDFの先頭に「組版予行・未投稿」と表示し、著者は未設定としている。

## 配布物について確認できている範囲

[公式FAQ](https://www.ieice.org/jpn_r/shiori/faq_transactions.html)は引き続き[和文LaTeX配布先](https://www.ieice.org/ftp/tex/ieicej/)を案内している。今回の検索と公式ページの確認では、別の現行公式配布経路を見つけていない。以前失敗したZIPの再取得は０回である。[確認記録](../../reports/ieice_distribution_review_20261024.json)。

使用したのは以前確認した[公開ミラー固定版](https://github.com/mar-tusita/ieicej-platex/tree/09affdda87853ac52313ec92ae90e0f14a43a20d)。クラス宣言は`2023/11/21 v3.4a`、配布説明はv3.4bで、名称だけで公式ファイルとの一致・不一致を断定しない。公式ZIPとのバイト同一性は未確認のままである。[従来の照合](../../reports/ieice_mirror_check_20261023.json)にある４ファイルを再度hash照合した。

このPDFは当該ミラーと未設定著者欄での組版結果であり、現行公式様式や実著者情報での最終ページ数を保証しない。元のjsarticle稿と全数値資料を保持し、クラス本体はGitへ転載していない。

## 再生成と記録

[生成器](../../scripts/build_resource_mirror_preview.py)は確認済み原稿の99出典、生成表、PDF、合意した日英題名とミラー４ファイルを照合する。原稿内の４つの数値表を変更せず局所出力先へ複製し、shell escapeを無効化、TeXのファイル入出力を`p`へ制限した。読み込んだTeX配布入力74件と実行器のhashを記録する。既存出力先は上書きしない。

```sh
python3.12 scripts/build_resource_mirror_preview.py --mirror /path/to/checked-mirror --tex-bin /path/to/TinyTeX/bin --output /tmp/resource-letter-preview
```

追加モデル生成・計数・API・評価は０。P82は固定条件で実行中、P84は未開始。教授用456字あらましと題名、旧稿は変更していない。著者・所属・順序、公式様式確認、採録に足る中心貢献は未完了である。

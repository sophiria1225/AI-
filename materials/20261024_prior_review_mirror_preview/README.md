# 14文献の資源別稿をミラークラスで確認

2026-10-24。[予行PDF](preview.pdf)／[予行TeX](preview.tex)／[出典と表示検査](../../reports/prior_review_mirror_preview_20261024.json)。現在の閉じた[資源別・先行研究改訂稿](../../papers/202610_letter/resource_prior_review/README.md)を、確認済みミラーのletter形式で組版した。本文・全４数値入力・文献14件・日英のあらましを変更していない。

本文と文献は４頁、英文末尾は１頁で、全５頁を画像化して目視した。Overfull、Underfull、頁外文字、未定義引用・参照は０。和文115字、英文47語、日英各５キーワードを保持する。先頭の「組版予行・未投稿」と著者の未設定表示も確認した。第４頁は文献の続きであり、新しい実験結果の頁ではない。

使用した[公開ミラー固定版](https://github.com/mar-tusita/ieicej-platex/tree/09affdda87853ac52313ec92ae90e0f14a43a20d)は、以前の[４ファイル照合](../../reports/ieice_mirror_check_20261023.json)と同じhashである。現行公式ZIPとのバイト同一性は未確認。公式ZIPの再取得は行っていない。実著者・所属・順序を入れた最終頁数、公式様式、投稿可能性の確認とは区別する。

## 再生成

[原稿選択用処理](../../scripts/build_bound_mirror_preview.py)は、目視済みPDFと出典を持つ別稿だけを選び、[既存のミラー組版処理](../../scripts/build_resource_mirror_preview.py)を変更せず使う。元稿の111出典、生成表、PDFとミラーを照合し、本文・入力表をそのままコピーする。全数値を変えないことを別途照合した。shell escapeは無効、TeXのファイル入出力設定はpである。

```sh
python scripts/build_bound_mirror_preview.py \
  --folder resource_prior_review \
  --mirror /path/to/checked-mirror \
  --tex-bin /path/to/TinyTeX/bin \
  --output /path/to/fresh/private/preview
```

将来のclosed_control_integration稿にも同じ入口を用意したが、準備状態ではPDF・目視済み出典がないため実行しない。今回の確認はP80/P81/P83の閉じた稿だけで、進行中P82や未実行P84の結果を代入していない。新しいモデル生成・計数・API・評価は０。以前の11文献稿の[組版予行](../20261024_resource_mirror_preview/README.md)も保持する。

# 和文Dレター校正稿とTeXソース

初稿は [manuscript.pdf](manuscript.pdf)、編集用一式は [source_bundle.zip](source_bundle.zip)。`main.tex` が本文、`results_p141.tex` が最終診断の結果、`figures/` が図と対応する出典情報である。ソースZIPでは、このフォルダの階層を保って展開する。`build.sh` はPDFを再生成するスクリプト、`FORMAT.md` は書式・環境・確認上の制約を説明する。

電子情報通信学会・和文論文誌Dのレターに向けた**校正稿**であり、投稿済み・投稿準備完了ではない。著者・所属等は未確認のため仮欄を残す。本文・図表・文献4頁と末尾英文1頁を区別する。現PDFは既存 `ieicej` v3.4a ミラーによる組版で、[現公式v3.4b](https://www.ieice.org/ftp/tex/ieicej/LaTeX2e/ieicej3.4b.zip)との一致は未確認（2026-10-28取得HTTP403）。クラス自体はソースZIPに再配布しない。

実験はユーザーの最終指示に従い、2026-10-28 03:36 JSTに閉鎖したP141を終了点とした。新しいモデル実験は追加しない。P141は単一の既知課題で、TRとTDOが成功し、TDOは2,807トークン（0.843987%）少なかった。EDOは失敗し使用量不明1件が残った。一般的な品質維持や既存手法への優越性、採択を保証する結果とは扱わない。

本文に用いた根拠は [EVIDENCE.md](EVIDENCE.md) にまとめた。参考文献は7件で、6件は正式な会議録、1件はプレプリントと明記した。`source_manifest.json` は配布ファイルのSHA-256、`typesetting_review.json` と `scientific_review.json` は初稿の確認記録である。

## ソースZIPからのビルド

upLaTeX、upBibTeX、dvipdfmx、extractbbを含むTeX環境と、検証済み `ieicej.cls` を別途用意する。必要packageとクラスのSHA-256は [FORMAT.md](FORMAT.md) に記載する。Gitリポジトリの外でも、展開先で次のように実行できる。

```sh
TEX_BIN=/path/to/tex/bin \
IEICEJ_DIR=/path/to/directory/containing/ieicej.cls \
bash build.sh
```

既定では記載のv3.4aクラスSHAを検査する。別のクラスを使う場合は、その出所と内容を検証した上で `IEICEJ_SHA256` も明示する。環境変数の指定だけで公式適合を認証するものではない。クラス・文字サイズ・行間を変更しない。

出力は `build/main.pdf`、組版ログは `build/` に保存する。PDF図の寸法情報 `.xbb` を事前生成し、TeXのshell escapeは無効にする。再ビルドは同じ出力を更新するため、以前のPDFが必要なら別名で保存するか `bash build.sh main.tex build-v02` を使う。実行時の文献ファイルもZIPに含め、配布時には全頁の図表、引用、文字、頁数を確認する。

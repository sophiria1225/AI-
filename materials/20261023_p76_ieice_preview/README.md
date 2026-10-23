# P76反映後のレタークラス組版予行

[予行PDF](AI_harness_P76_ieice_preview_20261023.pdf)に閉じたP76全８条件を含めた。本文・文献４ページ＋英文末尾１ページ、和文116字・英文46語、日英４キーワード・全14文献。全５ページを目視し、ページ外文字・overfull/underfull・未解決引用／参照は０だった。

入手済みミラーのieicej v3.4aを使用した。現行公式配布物との一致は未確認、著者は未設定で、先頭に「組版予行・未投稿」と記す。投稿可能な完成版ではない。[主原稿](../../papers/202610_letter/candidate_cost_completion.pdf)と[P75時点の予行](../20261023_ieice_mirror_preview/README.md)を別に保持する。

[出典・全TeX依存関係・描画記録](../../reports/P76_ieice_mirror_preview.json)／[変換後TeX](preview.tex)／[P76の全結果](../../docs/P76_findings.md)。TeXはリポジトリの本文部品を参照し、クラス自体は転載しない。新しいモデル生成・環境API・評価は０。

PDF SHA-256：`5d09dae3e40633d1d825e4e403e0088aa77c2a46f1868e8ae6e9c3790fe3b3fb`。元の主PDF SHA-256：`9acf95889a07911d1a9751312e181efc26eccb28469aa7a2e6a60b72a2e1df5d`。

再生成は報告環境で `scripts/build_ieice_mirror_preview.py --mirror <検査済みミラー> --tex-bin <uplatexとdvipdfmxのディレクトリ> --output <未作成の出力先>`。以前の予行を上書きしない。

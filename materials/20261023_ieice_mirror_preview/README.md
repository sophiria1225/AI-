# レタークラスによる組版予行

[予行PDF](AI_harness_ieice_mirror_preview_20261023.pdf)は、入手済み公開ミラーの `ieicej` v3.4aを用いた本文４ページ＋英文末尾１ページ。全５ページを目視確認し、はみ出し・overfull/underfull・未解決引用／参照は０だった。先頭に「組版予行・未投稿」、著者欄に未設定を明記した。

最新版の公式配布物との一致は未確認であり、公式様式の確認完了や投稿可能な原稿とは扱わない。[現在の主PDF](../../papers/202610_letter/candidate_cost_completion.pdf)は別に保持する。今回の予行内容はP75の履歴条件までで、実行中のP76の結果は含めていない。

[変換後TeX](preview.tex)／[出典・依存関係・描画記録](../../reports/ieice_mirror_preview_20261023.json)／[判断の説明](../../docs/ieice_mirror_preview_20261023.md)。TeXはリポジトリの各本文部品を参照する。クラス自体は転載していない。

PDF SHA-256：`762debebf3de6f9bd80a31335b6a5dd96a8cd6b01bb30da8b56804fe4a5c7da2`。

再生成は報告環境で `scripts/build_ieice_mirror_preview.py --mirror <検査済みミラーのローカルディレクトリ> --tex-bin <uplatexとdvipdfmxのディレクトリ> --output <未作成の出力先>`。元入力・クラス・原稿出典を照合し、過去の予行ディレクトリは上書きしない。新しいモデル生成・環境API・評価は０。

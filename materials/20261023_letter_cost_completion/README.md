# 10月23日：費用と終了手続きに絞った検討原稿

- [本文・文献４ページ＋英文末尾１ページのPDF](../../papers/202610_letter/candidate_cost_completion.pdf)
- [TeX本文](../../papers/202610_letter/candidate_cost_completion.tex)
- [和文あらまし115字](../../papers/202610_letter/cost_completion_abstract_ja.txt)／[英文49語](../../papers/202610_letter/cost_completion_abstract_en.txt)
- [主張・根拠・先行研究との差](../../docs/letter_claim_scope_20261023.md)
- [出典と数値](../../papers/202610_letter/cost_completion_source_map.json)／[描画記録](../../papers/202610_letter/cost_completion_layout.json)

P55/P71の全24表示条件と、P56の４ケース＋P72の14ケースの終了診断を別表へ載せた。P72では全未完了７状態のうち写真Dだけが通知で未達→成功、精算・書出しの６状態は未達。作業保存状態は全14件で不変だった。元の成否と不明費用は保持し、診断を自律実行の成功率へ加えない。P66/P68の通常終了制御は別条件として区別する。

全５ページを目視確認。はみ出し・未解決引用／参照０、underfull警告９件。本文は汎用jsarticleの自然改頁４ページ、英文要旨と英訳キーワードのみ末尾へ分けた。日英４キーワード、全13文献の全著者表記を反映。公式様式・著者情報・独自の中心貢献・実証レターの科学的十分性は未確定。

PDF SHA-256：`30d2d04e31f5337770802a0b71810a248eb4f393b549739127f9d27b432bdb95`。[P71の６枚資料と全24条件CSV](../20261023_p71/README.md)／[P72の５枚資料と全14ケースCSV](../20261023_p72/README.md)。

再描画は報告環境で `scripts/build_public_completion_paper.py --tex-bin <uplatexとdvipdfmxのディレクトリ>`。新しいモデル生成・環境API・評価は０で、根拠や文献のハッシュが変われば停止する。[P71反映前のPDF等](../../papers/202610_letter/archive_before_P71_20261023/README.md)と従来の組版処理を保持した。10月31日投稿の目標を維持する。

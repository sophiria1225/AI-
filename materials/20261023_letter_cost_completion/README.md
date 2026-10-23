# 10月23日：P78反映前の検討原稿

このページはP76までの原稿の保存案内。[P78を含む新しい原稿資料](../20261023_letter_api_errors/README.md)へ更新済み。以下の字数・ハッシュは保存版に対応する。

- [本文・文献４ページ＋英文末尾１ページのPDF](../../papers/202610_letter/archive_before_P78_20261023/candidate_cost_completion.pdf)
- [TeX本文](../../papers/202610_letter/archive_before_P78_20261023/candidate_cost_completion.tex)
- [和文あらまし116字](../../papers/202610_letter/archive_before_P78_20261023/cost_completion_abstract_ja.txt)／[英文46語](../../papers/202610_letter/archive_before_P78_20261023/cost_completion_abstract_en.txt)
- [主張・根拠・先行研究との差](../../docs/letter_claim_scope_20261023.md)
- [出典と数値](../../papers/202610_letter/archive_before_P78_20261023/cost_completion_source_map.json)／[描画記録](../../papers/202610_letter/archive_before_P78_20261023/cost_completion_layout.json)

P55/P71の全24表示条件と、P56の４ケース＋P72の14ケースの終了診断を別表へ載せた。P72では全未完了７状態のうち写真Dだけが通知で未達→成功、精算・書出しの６状態は未達。作業保存状態は全14件で不変だった。元の成否と不明費用は保持し、診断を自律実行の成功率へ加えない。P66/P68の通常終了制御は別条件として区別する。

全５ページを目視確認。はみ出し・未解決引用／参照０、underfull警告９件。本文は汎用jsarticleの自然改頁４ページ、英文要旨と英訳キーワードのみ末尾へ分けた。日英４キーワード、全14文献の全著者表記を反映。公式様式・著者情報・独自の中心貢献・実証レターの科学的十分性は未確定。

P73の全33対の再構成入力診断と、P75で確認した推論履歴の条件を追記済み。全表示の対照も返却された推論を再投入していない。P76の全８保持条件も別表へ追加した。両方2/4成功、写真−38,570・精算+3,444・返金+2,281 token、書出しは両未達・不明各１生成で、全体採用基準は未達。元の成否・不明使用量は保持する。

PDF SHA-256：`9acf95889a07911d1a9751312e181efc26eccb28469aa7a2e6a60b72a2e1df5d`。[P71の６枚資料と全24条件CSV](../20261023_p71/README.md)／[P72の５枚資料と全14ケースCSV](../20261023_p72/README.md)／[P73の５枚資料と全33対CSV](../20261023_p73/README.md)／[P75の４枚資料と全105回CSV](../20261023_p75/README.md)。

再描画は報告環境で `scripts/build_reasoning_comparison_paper.py --tex-bin <uplatexとdvipdfmxのディレクトリ>`。新しいモデル生成・環境API・評価は０で、根拠や文献のハッシュが変われば停止する。[P71反映前のPDF等](../../papers/202610_letter/archive_before_P71_20261023/README.md)と従来の組版処理を保持した。10月31日投稿の目標を維持する。

[P76の５枚資料と全８条件CSV](../20261023_p76/README.md)／[P76を含むミラー組版予行](../20261023_p76_ieice_preview/README.md)。

# P78の全失敗通知条件を含む検討原稿

[原稿PDF](AI_harness_letter_api_errors_20261023.pdf)／[TeX本文](candidate_cost_completion.tex)／[現行原稿の案内](../../papers/202610_letter/README.md)／[主張と根拠](../../docs/letter_claim_scope_20261023.md)。この資料は組版完了時の保存版であり、TeXの参照先はリポジトリ直下を基準とする。

題名は「状態保持型LLMエージェントにおける情報保持と実行制御の評価」、英題は「Evaluating Information Retention and Execution Control in Stateful LLM Agents」。本文と文献４ページ、末尾英文１ページ。和文115字・英文45語、日英５キーワード、全14文献の著者を省略せず記載する。教授用456字あらましは別の仮案として保持した。

P78の８条件は両方式3/4成功、全使用量既知で、例外通知側が120,991 token多く事前採用基準に未達だった。返金は実例外０、書出しは例外前に入力と公開行動が分かれたため、差を通知方法だけの効果とはしない。参照IDをそろえた事後照合で残時間通知に１秒の差があったことと、その差の因果効果は区別する。

全24表示条件、全18終了診断、別条件の通常終了制御、P76の全８推論保持条件を残した。P78を過去比較の同時対照や独立した追加課題とは扱わない。新手法の中核、一般的な品質維持、採録に足る中心貢献は未確立である。

最終版の全５ページを目視し、表４の見出しと表を同じ段にまとめた。はみ出し・未解決引用／参照０、underfull警告９件。初期４回の本文５ページによる停止と、５回目の表見出しの分離も[組版記録](../../reports/P78_manuscript_integration_20261023.json)へ保存する。文字を小さくする変更、文献削除、本文の強制改頁は行っていない。

PDF SHA-256：`caf2465dd300a7c33e9310d4bac0fece8c40e8116ff13a40704b4fc38a1109b9`。[出典](cost_completion_source_map.json)／[描画記録](cost_completion_layout.json)／[P78全件の実験資料](../20261023_p78/README.md)／[反映前の原稿](../../papers/202610_letter/archive_before_P78_20261023/README.md)。

再生成は報告環境で `scripts/build_api_error_paper.py --tex-bin <uplatexとdvipdfmxのディレクトリ>`。生成器が元の結果・描画源と閉じたP78の33ソースを照合する。原稿整備による追加モデル生成・環境API・評価・再tokenizeは０。汎用jsarticleの検討版で、現行公式クラスの確認と著者情報は未完了、投稿可能な最終版ではない。

# 10月31日投稿用原稿の現在地

2026年10月23日。本文・文献４ページと末尾英文１ページの検討原稿を整えた。採録に足る中心貢献・公式様式・著者情報は未確定。必要情報と最終品質を守り、仕事全体費用を減らす最終目標を維持する。

[現在のPDF](candidate_cost_completion.pdf)／[TeX](candidate_cost_completion.tex)／[主張・根拠・限界](../../docs/letter_claim_scope_20261023.md)／[説明資料](../../materials/20261023_letter_cost_completion/README.md)。

P55/P71の全24表示条件を本文へ載せ、P56の４ケースとP72の14ケースは終了診断の別表へまとめた。P72では全未完了７状態のうち写真Dだけが通知１回で未達→成功、他６状態は未達。P66/P68の通常終了制御は別条件として保持する。両接続の詳細省略は既知費用だけでも全表示を上回った。同じ既知４課題・各条件１回で、新手法や一般品質維持の実証ではない。

[P73の事後入力診断](../../docs/P73_findings.md)を通常終了制御の節へ追記。元batchの停止を保持し、全33対の再構成文章・全token列・生成制約の一致と追加処理費用を明示した。[反映前の原稿](archive_before_P73_20261023/README.md)を保持する。

和文116字・英文46語、日英４キーワード。全14引用を全著者表記へ整備した。全５頁目視、はみ出し・未解決引用／参照０、underfull警告９件。自然改頁の汎用jsarticleで、英文添付だけを別ページへ置く。ミラークラスの予行は本文４ページを確認したが、現行公式配布物との一致は未確認。

[数値・出典](cost_completion_source_map.json)／[組版点検](cost_completion_layout.json)／[日英メタデータ](submission_metadata.json)／[文献照合](../../reports/letter_bibliography_ieice_style_20261023.json)／[機械可読な現状](current_status.json)。旧来の著者省略を直し、CaveAgent v4の24名も全て残した。書誌確認と科学的主張の検証は分ける。

再生成は報告環境で `scripts/build_public_display_paper_tables.py`、続いて `scripts/build_reasoning_comparison_paper.py --tex-bin <uplatexとdvipdfmxのディレクトリ>`。閉じた根拠が変われば停止し、PDFが変われば再度目視する。原稿生成はモデル・模擬環境・評価器を呼ばない。

[P71反映前の原稿・要旨・出典](archive_before_P71_20261023/README.md)を保持した。`candidate_execution_state`、`candidate_inventory_visibility`、`candidate_inventory_terminal_scope`や`body.tex`は過去案で、現在の投稿候補ではない。[P72反映前の原稿](archive_before_P72_20261023/README.md)も保持した。元P55/P56/P71の成否や欠測をP72で上書きしない。次の作業は[優先順位](../../docs/next_actions.md)に従う。

P75の履歴条件を方法節へ明記した。Fを含む全表示条件で返却推論を再投入していないため、推論保持を含む通常対照へ一般化しない。本文４頁＋英文末尾１頁を再組版し、全５頁を目視確認。P76の閉じた全８条件を別表へ含めた。両方2/4成功、写真の減少と精算・返金の増加、書出しの両未達・不明２生成を残す。採用基準は未達。[P76反映範囲](../../docs/P76_manuscript_integration.md)／[反映前の原稿](archive_before_P76_20261023/README.md)。

[入手済みミラーによる組版予行](../../materials/20261023_p76_ieice_preview/README.md)も本文４頁＋英文末尾１頁、全５頁目視済み。最新版の公式配布物との一致と実著者欄は未確認であり、現在の主PDFとは別の予行版として保存する。

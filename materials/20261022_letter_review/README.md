# 投稿の問いを絞るための検討用原稿

[４ページPDF](../../papers/202610_letter/candidate_execution_state.pdf)／[TeX](../../papers/202610_letter/candidate_execution_state.tex)／[出典・数値対応](../../papers/202610_letter/evidence_draft_source_map.json)／[描画確認](../../papers/202610_letter/evidence_draft_layout.json)。

目的、近接研究、実行状態と表示の区別、P33・P47の全予定条件、P49・P50の修復範囲、投稿の中心に必要な追加比較をつないだ。７つの監査済み集計から表を生成し、未評価・未実行を残している。初回の表題と表の分離を修正し、最終４ページを描画・目視確認した。ページ外の文字ブロック０、TeX警告０。

構成を検討するために節・段の境界で改頁した４ページであり、汎用jsarticleを使用している。公式IEICE様式で４ページに収まったという確認ではない。著者情報は未設定。研究上の中心的な貢献は未確定で、投稿可能な完成原稿として扱わない。

日本語あらまし案75字、英語案43語を別ファイルへ保存した。旧P16案は履歴として保持している。新しい案も主張・主要比較の確定後に書き直す。

[P51の測定補足](measurement_addendum.md)を追加。完了した使用量と途中の下限を分ける合成３生成の校正で、PDFの主結果や新方式の検証ではない。

表の再生成は `python scripts/build_letter_evidence_tables.py`。組版はリポジトリのルートから `uplatex`（shell escapeなし）を２回実行し、`dvipdfmx`で変換する。TinyTeXと汎用クラスの既存環境を使用した。原記録・モデル生成・環境APIを変更する処理は含まない。

# 公開レビューの修正履歴

実験・閉鎖監査・図v01は変更していない。公開独立レビュー初回は4,349項目のうち4,348がPASSで、`author_redraw_manifest`だけを拒否した。原因は検査側がPNG一致の辞書を整数2と比較したschema誤りだった。実物は2つのPNG名をkeyとして各値Trueを持つ辞書であり、元data/PNGのhash不一致ではない。

初回FAILED JSONを保存し、検査を「2keysすべてTrue」へ修正した別v02へ分離する。元実験、元producer監査、元独立閉鎖review、元rendererは再実行しない。初回JSONの包括的な`original_figures_and_prior_reviews_byte_identical=false`も、当該検査の失敗を含めた初回判定として保持し、元artifactの変化とは解釈しない。

[初回検査](../../reports/P132_publication_review_initial_schema_failure_20261027.json)／[修正版検査](../../reports/P132_publication_independent_review_20261027.json)。原稿や課題成否の修正ではない。

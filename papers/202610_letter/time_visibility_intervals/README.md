# 欠測の条件付き費用区間を加えた検討用原稿

2026-10-24。[PDF](draft.pdf)は本文・文献４頁＋英文１頁。全５頁を確認し、はみ出し、Underfull警告、未定義引用・参照は０。全24条件の元の数値行と不明使用量２生成を保持している。

[同一seed反復稿](../time_visibility_repetitions/README.md)へ、全429生成の補助計数に基づく費用区間と、成功・失敗した課題の費用内訳を追加した。過去のP80下限だけの説明は、新しい区間の節へまとめた。成功部分の397,675 token減を失敗部分の372,927〜378,621増がほぼ相殺すること、反復ごとの方向が増加・増加・減少であることを明記した。合計の条件付き約0.79〜1.02％減を安定した改善や必要品質の回復とはしない。

参照IDの文章化経路に残る入力差、局所診断の限界、通常API型の過去のCSV成功記録も本文に残す。入力形式・資源計測と同じ保存状態からの提示比較に関する近接研究２件を加え、通常の比較手順を独自手法とはしない。

日英題名は合意済みのものを用いる。和文106字・英文44語はこの検討稿の短い仮要旨であり、教授用456字の置換ではない。和文要旨に`。`と`・`は使っていない。著者・所属・順序は未設定、公式の投稿様式ではなく、投稿可能な最終版ではない。進行中P82と未実行P84の結果は含めていない。

[本文](draft.tex)／[全件表](results.tex)／[費用区間](intervals.tex)／[照合元の内訳と前提](../../../docs/P81_usage_intervals_20261024.md)／[組版・目視記録](visual_review.json)。元の主原稿と既存の検討稿は保存している。

作成は[集計器](../../../scripts/build_time_visibility_interval_draft.py)と[描画器](../../../scripts/render_time_visibility_interval_draft.py)による。元の終了資料と64出典を照合し、数値行の変更を拒否する。再描画後は改めて目視記録を作る。

```sh
python scripts/build_time_visibility_interval_draft.py
python scripts/render_time_visibility_interval_draft.py --tex-bin /path/to/TinyTeX/bin/universal-darwin --output-dir /path/to/render-output
```

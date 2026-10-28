# 図1の日本語改稿：2案の比較

[2案一覧](contact_sheet.png) / [採用案：履歴・要約・直近履歴を分ける](candidate_01_split_documents.png) / [別案：圧縮した入力をまとめて示す](candidate_02_compressed_view.png)

v07には案1を採用した。どちらも入力側の要約と実行後の終了判断を独立したパネルで示す。用紙の束、要約、判定分岐は制御の働きを表し、二つを組み合わせた新方式の実験結果を表すものではない。表示文字は日本語で、モデル略称LLMだけを維持する。

表示寸法は幅130mm・高さ58mm、最小文字7pt。再生成は `papers/202610_letter/harness_efficiency_20261029_v07/figures/render_control_points.py` を参照。旧図と実験数値は元バージョンに保持し、この変更で新しい実験結果を加えていない。

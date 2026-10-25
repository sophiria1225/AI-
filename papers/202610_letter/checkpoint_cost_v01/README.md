# 履歴要約の費用と成功をまとめた作業稿

[PDF](draft.pdf)／[本文ソース](draft.tex)／[全24条件](all_conditions.csv)／[数値と根拠](evidence_summary.json)／[組版記録](layout.json)／[全ページの目視記録](visual_review.json).

題名は「状態保持型LLMエージェントにおける情報保持と実行制御の評価」／“Evaluating Information Retention and Execution Control in Stateful LLM Agents”. 元の日英題名を維持し、P118〜P120の全24実行とP121の974入力計数を中心にまとめた. 同じ既知４課題を繰り返した順次開発であり、独立した24課題ではない.

写真の必須同時要約は、別呼出し要約と同じく成功し、139,871から129,374 tokenへ約7.50%減少した. ただしCSVの成功を失い、全４課題の品質維持と費用削減は未達だった. 入力短縮、要約作成費用、後続行動、最終成果を分けて記載し、新しい圧縮原理や一般的な品質保証を主張しない.

本文と文献４ページ、英文要旨１ページ、全５ページを目視した. はみ出し、ページ外描画、未定義引用と参照は０. underfull警告１件はあるが文字欠落や重なりはない. 本文最終ページの右段は未使用. 公式誌面クラスは未使用で、汎用クラスによる作業稿である. 著者、所属、公式様式、新規な貢献の判断は未完了であり、投稿可能な最終版とは扱わない.

本文用は[和文104字](abstract_ja.txt)、[英文48語](abstract_en.txt)、５キーワード. [教授用459字あらまし](professor_abstract_ja.txt)は別案として用意し、`.`を句点に使い、中黒は含めない. 前の456字案は変更していない. [投稿情報](submission_metadata.json)の著者、所属、住所は未設定のまま残す. 教授への送信と学会投稿は行っていない.

以前の[実行形式を中心とする原稿](../execution_evidence_controls_v02/README.md)は変更せず保存した. その結果を今回の本文へ統合済みとは扱わない. 今回の原典は[確認範囲](../../../docs/inline_memory_prior_scope_20261025.md)と[著者情報の照合](bibliography_sources.json)に基づき、外部手法を実装再現したとはしない.

[P120の全件所見](../../../docs/P120_findings.md)／[P121の補助診断](../../../docs/P121_findings.md)／[原稿再開の指示と区切り](../../../docs/letter_experiment_cutoff_20261025.md).

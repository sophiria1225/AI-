# API一覧と詳細の表示比較：10月23日の全結果

[６枚PDF](AI_harness_inventory_comparison_20261023.pdf)／[操作できるHTML](index.html)／[研究用図PDF](work_tokens.pdf)／[SVG](work_tokens.svg)／[全結果と解釈](../../docs/P55_findings.md)。

全12条件を評価し、監査不一致０。成功は全表示F 1/4、詳細省略D 2/4、詳細＋一覧省略B 1/4。Dは既知分だけでも仕事全体でFより43,083 token多く、さらに不明１生成があるため、総費用削減策には採用しない。写真F/Dの非supervisor保存状態は同一であり、成否差をファイル整理そのものの改善と呼ばない。

表紙は題目のみ。本文は目的と３条件、全12成否・仕事全体token、全件グラフ、実行量と稼働費用、採否と限界の５枚。全６ページを目視、HTML境界・重なり検査も不一致０。資料の数値は閉じた監査JSONから生成した。[出典と描画記録](build_manifest.json)。

[今回の問いに絞った４ページ原稿](../../papers/202610_letter/candidate_inventory_visibility.pdf)／[TeX](../../papers/202610_letter/candidate_inventory_visibility.tex)／[和文あらまし97字](../../papers/202610_letter/inventory_abstract_ja.txt)／[英文45語](../../papers/202610_letter/inventory_abstract_en.txt)。全４頁を目視、はみ出し・未解決引用０。汎用jsarticleで自然改頁した検討用原稿であり、公式IEICEの４ページ確認、著者情報、中心的貢献、投稿準備は未完了。英語あらましは別ファイル。

[原稿の出典・ハッシュ](../../papers/202610_letter/inventory_draft_source_map.json)／[描画点検](../../papers/202610_letter/inventory_draft_layout.json)。通常の段階的開示や再取得費用の既存知見を独自方式にしない。[近接原典と読了範囲](../../docs/inventory_retention_overlap_20261023.md)。

再生成は `scripts/build_inventory_report.py --pdf` と `scripts/build_inventory_paper_tables.py`。TeXはリポジトリルートからshell escapeを無効にしたuplatexを実行しdvipdfmxで変換する。図の実測MediaBoxを明示し、TeXから外部処理を起動しない。再生成後は描画確認とハッシュを更新する。

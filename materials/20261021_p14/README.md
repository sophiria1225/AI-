# P14終了時の説明資料

[11枚のPDF](AI_harness_P11_P14_20261021.pdf)／[編集用PowerPoint](AI_harness_P11_P14_20261021.pptx)／[本文テキスト](transcript.md)。

研究目的、実装したハーネス、全履歴・直近履歴・FOCUS適合版・通常台帳の全結果、保持費用、先行研究との重複、次の限定実験、今月末の投稿計画をまとめた。新しい機構の有効性は未確定で、４開発課題の校正と本評価を分けている。

図の元データは[CSV](figures/cohort_totals.csv)、編集・再利用用に[SVG](figures/cohort_totals.svg)と[PDF](figures/cohort_totals.pdf)も保存。[入力ハッシュ](build_manifest.json)と[数値・テキスト・配置の検査](review.json)から監査できる。PowerPointアプリによる実描画は未確認で、PDFは全ページのプレビューを確認した。

再生成：専用reporting-venvで`scripts/build_p14_presentation.py`、検査は`scripts/review_p14_presentation.py --preview-dir <local-directory>`。原実験の再実行やモデル呼出しは行わない。日本語フォントファイルは再配布していない。

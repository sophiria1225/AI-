# 10月23日：再構成入力の事後診断

[５枚PDF](AI_harness_prompt_identity_20261023.pdf)／[HTML・発表ノート](index.html)／[全33対CSV](all_input_pairs.csv)／[全結果と限界](../../docs/P73_findings.md)。

元P73は末尾LFの原文照合で停止。停止結果と元の検証済み０対を維持し、保存済み69出力を別の読取診断で全件比較した。写真13・12対と書出し８対の文章・全token列・生成制約は一致し、元66入力の実測数とも全件一致。未変更とID変更は一致、本文変更は差を検出した。

元batch69再構成・全入力計数5.543310秒、事前照合1.858735秒、事後読取0.254050秒。新規生成・環境API・評価０。過去のGPU・乱数器状態や一般品質維持は検証していない。元P66/P68の全文不一致・成否・費用は保持する。

全５頁を目視し、重なり・はみ出し０。PDF SHA-256：`d721bf25c989b3bebd49b2f7d27951ec2e696c08d56ea3c0fb34ce69466f3926`。再生成は `scripts/build_prompt_identity_report.py --pdf`。出典は[build_manifest.json](build_manifest.json)、表示点検は[layout_checks.json](layout_checks.json)。PDFが変われば再度目視する。

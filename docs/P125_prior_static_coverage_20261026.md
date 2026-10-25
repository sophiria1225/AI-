# 閉鎖P122: 固定P124 AST認識の適用範囲

状態: complete。24 runs / 432 programs、静的eligible 4 programs / 4 sites。
処理時間 0.267秒。上限5000 programs / 30秒。

保存codeをAST判定しただけで、実行時namespace/value guard、既観測field hit、API省略、精度、総token削減は検証していない。
taskは固定比較内のslotとID hashのみ。元code、課題値、認証情報、変数名は出力しない。
P125の条件は変更しない。P123途中・未知scenario・評価器本文は未閲覧。モデル/API/tokenizer/evaluator/code実行は全て0。

| Run | Task slot | Seed | 旧policy | Programs | Eligible | Sites | 静的fallback理由 |
|---|---:|---:|---|---:|---:|---:|---|
| BOC_P122_R01_01_SINGLE_CHECKPOINT | 1 | 57 | single_checkpoint | 16 | 0 | 0 | no_supported_loop=14, unsupported_program_effect=2 |
| BOC_P122_R01_01_INLINE_CHECKPOINT | 1 | 57 | inline_checkpoint | 16 | 0 | 0 | no_supported_loop=14, unsupported_program_effect=2 |
| BOC_P122_R01_02_INLINE_CHECKPOINT | 2 | 57 | inline_checkpoint | 24 | 0 | 0 | no_supported_loop=24 |
| BOC_P122_R01_02_SINGLE_CHECKPOINT | 2 | 57 | single_checkpoint | 24 | 0 | 0 | no_supported_loop=24 |
| BOC_P122_R01_03_SINGLE_CHECKPOINT | 3 | 57 | single_checkpoint | 13 | 0 | 0 | no_supported_loop=13 |
| BOC_P122_R01_03_INLINE_CHECKPOINT | 3 | 57 | inline_checkpoint | 13 | 0 | 0 | no_supported_loop=13 |
| BOC_P122_R01_04_INLINE_CHECKPOINT | 4 | 57 | inline_checkpoint | 28 | 0 | 0 | no_supported_loop=3, unsupported_program_effect=25 |
| BOC_P122_R01_04_SINGLE_CHECKPOINT | 4 | 57 | single_checkpoint | 31 | 0 | 0 | no_supported_loop=7, unsupported_program_effect=24 |
| BOC_P122_R02_01_INLINE_CHECKPOINT | 1 | 157 | inline_checkpoint | 17 | 0 | 0 | no_supported_loop=1, unsupported_program_effect=16 |
| BOC_P122_R02_01_SINGLE_CHECKPOINT | 1 | 157 | single_checkpoint | 19 | 0 | 0 | unsupported_program_effect=19 |
| BOC_P122_R02_02_SINGLE_CHECKPOINT | 2 | 157 | single_checkpoint | 21 | 0 | 0 | no_supported_loop=1, unsupported_program_effect=20 |
| BOC_P122_R02_02_INLINE_CHECKPOINT | 2 | 157 | inline_checkpoint | 21 | 0 | 0 | unsupported_program_effect=21 |
| BOC_P122_R02_03_INLINE_CHECKPOINT | 3 | 157 | inline_checkpoint | 10 | 0 | 0 | no_supported_loop=10 |
| BOC_P122_R02_03_SINGLE_CHECKPOINT | 3 | 157 | single_checkpoint | 10 | 0 | 0 | no_supported_loop=10 |
| BOC_P122_R02_04_SINGLE_CHECKPOINT | 4 | 157 | single_checkpoint | 10 | 2 | 2 | no_supported_loop=7, unsupported_program_effect=1 |
| BOC_P122_R02_04_INLINE_CHECKPOINT | 4 | 157 | inline_checkpoint | 10 | 2 | 2 | no_supported_loop=7, unsupported_program_effect=1 |
| BOC_P122_R03_01_SINGLE_CHECKPOINT | 1 | 257 | single_checkpoint | 14 | 0 | 0 | no_supported_loop=12, unsupported_program_effect=2 |
| BOC_P122_R03_01_INLINE_CHECKPOINT | 1 | 257 | inline_checkpoint | 15 | 0 | 0 | no_supported_loop=12, unsupported_program_effect=3 |
| BOC_P122_R03_02_INLINE_CHECKPOINT | 2 | 257 | inline_checkpoint | 26 | 0 | 0 | no_supported_loop=26 |
| BOC_P122_R03_02_SINGLE_CHECKPOINT | 2 | 257 | single_checkpoint | 26 | 0 | 0 | no_supported_loop=26 |
| BOC_P122_R03_03_SINGLE_CHECKPOINT | 3 | 257 | single_checkpoint | 11 | 0 | 0 | no_supported_loop=11 |
| BOC_P122_R03_03_INLINE_CHECKPOINT | 3 | 257 | inline_checkpoint | 11 | 0 | 0 | no_supported_loop=11 |
| BOC_P122_R03_04_INLINE_CHECKPOINT | 4 | 257 | inline_checkpoint | 22 | 0 | 0 | no_supported_loop=9, unsupported_program_effect=13 |
| BOC_P122_R03_04_SINGLE_CHECKPOINT | 4 | 257 | single_checkpoint | 24 | 0 | 0 | no_supported_loop=7, unsupported_program_effect=17 |

固定根拠:

- compiler SHA256: `1837f4984b88326f4fea754bf8244783774eec7c6a30c974159895e2dedf774b`
- comparison SHA256: `ccac65fb9f210193cc70ae9e39b9c276eda95e2b6165f431b7e3f5fab4fa4c8e`
- 全program input/code manifest SHA256: `50714bbf4617739c091eb646bd430bc0ba66c59663df695d2c08483c3400d4a9`

詳細集計: [集計JSON](../reports/P125_prior_static_coverage_20261026.json)

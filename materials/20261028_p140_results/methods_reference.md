# P140 方法・設定の参照表

凍結設定と実装、および完了済み事前検査のモデル identity に基づく事実表である。実行途中の成果・usage・生成本文を参照しておらず、結果、削減率、採択判断を含まない。既知課題を用いる事後設計の開発比較であり、確認実験や独立反復とは位置づけない。出典番号は末尾の repo 相対パスと SHA-256 に対応する。[S01, S10]

## 固定対象と確認範囲

| 項目 | 固定内容 |
|---|---|
| 実行ソース commit | `827298fa4219aa4e500d604dfb771f6fe6b815c8` |
| 計画 | `configs/P140_whole_task_checkpoint_delta_envelope_v01.json` |
| 計画 SHA-256 | `635730afeb8baa5c34d80ddb12a9f85b7823944b4c72064c0a46621327d163dc` |
| ソース束縛 | 計画内 1,675 ファイル。事前検査・activation は計画自身を加えた 1,676 ファイルを束縛 |
| 完了済み事前検査 | 初期入力 12、focus 入力 4、checkpoint 後 actor 入力 2 の native 計数。事前検査のモデル生成・評価器呼出しは 0 |
| 保存 identity | revision・runtime・context がモデル選択設定と一致。activation は事前検査の SHA-256 と同じソース束縛を保持 |
| この資料作成時の実行 | モデル・API・native 計数・評価器・保存生成コードの実行なし。現在のサーバーへの再照会なし |

並列 slot 数と KV 型は保存 identity の直接フィールドではなく、事前検査が通過した `check_live_model`／所有サーバー引数検査の条件から確認した。現在時点のライブ設定を再観測したという意味ではない。[S05–S09, S26–S27]

## モデルとサーバー

| 項目 | 設定・確認範囲 | 出典 |
|---|---|---|
| 原モデル名 | `MiniMaxAI/MiniMax-M3` | S04 |
| 使用 GGUF の HF repo | `bartowski/MiniMax-M3-GGUF` | S04 |
| 使用 GGUF の固定 revision | `2ee48e5fcf21a2522ee2fb9ffaa15592ec5498e6` | S04, S26 |
| 量子化 | `IQ4_XS`（選択サブディレクトリ `MiniMax-M3-IQ4_XS`） | S04 |
| ローカル alias | `minimax-m3-iq4xs` | S03–S04, S08 |
| 用途 | text / tool use。vision projector は対象外 | S04 |
| バックエンド | `llama.cpp`、binary tag `b11669`、commit `620d2225cc436ab0b001e3200e590e3b286ef9ab` | S04, S26 |
| 配布物 | `llama-b11669-bin-macos-arm64.tar.gz`、SHA-256 `dbed55493d72bc1ba2babc8770d669c2289b5bc4ee9fb2a4dfc158d45b7d13fd` | S04, S26 |
| runtime 記録の release ラベル | `v0.7.0`。具体的ビルドの識別には上記 tag / commit を併記 | S04, S26 |
| context | 65,536 tokens。入力＋予約出力が収まらない要求は admission で拒否 | S03, S17, S26 |
| モデル並列 slot | `--parallel 1`。事前 identity 検査も `total_slots == 1` を要求 | S06, S08 |
| KV cache 型 | K = `q8_0`、V = `q8_0`。起動引数と identity 検査で固定 | S05–S08 |

revision は量子化配布 repo の commit である。原モデル repo の別 revision は、この選択設定では明示なし。モデル選択 JSON は計画内 1,675 source map の直接要素ではないため、固定 commit の tracked bytes、P29 設定からの参照、保存 identity の一致を別の根拠として用いる。重み本体や個別保存場所は含めない。[S03–S04, S08, S26]

## 生成要求の明示設定

actor は課題を進める生成、focus は別呼出しで checkpoint を要約する生成を指し、同じモデルを使う。[S03, S12–S18, S21]

| 項目 | actor | focus |
|---|---|---|
| `temperature` | `1.0` | `0.7` |
| `top_p` / `top_k` / `min_p` | `0.95` / `0` / `0.0` | 同じ |
| `repeat_penalty` | `1.0` | `1.0` |
| request seed | `57 + その役割の先行記録済み生成呼出し数` | 同じ式。actor とは別に数える |
| 設定出力上限 | 1 呼出し 4,096 tokens | 1 呼出し 4,096 tokens |
| 実際の `max_tokens` | 残余共有予算と native 入力数から選ぶ上限（最大 4,096） | 同じ admission と、focus＋次 actor を見込む事前 screening |
| thinking | `thinking_mode=enabled`、`reasoning_budget_tokens=-1`、`reasoning_format=deepseek` | 同じ |
| tools | 共通の `CODE_TOOLS`、`tool_choice=auto`、`parallel_tool_calls=true` | tools なし。`tool_choice`／`parallel_tool_calls` は要求に追加しない |
| streaming | `false` | `false` |
| prompt cache | 各条件の最初の生成は `cache_prompt=false`、以後は `true` | 同じ全役割の呼出し履歴に基づく |
| `typical_p`、sampling 順序、frequency / presence penalty | 明示なし | 明示なし |

seed 57 は各条件の基点であり、全呼出しへ固定 57 を送る設定ではない。環境の `world_seed` は 42。`reasoning_budget_tokens=-1` は別の推論予算制御を設けない指定であり、4,096 の総出力上限や共有予算を解除しない。`parallel_tool_calls=true` はモデル並列 slot 数 1 とは別の設定である。未指定パラメータのバックエンド既定値は推測して補っていない。[S01, S03, S11–S18]

出力予約は `min(4096, max(0, 残余 token 予算 − native 入力数))`。さらに入力＋予約出力の context 条件を検査する。focus の screening は現在の actor 入力数、focus 入力数、両者の設定出力上限、残余共有呼出し数を用いるため、trigger が立っても必ず送信されるわけではない。呼出し timeout は設定上 600 秒を上限として残余作業時間で制限する。自動再試行は 0。[S01, S13–S18]

## 比較条件と有限予算

4 つの既知課題に 3 方式、各 1 条件、計 12 枠。課題は同じ公開 task identity と初期状態を使う。保留 12 課題は選定・設計・この資料の作成に参照していない。[S01, S10]

| 課題 slot | 公開 task ID | 1 条件の API 上限 | 方式の実行順 |
|---|---|---:|---|
| 1 | `34d9492_1` | 160 | threshold_recursive → exposure_delta → exposure_delta_object |
| 2 | `3c13f5a_1` | 80 | exposure_delta → exposure_delta_object → threshold_recursive |
| 3 | `60d0b5b_1` | 80 | exposure_delta_object → threshold_recursive → exposure_delta |
| 4 | `6104387_1` | 80 | threshold_recursive → exposure_delta → exposure_delta_object |

| mode | 初回機会 | 第 2 機会の timing | 第 2 機会の表現 |
|---|---|---|---|
| `threshold_recursive` | 共通の native 入力閾値 | native 入力 ≥ 16,384 | 旧要約を参照して 1 個の要約へ置換 |
| `exposure_delta` | 同上 | 過去に支払った prefix 提示量 `E ≥ C` | 旧要約を同 bytes で保持し、新しい delta を追加 |
| `exposure_delta_object` | 同上 | 同じ `E ≥ C` | 同じ delta 機構。第 2 delta focus の system prompt に「新 delta JSON object だけを返し、array 合成は host が行う」と明示 |

候補と未変更 `exposure_delta` の差は、第 2 機会に delta が要求される場合の focus system prompt だけである。初回 focus prompt、user packet、parser、サイズ上限、host の結合処理は共通。初回に採用された要約がなければ、次の機会を自動的に「delta 介入あり」とは数えない。[S19–S21]

| 項目 | 固定上限・条件 |
|---|---|
| 1 条件の生成呼出し | actor + focus 合計 80 |
| 1 条件の logical input + output | 全役割合計 450,000 tokens |
| 1 条件の作業時間 | 1,800 秒 |
| その他の段階上限 | setup 120 秒、cleanup 180 秒、idle wait 60 秒、公式評価 180 秒 |
| checkpoint 機会 | 最大 2。拒否・未送信になった機会も含む |
| 要約前提 | 新しい closed turn が 3 以上、削除候補の新 raw prefix が存在 |
| 最近の履歴 | 直近 2 closed turns を保持 |
| 全 12 枠の予約上限 | 960 生成呼出し、5,400,000 tokens、1,200 API 要求、12 公式評価 |
| 時間枠 | server 30,000 秒、batch 28,200 秒、pipeline 30,600 秒。最終起動 2026-10-27 23:30 JST、絶対終了期限 2026-10-28 08:00 JST |

P123 の通常 interface を引き継ぐが、P140 は全方式で最大 2 機会に揃えている。P123 の最大 3 機会という元条件全体を再現した対照ではない。[S01–S02, S10]

## E / C と checkpoint 採用の定義

`C` は直前の **terminal usage が既知である、送信済み focus** の input + output。構文不適合、サイズ超過、短縮不成立などで要約が採用されなくても既知の費用を計上し、`C` を更新して `E` を 0 に戻す。[S22–S23]

その後の各既知 actor 要求について、実際の完全入力の native token 数を `I`、その入力から新たな圧縮対象 raw prefix だけを除いた計数専用入力の native token 数を `I_without` とし、`E ← E + max(0, I − I_without)` とする。system、task、以前の checkpoint、直近 2 turns、予算通知、tools は保持する。符号付き差も記録するが trigger には正部分を用いる。計数専用入力をモデル生成へ送信しない。実際に送信され terminal usage が既知になった actor だけを加算し、次の未送信入力を先取りしない。全方式に同じ shadow 計数を適用する。[S19, S21–S23]

初回は全方式とも native 入力 16,384 以上を用いる。第 2 機会では上表の timing を使い、いずれも新 raw prefix・fresh turn・最大機会数・共有予算の条件を満たす必要がある。`E` は過去の提示に基づく指標であり、実現した節約量、将来の回収、期限内完了、競争比を保証しない。[S01, S19–S23]

要約は `completed / usable_state / remaining / uncertainties` の 4 fields を持つ JSON object。各項目は最大 2,048 文字、旧要約と delta の合計で各 field 最大 32 項目、canonical JSON body 合計最大 8,192 **文字**。これは token 上限ではない。単体では object、2 fragment の body は host が `[previous, delta]` として構成する。構文・上限が成立し、完全な次 actor 入力の native 計数が従来入力より厳密に小さい場合だけ投影を採用する。意味の保持を検証する別モデルは用いず、要約を fallible として扱う。[S01, S18–S20]

## 会計・成功・比較の限界

| 項目 | 定義 |
|---|---|
| 主費用 | 仕事全体の actor + focus の logical input + output。繰返し入力、返却された reasoning、失敗・不採用 focus の既知費用も含める |
| cache | cached input は補助計測として保持し、input から控除しない。wall time・GPU 実演算量・金銭請求額とは別の指標 |
| 未知 usage | terminal usage 不明は unknown のまま保持し、生成継続・無料 retry を行わない。既知小計と未知回数・欠測条件を分離し、正確な全仕事 total を 0 や推定値で埋めない |
| 報告の厳密 total | 全 12 条件が評価済み・usage 既知でなければ各方式の固定 total は null。各比較も全 4 pairs 既知が必要で、共通成功集合が空なら common total は null |
| 計数専用処理 | native input / shadow 計数は生成ではなく、モデル生成 token 費用へ架空に加算しない。処理時間・計数記録は別途保持 |
| 最終品質 | 実行終了後の凍結状態に対する AppWorld 公式 `evaluate_task` の `result.success` を boolean として記録。要約採用・モデルの完了宣言・正常 API 返答で代用しない |
| 評価の分離 | 評価結果は actor に返さない。評価前後の凍結 DB hash 不変を検査する実装。これは評価器の無誤りを別途証明するものではない |

上記は固定会計・報告コードと評価 wrapper の定義であり、この資料で評価本文や DB を読み直した結果ではない。[S01, S10, S12–S18, S22–S23, S25]

主比較は候補対 `threshold_recursive`、別比較は候補対未変更 `exposure_delta`。それぞれ全 4 pairs の既知会計、成功喪失なし、全件および共通成功の費用減、共通成功上で既知費用を伴う変更 prompt と delta の実 actor 配信などを固定条件とする。後者にはさらに、介入前 prefix の validated transport-ID canonical 対応を要求する。両比較を分けて保持し、片方の不成立を他方の結果へ置換しない。ここではどちらの判定値も記載しない。[S01, S10, S24]

P139 の閉鎖後証拠を見て設計した、既知 4 課題・seed 基点 57 の開発比較である。旧 cohort を併合せず、独立反復、未知課題への一般化、一般的な品質非劣性、新規性はこの設定から主張しない。strict prefix 一致は別に保持し、canonical 比較が許すのは検証された tool transport ID の全単射のみ。本文、引数、role、usage、状態内容を意味的に正規化しない。それでも canonical 対応は隠れた環境状態や意味の同一性を保証しない。[S01, S10, S24]

## 公開 repo 相対パスと SHA-256

S01–S25 は固定 commit、凍結実行 tree、この公開準備 tree の同 bytes を確認した。S02–S25 のうち S04（モデル選択）を除く 23 ファイルは S01 の source map に直接束縛される。S26–S27 は完了済み事前検査・activation の記録であり、進行中の成果ではない。成果回収前なのでこの 2 記録をここへ複製していない。相対パスは repository root 基準。

| ID | 相対パス | SHA-256 |
|---|---|---|
| S01 | [configs/P140_whole_task_checkpoint_delta_envelope_v01.json](../../configs/P140_whole_task_checkpoint_delta_envelope_v01.json) | `635730afeb8baa5c34d80ddb12a9f85b7823944b4c72064c0a46621327d163dc` |
| S02 | [configs/P123_whole_task_rolling_checkpoint_v01.json](../../configs/P123_whole_task_rolling_checkpoint_v01.json) | `b4bb3fabb6d1b97dc67f3f17f1a3a97bafccfd13f2ce02c70da73d54d6962b0e` |
| S03 | [configs/P29_stateful_code_v01.json](../../configs/P29_stateful_code_v01.json) | `501cb346e7dbfbeace99a16c06923d09543fc0a82bfb2d3ead87413abe549898` |
| S04 | [configs/models/minimax_m3_iq4_selection.json](../../configs/models/minimax_m3_iq4_selection.json) | `66fcce6347cfa18a0bc8cba3643048c1a136620fb2c4d4c4db87c051b8abd83c` |
| S05 | [scripts/run_whole_task_checkpoint_delta_envelope_pipeline_p140.py](../../scripts/run_whole_task_checkpoint_delta_envelope_pipeline_p140.py) | `cf0f5c893adee77c0b3a755013bcb056aa3e5cd56a5d84851c76d308079eb9f9` |
| S06 | [scripts/serve_research_model_recovery.py](../../scripts/serve_research_model_recovery.py) | `e2b95b612426a318821c6295be156122deaebbdda074c10fbd727f0502a82d68` |
| S07 | [scripts/checkpoint_delta_envelope_server_identity_p140.py](../../scripts/checkpoint_delta_envelope_server_identity_p140.py) | `47d6f5d41277a1a4e2eca88f4898cd3dcf92c1ac5845dc28234405cbb36bd121` |
| S08 | [scripts/model_provenance.py](../../scripts/model_provenance.py) | `bafb2f78c0bbf49573afeaafc833906d7ae2d93d679bad321ea1fb27b46fd4b3` |
| S09 | [scripts/run_whole_task_checkpoint_delta_envelope_p140.py](../../scripts/run_whole_task_checkpoint_delta_envelope_p140.py) | `4bddba239f7d73c4225b7ecec05da79a04a841bf52141337611d8a25138cffd6` |
| S10 | [scripts/whole_task_checkpoint_delta_envelope_p140.py](../../scripts/whole_task_checkpoint_delta_envelope_p140.py) | `0e9f6da468c317fef8bb1ce2e518cef16939a8a35065fa3a27e44cdf6ca4f21e` |
| S11 | [scripts/api_error_comparison.py](../../scripts/api_error_comparison.py) | `211e4044e2f3d1a09dc2944fdeba9395ac5d8544acde3c4e5841ae5c5169029b` |
| S12 | [scripts/local_llama.py](../../scripts/local_llama.py) | `0c2eda98d5a031ea4b045cd272a9eca3a9263c9bc1f4d310636387b807197467` |
| S13 | [scripts/tool_choice_local_llama.py](../../scripts/tool_choice_local_llama.py) | `e230f8997786f4df97aebfbe9b34ac0ec44a31c59f8c9c853dcbbbfa2ab6e3fd` |
| S14 | [scripts/fixed_budget_local_llama.py](../../scripts/fixed_budget_local_llama.py) | `4ac43105b446ff89c515de484a1b46b5d412b90817eab5e441b4424ec25d2f84` |
| S15 | [scripts/tool_choice_residual.py](../../scripts/tool_choice_residual.py) | `65ac0c5318d31e140a593513833f644e88da29fe9839b8f21c9d24e5fdf56560` |
| S16 | [scripts/fixed_budget_residual.py](../../scripts/fixed_budget_residual.py) | `cbf7f8cdc93c99c10f3700571267339ce847e05fe45089c3b075371658cc5eb7` |
| S17 | [scripts/residual_output_budget.py](../../scripts/residual_output_budget.py) | `5f96aa7d26d45ada35e10c6b39fe36a9ed71da96019095b495efd9a01c552cd4` |
| S18 | [scripts/rolling_checkpoint_inference.py](../../scripts/rolling_checkpoint_inference.py) | `d099e55d1cb727875fd18b1447abd9bb8e250127c234564440eb5463fd98ab6b` |
| S19 | [scripts/checkpoint_representation_p139.py](../../scripts/checkpoint_representation_p139.py) | `8cc12812f5413f8157e99591108ea53bf0af91bdfff64639baf24481f0f231e9` |
| S20 | [scripts/checkpoint_delta_envelope_p140.py](../../scripts/checkpoint_delta_envelope_p140.py) | `7c9f5390e034b8bc3b82f4575b0b8880d5fe3b09c383166fab5f83058e65db1d` |
| S21 | [scripts/checkpoint_delta_envelope_inference_p140.py](../../scripts/checkpoint_delta_envelope_inference_p140.py) | `c115aad68d31f42738a3714ddbf8817a87d8d1f89c1746204a95487f3881456a` |
| S22 | [scripts/checkpoint_prefix_exposure.py](../../scripts/checkpoint_prefix_exposure.py) | `134ecdf959a5d63696c62d601c0d79e7c786ae8d187a599d2d3ec04e16a5d037` |
| S23 | [scripts/checkpoint_representation_inference_p139.py](../../scripts/checkpoint_representation_inference_p139.py) | `c7b896bc2508954a3188fa8c99c12ce36e1cec358d857f43ed366592ebb276a5` |
| S24 | [scripts/checkpoint_prefix_identity_p140.py](../../scripts/checkpoint_prefix_identity_p140.py) | `9b6700a4f9978be3ac76a2555dce2e428e3248f1d218aeb78adc68cb6180419a` |
| S25 | [scripts/evaluate_context_trial.py](../../scripts/evaluate_context_trial.py) | `993670d699d58d24211be30f61cda113c99c7244ffe87b86b16d623c967c3fa4` |
| S26 | `reports/P140_initial_checks.json` | `657b1d743b389782347fed6698951de2817d4ba59371e61d8d4542bca733e475` |
| S27 | `reports/P140_activation_v01.json` | `8a95458aa6f409df74e6451a7007b66a15cfd86829abf84bfac065a278fde7f6` |

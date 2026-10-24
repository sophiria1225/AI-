# 部分コードの再利用を検討する前の原典確認

2026-10-24。[閉じた855生成の点検](../materials/20261024_truncated_code_prefix_scope/README.md)で、未完の引数に構文として読めるコードの前半が残ることを確認した。以下は新規性の証明ではなく、通常部品との重なりと未解決部分の整理である。

Pydanticの[JSON文書](https://pydantic.dev/docs/validation/latest/concepts/json/#partial-json-parsing)は不完全なJSONの読取りを扱い、[部分検証](https://pydantic.dev/docs/validation/latest/concepts/experimental/#partial-validation)では未完の末尾文字列を残す設定も説明している。一方、元の入力が最終的に何だったはずかは保証せず、末尾項目のエラーを無視する制限もある。既知の文字だけを取り出すことや途中JSONの解析そのものを独自手法としない。必須引数の補完や、抽出したプログラムの実行を正当化する保証とは別である。

[AgentExecutor v1](https://arxiv.org/html/2608.05959v1)の要旨・§2.1・§3.1–3.5.2を確認した。ここでいうprefixは、不足する環境や変数を補うため、与えられたコード片の前へ生成・追加するコードであり、目標は元コードの行被覆である。今回の「既に出たプログラムの前半を保持する」とはprefixの意味が異なる。同論文を、途中切れツール呼出しの安全なcommitを検証した研究として引用しない。反対に、この一つの論文と対象が違うことだけで新規性があるとも判断しない。外部の実装・データは再実行していない。

今回の７出現は同じ１コードであり、先頭に認証、後に反復するデータ取得がある。構文検査、未実行であることの記録、モデルによる再承認、既存状態との対応、作用の確定、最終成果の独立評価は別の条件である。未完の続きを自動補完して成功済みの操作へ格上げしない。単純な再試行、通常の部分JSON処理、未実行コードの参照による再使用と比較せずに新規制御を主張しない。

検索はstreaming code execution、truncated tool calls、partial JSONの３問と既知URLの原典読取に限る。検索で関連例が出なかったことは不存在の証拠ではない。[読取範囲の記録](../reports/partial_code_prior_sources_20261024.json)。[先行実行と処理列再利用](../materials/20261024_execution_reuse_priors/README.md)の既存研究も保持する。

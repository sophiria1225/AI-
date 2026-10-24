# 外部実装での履歴識別子：確認範囲

2026-10-24. smolagents の固定コミット `96f33faaf028479119ec8d34507b47694cf14e34` を読み、ツール呼出しの識別子がモデル向け本文へ入る経路を確認した. これはP98の適用範囲を説明するソース上の補足であり、外部環境での性能再現ではない.

| 読んだ経路 | ソースから確認したこと | 主張しないこと |
|---|---|---|
| `ToolCall.dict` → `ActionStep.to_messages` | 呼出しIDを含む辞書列を通常の本文へ文字列化する. エラー分岐にも先頭呼出しIDを本文へ追加する箇所がある. | 形式エラーの場合だけに起きる現象とはしない. |
| `ToolCallingAgent` → `Model.parse_tool_calls` | 構造化ツール呼出しがない場合は本文の解析へ進み、その解析器はUUIDを作る. 取得したIDをメモリーへ記録する. | 今回のAppWorld比較と同じ失敗、同じ出力分岐が起きるとはしない. |
| メモリー → モデル入力整形 | 各手順のメッセージを集めて次のモデル入力へ渡す. 標準の役割変換ではtool-callとtool-responseをassistantとuserへ写し、本文を残す. | 全バックエンド・全設定の実際の送信を測ったとはしない. |
| `CodeAgent` | IDは保持手順数から作る. | すべての経路で乱数IDを使うとはしない. |
| 標準の提出設定 | `required`が引数の既定値であり、モデル設定による上書きもある. | P99の設定を新提案と呼ばない. |

根拠は固定版の [memory.py](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/memory.py#L92)、[履歴から入力への接続](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/agents.py#L758)、[ToolCallingAgent](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/agents.py#L1284)、[本文解析とUUID](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/models.py#L400)、[モデル入力整形と提出設定](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/models.py#L502)、[CodeAgentのID](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/agents.py#L1715). ３ファイルのGit blob SHAを取得内容と照合し、SHA-256と読んだ行範囲を [出典記録](../reports/external_history_identifier_sources_20261024.json) に保存した.

この確認から、モデルの入力となる本文には、処理内容に加えて接続用の識別子が入り得ると説明できる. ただしIDを変えた場合の出力変化、ツール実行、課題品質、費用は外部実装で測っていない. 既知の参照統一や複数の評価指標を新手法へ読み替えず、P98の自作ハーネスで得た観測とは区別する. フレームワークの代表的調査でもない. LangChainも検索したが、検索断片だけで同じ経路があると結論せず、確認件数へ含めていない.

外部コードの実行・インストール、モデル生成、環境API、評価器の追加はすべて０. P97/P99の条件を変更していない. P98本文とPDFは固定した版を保持し、この補足を本文へ統合したとはまだ扱わない.

# 外部ハーネスの参照IDが本文へ入る範囲

2026-10-24。P84の生成中に、３ライブラリの固定版９ファイルを静的に読んだ。今回の履歴修正が適用できる範囲を確認するための調査であり、外部ライブラリの動作再現、生成比較、品質評価ではない。[読取範囲・固定commit・内容hash](../../reports/framework_reference_source_review_20261024.json)を保存した。

| 確認した経路 | 実装で確認できた参照IDの扱い | 今回の修正への含意 |
|---|---|---|
| smolagents の ActionStep → モデル入力 | ツール呼出しの辞書を文章にする際にIDも含める。エラー時には呼出しIDを本文に再掲する。共通の入力整形は役割を変換してもこの文章を保持する | 参照を文章化する経路はこの研究ハーネス以外にもある。ただし正常な呼出しにも使う経路であり、今回の不正引数時だけの退避と同じではない |
| AutoGen の通常の OpenAI 形式変換と既定の結果要約 | 呼出しIDと結果の対応IDを専用欄に保持し、結果本文は別に渡す。既定の要約は結果内容を使う | この範囲では今回と同じ自動的なIDの文章化を確認していない。独自の要約関数や結果本文、別の変換経路までIDが入らないと保証したわけではない |
| Pydantic AI の文字だけの結果／添付ファイル付き結果 | 文字だけの結果は本文と対応IDを別欄へ送る。添付をユーザー欄へ移す経路では、出所を示すタグにツール名・呼出しID・ファイルIDを含める | 本文にあるIDがすべて不要とは限らない。添付と呼出しの対応を保つ必要があり、今回の文字列一括除去の根拠にできない |

smolagents は [記憶からの文章化](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/memory.py#L92)、[入力整形](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/models.py#L332)、[モデルへの送信経路](https://github.com/huggingface/smolagents/blob/96f33faaf028479119ec8d34507b47694cf14e34/src/smolagents/agents.py#L1284)を確認した。ToolCallingAgent はモデルが返したIDを保持し、CodeAgent はステップ数からIDを作る。この違いを無視して、すべての実行でIDが無作為に変わるとはいわない。

AutoGen は [呼出しと結果の変換](https://github.com/microsoft/autogen/blob/004749e6b7102c8fd317b9b1499ce5807223c278/python/packages/autogen-ext/src/autogen_ext/models/openai/_message_transform.py#L441)と [既定の要約](https://github.com/microsoft/autogen/blob/004749e6b7102c8fd317b9b1499ce5807223c278/python/packages/autogen-agentchat/src/autogen_agentchat/agents/_assistant_agent.py#L1498)を確認した。専用欄のIDが最終的なモデル入力で不可視になるとは限らず、ここで確認したのは本文への転記の有無である。モデル側の会話テンプレートや提供者の内部処理は調べていない。

Pydantic AI は [文字と添付の分離](https://github.com/pydantic/pydantic-ai/blob/120891d166555a20060650b9e0e699a530808b0d/pydantic_ai_slim/pydantic_ai/messages.py#L2199)、[出所タグ](https://github.com/pydantic/pydantic-ai/blob/120891d166555a20060650b9e0e699a530808b0d/pydantic_ai_slim/pydantic_ai/messages.py#L1900)、[送信時の対応ID](https://github.com/pydantic/pydantic-ai/blob/120891d166555a20060650b9e0e699a530808b0d/pydantic_ai_slim/pydantic_ai/models/openai.py#L2331)を確認した。この固定版では旧RetryPromptPartは非推奨で、ツールに対する再試行は対応IDを保ったToolReturnPartへ変換する。古い検索結果のクラス説明だけで現行経路を判断しない。

今回のCは、整合した呼出し・結果の構造を保持したまま通信参照だけを統一し、その後にRで文章化する。一般本文や引数の同じ文字列は変更しない。外部実装へ広げるには、参照の使い道、対応関係、未知の参照、添付経路を個別に確認する必要がある。上の９ファイルを読んだだけで、外部実装への互換性、同じ不具合の発生率、出力安定化、費用削減、新規性を示したことにはならない。

[P83の全６入力](../../docs/P83_findings.md)／[公開最小再現例](../20261024_protocol_minimal_reproducer/README.md)／[先行研究と露出範囲](../../docs/identifier_prior_and_exposure_20261024.md)。P84の入力・順序・予算・採否は変更していない。追加の生成・入力計数・環境実行・課題評価は０。

# 既存の文法制約と、出力上限に達した呼出し

2026-10-24。終了済みのP80/P81全24条件・429生成を監査hashへ照合し、P83の全６保存入力の構文設定を調べた事後診断である。追加のモデル生成・入力計数・API実行・評価は０。解析は0.699295秒で、資料の記述やファイル書出しを含まない。P82の途中記録はこの解析へ入れていない。

## 全件の記録

| 終端の観測 | 生成数 | 文章化対象の引数を返した応答数 |
|---|---:|---:|
| tool_calls | 423 | 0 |
| length | 4 | 3 |
| 終端未観測・使用量不明 | 2 | 不明 |
| 合計 | 429 | 観測済み3、未観測2 |

全429要求はtoolsあり、tool_choice=auto、parallel_tool_calls=true、stream=falseだった。要求側の明示grammar・json_schema・response_format指定は０。ただし、明示指定がないことは推論器内の制約がないことを意味しない。

P83の６保存入力のsession controlsは全て同一で、formatはpeg-minimax-m3、非空の5,013文字の文法、grammar_lazy=true、trigger１件、preserved token５件だった。保存ファイルと公開controls hashを照合した。追加のレンダリングやサンプリングは実施しておらず、全生成トークンでの文法適用を動的に検証したわけではない。

| 閉じたH書出し条件 | 不正引数の応答 | 出力数／上限 | 既存の参照露出診断 |
|---|---|---|---|
| P80・第１反復 | call_013、length | 4,096／4,096 | 次の14要求目から7要求 |
| P81・第２反復 | call_013、length | 4,096／4,096 | 次の14要求目から6要求 |
| P81・第３反復 | call_013、length | 4,096／4,096 | 次の14要求目から7要求 |

各応答は１つのツール呼出しを含み、その引数がJSONとして不正だった。構文は正しいがobject型でない引数は観測されなかった。もう１件のlengthは第３反復call_018で、ツール呼出し０だった。length自体を不正引数と同一視しない。これらは同じ既知課題の反復であり、３つの独立課題での障害とは数えない。

## 固定ソースとの対応

llama.cppの固定コミット620d2225cc436ab0b001e3200e590e3b286ef9abを読み、保存済みtar.gzと６ソースファイルのバイト一致を確認した。

- [MiniMax-M3 parser](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/common/parsers/minimax-m3.cpp)はtoolsとauto指定から遅延文法を組み立てる。指定された呼出し開始タグをtriggerとする。
- [chat session](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/common/chat.cpp#L1683)と[server task](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/tools/server/server-task.h#L266)は、生成した文法と遅延設定をsamplingへ渡す。
- [sampling](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/common/sampling.cpp#L216)には遅延文法の初期化と適用制御がある。構文を制約することは、有限の生成上限内に構文を完結させる保証とは異なる。
- [部分ASTの変換](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/common/chat-peg-parser.cpp#L1134)では、部分的な引数の閉じ引用符や閉じ括弧を補わずJSON文字列を作る。このソース挙動と観測は整合するが、保存された全生成過程の再実行による因果同定ではない。

元の[NativeConversation](../../scripts/native_conversation.py)は不正または非object引数が１つでもあれば、その呼出し群全体と実際の返却を文章として残す。P83で検証した参照統一の順序はこの表示経路に関係する。文法制約を追加するだけの案を、新提案として数えない。

## この診断から主張しないこと

不正呼出しを補修・再実行したものではなく、出力枠の延長や呼出し強制が有効と示したものでもない。Mの書出し３条件はこの露出なしでも未達だった。全失敗の原因、回避可能費用、品質維持、一般的な新アルゴリズムは未確立のままである。P82/P84の固定条件・予算・採否を変更しない。

[解析JSON](diagnosis.json)、[全429生成CSV](all_429_calls.csv)、[全24条件CSV](all_24_conditions.csv)、[読取範囲](../../docs/tool_grammar_boundary_20261024.md)、[解析コード](../../scripts/inspect_closed_tool_boundaries.py)。私的な要求・応答はhash照合と構文判定のためプログラムで読み込んだが、内容を公開せず、返却推論の意味を読んでいない。欠測２件は観測不能として残した。

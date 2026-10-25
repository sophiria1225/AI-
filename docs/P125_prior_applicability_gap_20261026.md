# P122 投影適用率の構文・API 範囲診断

結論: 現在の適用率を増やすために whole-program 構文制限を緩める根拠は、この閉鎖 cohort では見つからなかった。固定契約の対象は `spotify__show_song` だけで、対象呼出しを for 内に持つ全 4 programs が既に受理されている。

24 runs / 432 programs を固定 P124 compiler で AST 判定した。第1走査 0.288 秒、第2走査 0.158 秒、それぞれ上限 5000 programs / 30 秒。保存コード実行・namespace/value guard・model/API/tokenizer/evaluator 呼出しはすべて 0。P123、未見課題、評価本文は読んでいない。P125 source/条件は変更していない。

## 固定契約の対象箇所

| 分類 | 件数 |
|---|---:|
| 全 programs | 432 |
| 現 eligible programs / sites | 4 / 4 |
| no_supported_loop | 262 |
| unsupported_program_effect | 166 |
| 対象 API の直接 call を含む programs | 6 |
| 対象 API の call AST nodes | 10 |
| 対象 call を for 内に含む programs | 4 |
| 対象 call を含む for AST nodes | 6 |
| 対象 for programs の whole-program 拒否 | 0 |
| whole-program guard だけを除けば救える厳密 local candidate | 0 |
| safe prefix の候補を unsafe suffix が妨げる programs | 0 |

対象 call を持つ残り 2 programs は for 内 call がなく、同じ source hash の重複で、whole-program 拒否分類は unsupported_method_dumps。対象 6 programs は 3 unique source hashes、for を含む 4 programs は 2 unique source hashes にすぎない。eligible 4 件を独立した 4 種のコードと解釈してはいけない。

追加の字面検査では target literal pair を使う call はすべて call_api 形式で、別名 callable、対象属性呼出し、get_track 形式による見落としは 0。対象 API 名の文字列はドキュメント要求等にも現れるため、それ自体は実行候補数にしない。

## 全体の拒否分類（重複あり）

| AST/制約分類 | programs |
|---|---:|
| node_Import | 114 |
| node_ImportFrom | 2 |
| unsupported_method_dumps | 112 |
| other_named_call | 31 |
| unsupported_method_get | 26 |
| non_name_attribute_receiver | 24 |
| protected_function_capability_escape | 8 |
| attribute_capability_escape | 6 |
| multiple_or_destructured_assignment | 2 |
| node_Try | 2 |
| node_Lambda | 4 |
| node_Assert | 1 |
| unsupported_method_write | 2 |
| unsupported_method_writerow | 5 |

FunctionDef / AsyncFunctionDef による拒否は 0。node_alias は import 文の AST 型であり、変数 alias escape の証拠と混同しない。上表は非排他的な構文分類で、実行時の作用や動的例外を測ったものではない。これらを緩和しても対象 show_song loop の追加受理は 0。

## 公開 API ごとの lexical for 呼出し

全 call_api AST nodes は 541、公開 schema に照合できた literal app/API nodes は 533。残り 8 は schema にない literal 名で、元の名前は出力しない。以下は実 API 回数ではなくコード内の構文箇所数。反復回数、到達性、成功、キャッシュ hit は測っていない。

| 公開 API | 全 call nodes | for 内 nodes | for programs | for unique sources |
|---|---:|---:|---:|---:|
| file_system__move_file | 18 | 18 | 6 | 3 |
| file_system__show_file | 21 | 6 | 6 | 3 |
| file_system__create_directory | 10 | 6 | 6 | 3 |
| spotify__show_song | 10 | 6 | 4 | 2 |
| spotify__show_album | 7 | 5 | 5 | 5 |
| spotify__show_playlist | 6 | 4 | 4 | 4 |
| spotify__show_artist | 4 | 4 | 4 | 4 |
| venmo__create_payment_request | 14 | 2 | 2 | 1 |
| file_system__show_directory | 45 | 1 | 1 | 1 |

写真/ファイル系では show_file に 6 for programs / 3 unique sources があるが、公開 show_directory はパスの配列を返し、show_file は内容・日時等を返す。directory の既観測値だけで file 内容を再構成する契約はこの公開実装からは得られない。move_file / create_directory、精算側 create_payment_request は書込み操作であり、read projection の候補数に加えない。精算側で観測した for 内 call は create_payment_request の 2 nodes のみで、read projection の直接候補は出ていない。

## 最大1つの次候補

調べるなら `spotify__show_album_library` → `spotify__show_album` の metadata 需要に限った新契約の適否。show_album は for 内 5 nodes / 5 programs / 5 unique sources と、現 show_song よりコード形の範囲が広い。ただし公開 album library と full album の入れ子 song 詳細は同じ field ではなく、実 consumer が metadata だけを読むか、既観測値で足りるかは今回未確認。現診断だけで実験を推奨する根拠には足りない。両armに同じ通常 complete cache を用意し、serializer・要求 field・epoch の監査が先に必要になる。これは契約対象の拡張で、独立した新規 cache 原理やcompiler原理とは呼べない。

今回の実務判断: P125 は固定のまま実施し、この診断を理由に一般的な try/function/import 許可へ広げない。新しい契約候補の適用性は別の有限・閉鎖資料診断で確認する。

固定根拠:

- compiler SHA256: `1837f4984b88326f4fea754bf8244783774eec7c6a30c974159895e2dedf774b`
- contract SHA256: `cc7ff1f8ab452a5ed7cb562a93941a4d1f85db663c841d545cd01732ea04b44a`
- 432 input/code manifest SHA256: `50714bbf4617739c091eb646bd430bc0ba66c59663df695d2c08483c3400d4a9`
- 公開する集計: [JSON](../reports/P125_prior_applicability_gap_20261026.json)。元の非公開診断はhashで結合し、公開JSONは集計と公開API名に限定する。

# P125: 発動0の原因と次の検証範囲

全8条件、所有server、元監査とcollectorの閉鎖後に調べた。保存生成コードはASTとして読むだけで実行せず、モデル・実API・tokenizer・評価器の追加呼出しは0。全146 programのsource hashと保存証拠を対応させた。

| 確認項目 | 結果 |
|---|---:|
| static eligible / transformed / partial hit | すべて0 |
| 通常complete cache hit / projection contract stop | ともに0 |
| unsupported_program_effect / no_supported_loop | 120 / 26 |
| AST解析失敗・証拠欠落 | 0 |
| 両方式でsourceが一致したprogram組 | 73/73 |
| 通常経路のexecution_error | 28、すべて未変換 |
| CSVの実show_song取得（各方式） | 25 |
| 先行返答でIDを観測済み（各方式） | 25/25 |
| 現library providerで必要値が存在（各方式） | 0/25 |
| 既存の通常joinでtitleとartistsが存在（各方式） | 13/25 |

CSVはlibrary由来の既知値をモデル自身がmapに保持し、そのmapにない対象だけshow_songで取得していた。要求する値が存在しないため、現compilerの構文制限を緩めるだけでは取得を省略できない。先行IDの有無も今回の25件を分けない。過去の別実験で見られた未観測IDを今回の失敗原因に転用しない。

CSVの対象loopはtitleとartistsの名前を取り出して新しい値をmapへ入れる。全rootの直接escapeは観測されず、一般的なlazy proxyを導入する必要があるとは結論しない。一方、最後のrootはpersistent namespaceに残るため、必要fieldだけのdictを完全返答として残す変換は許されない。

既存の `JoinedPublicReadAuthority` はplaylistの順序付きartist IDsと先行artist namesを結合する通常部品である。このsource範囲なら必要2fieldsが13/25でそろう。先行show_song返答を一切用いない場合は10候補、利用可能な返答だけ省く場合は13候補が残る。後者は、他の操作の返答を保存値に固定した有限のprefix感度分析である。未来の返答や省いた返答をauthorityに戻していない。元記録の最後の対象をfull取得する感度分析でも13候補だが、その対象が実loopの真の最終反復であるとは限らない。

13候補は実トークン削減でも新規性でもない。内部のAPI返答はPython内にあり、それだけでモデル入力にはならない。直接のtoken差はreceiptや予算通知の表示差を通じる。API上限を回避した先の処理は未観測で、成功まで続けた結果、元の安い失敗より費用が増す可能性もある。

次の検証では、通常joinと需要fieldの指定を比較対象にも与えた上で、限定loopへの自動適用が追加効果を持つかを問う。入口検査の失敗時はその位置の元loopへ続き、実行済みprefixを再実行しない。最終full rootとpartial後例外の扱いを先に合成テストで確認する。現時点で次のモデル比較は開始していない。

[ID・先行値の公開集計](../reports/P125_closed_diagnostics_20261026.json)／[全programの機構集計](../reports/P125_mechanism_diagnosis_20261026.json)／[全8条件の結果](P125_findings.md)。

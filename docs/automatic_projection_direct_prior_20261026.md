# Automatic field projection: 直接競合する先行研究の追加確認

2026-10-26 07:49 JST。約5分の追加Web調査。既存 `docs/automatic_projection_prior_scope_20261026.md` の8件とは別に、一次論文本文から近い3件を確認した。検索対象は LLM agent/code actions、generated Python、field demand/projection、cross-tool result reuse、semantic cache、partial evaluation、late materialization の組合せ。網羅検索や優先権の証明ではない。コード変更・実験・保存生成codeの実行・P123途中結果閲覧は行っていない。

**結論：今回確認した3件では「生成Pythonのfield需要を認識し、prefixで観測した別APIのfieldから追加full readを省き、永続Pythonの次cellへ渡るrootを元位置の実full取得で残す」という全条件の組合せは確認できなかった。一方、生成Pythonの自動変換、agentのデータ再利用、透明なtool cacheは明確に先行する。残るのは限定した実行規則・境界・会計を結び付けた具体差であり、新原理や初の技術という結論にはならない。**

## 追加3件と重複範囲

| 一次資料・確認箇所 | 重なる主張 | 今回との具体差／確認の限界 | 必要な強い通常対照 |
|---|---|---|---|
| **Quasar**, Mell et al., 2025 preprint, [本文 §3.1–3.3, §3.5, Appendix A/B](https://arxiv.org/html/2506.12202v1) | LLMが書くPython部分集合を実行前に別表現へ変換し、実行側が最適化する。変数代入・既知loop・条件を簡約し、API結果をprogramへ代入して後続計算を進める。「モデルに新言語を書かせず生成Pythonを自動最適化」だけでは差にならない。 | 主な最適化は依存が許す外部callの並列実行。§3.1の意味論は、外部callが入力だけに依存する仮定の下で、rewrite間の外部call集合を同じにする。既観測の別APIの部分結果で現在のfull readを消す規則や、永続Pythonの最後のrootを完全dictとして保つ規則は確認した本文にない。論文リンク先GitHubは取得時404で、code全体の不存在までは主張しない。 | 同じ通常Python interface、同じordinary complete cache、同じreceipt表示、同じcheckpoint。効果を「自動変換一般」に帰属させず、cross-API部分再利用に分ける。CPU並列化によるlatency改善をtoken改善と混同しない。 |
| **LLM-dCache**, Singh et al., 2024, [本文 §IIIとTable I](https://arxiv.org/html/2406.06799v2) | Agentの作業間で既読データを再利用し、loadを削減する。cacheはAPIとしてモデルへ公開され、モデルがread/updateを選択する。地理データのmetadata DataFrameを保持し、実画像は必要な処理まで読み込まない。データ局所性や遅いmaterializationそのものは差にならない。 | cacheキーはdataset/year、cache対象はDataFrame。確認した方式では、現在の生成Pythonのfield consumerを静的認識して既観測cross-API fieldへ置換する制御ではない。こちらの差は、モデルの明示cache操作選択を必要としない需要認識と完全root境界。Table Iではlatency削減時にもtokensが増える設定があり、backend削減からtoken削減は導けない。 | 同じ既観測情報を使える普通のpersistent Python＋full cache。interfaceを選ばせない便益まで主張するなら、既存の明示field/read-view方式との比較が必要。単にcache無しagentに勝つ比較では足りない。 |
| **ToolCaching**, Zhai et al., 2026 preprint, [本文 §3, §4.1, §5.1–5.2](https://arxiv.org/html/2601.15335v1) | tool層でrequestを透過的に受け、cache可能性と鮮度を判定し、結果を再利用する。「harness側で自動cache」「モデルのcache選択不要」は既存。 | §5.1のkeyはtool名と順序を正規化した全引数のhash、valueはtool結果と管理metadata。semantic featuresはcache可能性・TTL等の判定に使う。別toolのfield含意やPythonのfield需要でhitを作る方式とは本文上区別できる。semanticという名称だけでcross-API semantic view cacheと同一視しない。会議刊行は確認せずpreprintとして扱う。 | 同じtask隔離・失効条件でのordinary complete cacheを両arm共通にする。これが現在の対照の必須部分。LLMにTTLを推定させる機能を再実装することは、今回の機構比較の必要条件ではない。 |

右列の実装差と対照は本レビューの比較判断であり、各著者による今回方式の評価ではない。確認した本文に規則が見当たらないことと、先行実装全体に存在しないことは別である。

## 残せる主張と、先に潰すべき普通の説明

残る最も狭い主張は、**限定consumerの需要集合とtask内の公開API間契約を照合し、認識した中間readだけを省き、最後のrootは元のAPI位置で完全取得するharness変換の評価**である。一般Pythonの最適化、新しいsemantic cache、新しいlazy evaluation、全例外経路の意味保存ではない。契約破れで停止したcellは品質失敗を含む費用として扱い、復元成功と数えない。

この組合せの寄与を説明するには、次の普通の説明を分ける必要がある。現在のP125条件を途中変更する提案ではなく、結果を解釈し追加比較の必要性を判断する基準である。

1. **同一requestの通常cache効果**：ordinary complete cacheを両側へ入れる。Aが省いたfull結果をそのcacheへ無料登録しない。後続cellで必要になった完全取得まで通した累積差を見る。
2. **receipt indexの表示だけによるtoken差**：full API本文は元々Python内に留まる。Aで直接減る主なLLM可視量はreceipt metadata。両側で普通の省略・遅延提供を同条件にしたとき差が残るかが強い反証になる。read_spanに必要な参照は保持し、遅延取得に追加turn/APIが要れば全て計上する。これだけでtoken差が消えるなら、Aの固有価値はAPI予算節約側に限定される。
3. **もともと観測済みデータを普通に使う効果**：明示field-viewが同じ情報と契約で同じbackend削減を達成するなら、差は再利用能力ではなく既存生成codeへの自動適用。採用されやすさを主張するには適用率と選択不使用も必要である。

閉鎖済み静的診断の4/432 programという適用範囲は、現在は狭いcase studyであることを示す。静的eligibleは実partial hitや品質維持ではない。P124の保存返答replayは境界と会計を確認する証拠に留まり、live作業の反実仮想や全仕事token削減を証明しない。これらを合わせても新規性は未確立だが、近い先行があることだけで実験を打ち切る理由にもならない。

調査後の推奨：追加の文献探索を広げず、固定済み全仕事比較を終え、共通成功taskで実partialが起きたか・失敗を含む全logical tokensが減ったかを判定する。採択可能性の判断は、その結果と上記の強い通常対照への耐性を見て行う。

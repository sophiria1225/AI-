# P143原稿の出所と主張範囲

## 閉鎖資料と派生処理

本稿は既知4課題×TR/TDO、seed157の全8条件を一つのcohortとして扱う。固定source headは`85a8d3b6f5e676fe3ab6a94118a9f87c0d11e0c3`、plan SHA-256は`eb77daca5dbeb818577c09dee577d25caa41eae2ae095b5d5acf5deac5b13510`、固定source数は1,820。公開原資料はリポジトリの`materials/20261028_p143_results/`と`reports/P143_comparison.json`にある。

| 内容 | 出所・SHA-256 |
|---|---|
| 閉鎖材料manifest | `build_manifest.json` — `941e24ef3c8e3e0b080e33724a9768244b75da20ed3f9743d7849a63d91fc120` |
| 原集計 | `summary.json` — `1634c2ce24055ae01a25fe71b482d75ff64e18b1dbc621f4ca19cd87b6db848f` |
| 全8行 | `conditions.csv` — `d8325e9116fd235f5d5120003d18a1149910addbbc22525f3af59cc3e81e31a2` |
| 全役割の呼出し会計 | `model_calls.csv` — `07cbb3658721ce790838db97589284df8fd454b797f7774139274e0b295df9e0` |
| 元独立検算出力 | SHA-256 `835485c3e1dbaf96b81609710cfaa17d3cb84c67150a24f4ba99a44749938fc6`。公開版は`reports/P143_closed_metadata_review_public_20261028.json` |
| 最終判断 | `docs/experiments/P143_final_assessment_20261028.md`と`reports/P143_final_assessment_review_20261028.json` |

loaderは指定hash、全8identity、条件表と呼出し表の役割別既知使用量を照合する。原producer/auditor/checkerの再実行や意味内容の再監査ではない。結果表と図は集約数値だけから作り、課題本文、資格情報、生成コード、推論本文、評価の正解本文を含めない。元独立検算は38,478 checksでPASSし、別のscalar reviewは613照合を行った。これらは効用判定のPASSを意味しない。

## 数値と結論

全8評価の成功数はTR 3/4、TDO 2/4。既知小計はそれぞれ645,609、546,325トークンで、TDO写真操作のactor 1呼出しがunknownである。全体の既知小計は1,191,934。148モデル呼出しはactor134（既知133＋unknown1）とfocus14（全既知）である。cached inputを控除せず、不採用focusと失敗条件も含める。

固定集計は全8条件の会計が揃うまで**両方式の全体exact total、全体差、共通成功差をnull**とする。個々の既知条件の値は残す。共通成功は精算と返金で、個別差は精算+35,578、返金0。CSVは−84,040だが双方失敗である。この個別差を用いて固定common nullを書き換えない。写真操作の成功喪失により品質保持も満たさず、効用条件・development gateはともにfalseである。

TDOの第2object focus送信は3課題、差分採用と既知actor配信は精算・CSVの2課題だけ。差分を含む既知actor呼出しは13と6。精算はfocus−52に対してactor+35,630で総費用が増えた。写真操作は第二focusの既知出力が4,096トークンで、公開監査に第二採用判定はない。後続actorの使用量unknownと区別し、schema違反等の未記録原因を断定しない。

処置前prefixはstrict一致とcanonical一致を分ける。canonicalは検証済みtransport tool-call IDだけを全単射で置換し、内容・推論・関数名・引数・順序を意味的に正規化しない。作動したprefixのcanonical一致は固定監査から確認するが、処置後の軌跡やモデル内部状態の同一性、因果的な要素別効果を証明しない。

## 選定と限界

先行P142の既知4課題・同seed157・閾値16,384では両方式各3/4成功、各572,405トークン、差分発動0課題だった。その観測後に本P143の閾値8,192を選び、作業上限も1,800秒から1,200秒へ変更した。P142との横断差を閾値だけの効果へ帰属せず、旧cohortをpoolしない。更に以前のP141既知1課題・seed57の0.84%減は候補選定背景に限り、本稿の有効性根拠へ加算しない。

本稿は既知4課題、再使用seed157、単一モデル量子化による開発比較である。未見12課題は未使用。通常閾値下で保持＋明示object prompt＋ホスト結合のbundleを比較し、保持単独・prompt単独・結合単独の効果を分離しない。E/C発動則は今回の処置ではない。統計的非劣性、一般化、独立追試、品質・節約保証、新規性の確定を主張しない。

## 先行研究との関係

本文の7文献は旧v01から同bytes継承した。ACONには圧縮役の費用を含む評価があり、全role会計自体は新規性ではない。TokenPilotのキャッシュを考慮する金銭的評価と、本稿のcached input非控除の論理IOは別のendpointである。LongLLMLingua/ACON/TokenPilotとの直接性能比較はない。TCAは入力帰属のpreprintとして位置づける。

Mastra Observational Memoryのthread-scope `wrapObservations`は、既存observationsへ新observationsを追記する。[固定commitの公式実装](https://github.com/mastra-ai/mastra/blob/b59da216b35097e5adc14914e5cae76f811ee8ec/packages/memory/src/processors/observational-memory/observational-memory.ts)の同関数を確認しており、旧圧縮テキストの保持とappendそのものを新しい原理とはしない。resource-scopeやreflectionには書換えもあるため、Mastra全体がimmutableとも述べない。初出を網羅的に証明した調査ではない。

## 派生図と文章の来歴

方法図は結果前に描画したsource `c509223860da496ef624cc8e030e48e2d3f2549f02f38d1da1f0ed62d61ba352`の完成版を同bytes取り込んだ。費用図の最初の実データ描画ではunknown注記が隣の棒に近かったため、数値・8行・ハッチを変えずアスタリスクと脚注へ移した。最初の出力を私的に保持し、最終figure manifestが配布図を束縛する。実験の再実行ではない。

表generatorの初回はTRだけのper-arm exact totalを補助JSONに入れたが、固定full8規則との混同を避けるpeer指摘に従い、配布版では両方式のaggregate exact totalをnullとした。本文の全体差・結論は当初からnull/否定で、原集計は不変。生成された数値を保ち、最終本文は個別費用・役割・作動範囲を人手で説明した。`result_data_manifest.json`が生成元hashと最終表/本文の変換を明示する。

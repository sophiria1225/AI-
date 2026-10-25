# Automatic field projection の短い独立新規性レビュー

2026-10-26。限定ASTによるfield需要抽出、既観測cross-API partial再利用、最後のrootの完全値保持、ordinary complete cache共通対照を対象に、一次資料8件を確認した。これは約10分の関連機構の比較であり、網羅的な先行技術調査や「初」の証明ではない。コード変更、モデル/API/tokenizer/評価器実行、P123途中結果閲覧は行っていない。

**結論：基本的な最適化機構の新規性は主張できない。ただし、現在の生成codeの需要と既観測API間契約を結び付け、永続interpreterの境界と費用を扱う具体的なharness制御は、検証する意味のある組合せである。既存技術があることだけで実験を中止する理由にはならない。現段階で、その組合せが採択に足る新規性を持つとも断定できない。**

## 一次資料との対応

| 一次資料 | 既にある仕組み・新規と呼べない点 | 今回との比較対象 |
|---|---|---|
| [Weiser, Program Slicing, 1984](https://www.cs.kent.edu/~jmaletic/cs63901/readings/Weiser84.pdf) | データ/制御依存を解析し、指定した観測に必要なprogram部分を自動抽出する。必要なfieldだけを静的に調べる発想自体は新しくない。 | 今回は一般slice計算器ではなく、限定loopのconsumer認識器。API返答の取得を省けるかを外部契約と結合する。 |
| [Polars公式: Optimizations](https://docs.pola.rs/user-guide/lazy/optimizations/) | queryが必要とする列だけscanするprojection pushdown、共通subplanのcache、slice省略は通常のquery最適化。 | 今回はDB/query engineへprojectionを渡すのでなく、Python sourceと異なるAPIの既観測返答からcallを省く。query形式なら通常のoptimizerで説明できる部分を明示する。 |
| [Dar et al., Semantic Data Caching and Replacement, VLDB 1996](https://www.vldb.org/conf/1996/P330.PDF) | cacheの意味記述から既充足部分と不足部分を分け、不足がなければserverアクセスを省く。要求文字列が同一でない再利用そのものは既存。 | 今回のcross-API関係は手で固定した公開serializer契約。一般的な意味関係の自動発見、新しいcache理論、embedding近似cacheではない。 |
| [Launchbury, A Natural Semantics for Lazy Evaluation, POPL 1993](https://launchbury.blog/wp-content/uploads/2019/01/semantics-of-lazy-evaluation.pdf) | 非strictな評価と共有を明示的heapで扱う。必要になるまで評価しない・繰り返し評価を避ける原理は既存。 | 今回の中間full readは後で必ず評価するthunkではなく、限定通常経路で不要な取得の除去。後続完全利用の費用は無料にしない。 |
| [Stadler et al., Partial Escape Analysis and Scalar Replacement for Java, CGO 2014](https://www.ssw.uni-linz.ac.at/Research/Papers/Stadler14/Stadler2014-CGO-PEA.pdf) | escapeしない経路ではfieldに分解し、escapeする経路には実objectを残す。『内部は部分値、外へ出る時は完全object』という一般構造は先行する。 | 今回はremote readとcell間namespaceが対象。最後の反復の元位置で普通full readを残すのは保守的な境界方針で、独立した新escape-analysisアルゴリズムではない。 |
| [Wang et al., Executable Code Actions Elicit Better LLM Agents / CodeAct, ICML 2024](https://arxiv.org/html/2402.01030v4) | Python codeをactionとして複数toolを組み合わせ、interpreterと複数turnでやり取りする枠組みは既存。 | 今回はcode action採用そのものではなく、既に生成された通常codeへharness側で限定変換を適用する点を評価する。 |
| [Anthropic, Code execution with MCP, 2025](https://www.anthropic.com/research/code-execution-with-mcp) | 大きいtool結果をcode内でfilter/aggregateし、必要な出力だけモデルcontextへ返す実装を説明している。『tool結果を全てLLMへ入れない』ことは新しくない。 | 例示手法は取得結果をcodeで処理する。今回の候補は既観測fieldが十分なら追加のfull read自体を省く。モデルが新interfaceを選ぶことを必要としない。 |
| [Chaturvedi et al., DTOC, 2026 preprint, §3.2–3.3](https://arxiv.org/html/2609.26121v1) | 実行済みtool出力を外部保存し、agentがenable/disableしてcontextをplaceholderへ置換・復元する。可逆なtool-output管理も既存。 | 今回は表示対象の選択より前のAPI実行制御。省いたfull返答は存在しないので、DTOCのような既保存出力の無料復元とは違う。 |

表の右列は資料と現実装を比較した本レビューの推論である。各資料が今回と完全同一の組合せを扱っていない、というだけで世界初とは言えない。

## 検証可能な技術的主張

最も具体的な対象は、**現在の生成Pythonから読み取りfield集合を認識し、同じtask/revisionの成功した過去返答だけでその集合が満たされる場合に中間readを省き、未知の次cellへ渡る最後のAPI rootを完全dictとして残す制御**である。通常complete cacheを両armに入れ、その上で追加効果を測る。

実行規則は、現在codeの需要集合D、prefix内の部分値P、公開契約が与える完全返答Fに対し、PがFのDへの射影に一致し、consumer/alias/型条件が認識範囲内なら中間反復でPを使う、というもの。最後の反復は元のfull call、missは普通call、未知構文は実行前に普通codeへ戻す。実partial使用後の例外は復元成功にせず停止・失敗計上する。この条件付き制御と境界の検査は説明できるが、任意Python・任意API・全例外経路の意味保存ではない。

追加価値の候補は次の3点である。

1. モデルが明示的なprojection APIやlazy proxyを選ばなくても、通常の生成codeへ作用する適用性。
2. 単一call単位のfull cacheでは得られない、既観測の異なるAPI返答からの部分再利用と、cell境界での実full root保持の結合。
3. 省いたfull返答が後続complete cacheに存在しないこと、後続full利用には費用がかかること、control費用と失敗を含めることを一つの実行・比較系で扱う点。

いずれも単独で新原理とはしない。とくに公開契約は既存P37由来であり、今回の新しい契約発見とは書かない。現在の1組のAPI・限定loopだけで広いAPI汎化や最適な取得計画を主張することもできない。

## 強い通常対照と短時間で必要な証拠

最低限の対照は現在の`ordinary complete cache only`でよい。ただし、token削減の説明には、普通のCodeAct処理やreceipt metadataの短縮でも得られる部分を分ける必要がある。現runnerではfull API本文は通常interpreter内に留まり、実APIごとの短い`api_receipts`がLLM履歴へ残る。Aの直接のtoken効果はまずこの列と将来入力での反復分、間接効果はAPI予算不足や補修turnの変化になる。『大きいAPI本文を丸ごとcontextから取り除いた』とは書かない。

短時間での判断基準:

- 固定replayでordinary cacheを上回る実partial利用、stdout・最後のfull root・plain namespaceの一致、後続完全利用の費用を確認する。これは機構が作用した証拠で、task品質や新規性の証明ではない。
- 次の全仕事比較では同じbudget/seed条件で最終独立評価、logical input+output総量、API数、実partial率、fallback率、契約破れを併記する。失敗・再試行・summary等も分母/費用から外さない。
- token差がreceipt短縮だけで説明されるなら、その事実を明示する。一般的なreceipt整形だけで同等のtoken効果が得られる場合、Aの技術的価値は追加API節約や予算不足回避にある。
- 少数の適用例だけなら限定的case studyとして扱う。対象外codeで無理に変換範囲を広げ、期限内に未検証な意味保存を約束しない。

原稿の仮置き主張は「既観測API間契約と現在codeのfield需要を用いる限定harness変換を実装し、永続Python境界と全仕事の精度・費用を検証する」が妥当。現時点では「新しいlazy evaluation」「新しいsemantic cache」「汎用的・losslessな精度保証付きtoken圧縮」「初の技術」とは書けない。

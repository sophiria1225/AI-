# 初回の関連研究確認

2026年10月20日の本文・コード追加確認は末尾に記載する。最初の確認時点で未確認だった範囲を、後の調査と区別して残す。

確認日：2026年10月13日。近接性を調べる初回調査であり、網羅的レビューや全手法の再現ではない。今回の研究の主目的は「品質条件を満たした全試行総トークンの削減」。動的構成、部分集中、介入価値予測の一般原理は新規性にしない。

| 研究・資料 | 今回確認した範囲 | 重なる点 | まだ検証すべき差 |
|---|---|---|---|
| [MaAS](https://proceedings.mlr.press/v267/zhang25bi.html)／[著者原稿](https://arxiv.org/html/2502.04180) | ICML 2025の公式書誌・概要、著者原稿の構成分布とトークン費用を含む目的式 | 問題に応じた構成選択と費用削減。「構成を変えて節約」だけでは差にならない | 完了途中の成果物・責任を保った引き継ぎ、共有だけの比較、品質条件付きの全試行費用。原実装の再現は未実施 |
| [Asynchronous Partial Overlay](https://jair.org/index.php/jair/article/view/10451) | JAIR 2006の公式書誌・概要 | 関連部分を仲介役へ集めて解く原理 | LLMの有限コンテキスト、未知の依存、移管・再入力費用の扱い。本文全体と改良研究・保証条件は未確認 |
| [TDAG](https://arxiv.org/html/2402.10178v2)／[掲載DOI](https://doi.org/10.1016/j.neunet.2025.107200) | 著者原稿の方法節。Crossref登録情報でNeural Networks 185、107200、2025年5月を確認 | 実行結果を受けた後続作業の変更。「初期だけ動的」と扱わない | 進行中の作業状態・更新責任の移管、利益と費用の測り方。出版社ページは取得エラーで、掲載版本文と公開原稿の一致は未確認 |
| [ATM](https://arxiv.org/html/2607.20488) | 著者公開原稿の3.1〜4.2節中心。正式採録は未確認 | 実行指標に基づく組織変更、状態整理、品質・効率による採否 | 構造変更はshadow windowで候補を評価する設定と読める。同一依頼の途中状態を移す問題と機能比較が必要。ツール修復は同一タスク中にも行うため混同しない |
| [Calibration Is Not Control](https://arxiv.org/html/2606.21399v1) | 著者公開原稿の保存状態からの分岐、動作条件付き価値、方策評価の方法節。正式採録は未確認 | 失敗予測と介入効果を分けること、同じ状態からの分岐、効果を予測して選ぶこと | 本研究固有の作業・責任再編に利益が残るか。分岐や利益予測自体を独創性としない |

MaASの公式会議録PDFは今回のブラウザ取得で読めず、方法の確認には著者原稿を使った。掲載版と著者原稿の全文一致を保証しない。他の候補であるChain of Agents、CoALA、GCC、APO改良、通信設計などの詳細比較は未完了。

MaASの著者原稿3.2節を追加確認した。式7・9の構成選択は問い合わせと前層の選択演算子を条件とし、逐次サンプリングの完了後に構成を実行すると記述されている。これは「作業成果物や担当責任を、同じ依頼の実行途中に移管する」という差分を調べる手がかりになる。ただし演算子自体に複数LLM・ツール処理が含まれ、コードは未検証なので、実行中の動的挙動が一切ないと一般化しない。[方法節](https://arxiv.org/html/2502.04180#S3.SS2)

TDAGの正式題名は *TDAG: A multi-agent framework based on dynamic Task Decomposition and Agent Generation*。書誌の取得結果は`records/sources/tdag_bibliography.json`へ保存した。[Crossref登録情報](https://api.crossref.org/works/10.1016/j.neunet.2025.107200)

## この段階の判断

一般的な「動的な分担」「状態の統合」「費用を考えて切り替える」は既存研究に近い。現在の計画を完全に新しい方法として確定できない。一方で、実際の作業中にどの負担が生じるかを観測し、情報整理・中央調整・作業移管を同じ条件で比べる意義は検証可能である。

E0で分担の利点と調整負担を観測し、E1で既存の単純な改善を超える差が残るかを確認してから技術の主張を決める。論文の新規性が成立したと結論する段階にはない。

## 2026年10月20日 本文と公開コードの追加確認

MaASの公式掲載PDFを取得した。コードも`987f3c1bc9a96e844fe090db3791446e3ef0f5c7`に固定して読み、HumanEvalのテスト用Workflowは最初にcontroller.forwardを呼び、返された層ごとの演算子を順に実行することを確認した。Controllerは問い合わせと以前に選んだ演算子の埋め込みを用いる。この経路では途中のテスト結果を受けてControllerを再度呼ぶ形ではない。ただしTest、SelfRefine、最終テスト不合格後の再生成はあるため、「実行中の適応がない」と一般化しない。[掲載情報](https://proceedings.mlr.press/v267/zhang25bi.html)、[固定版Workflow](https://github.com/bingreeky/MaAS/blob/987f3c1bc9a96e844fe090db3791446e3ef0f5c7/maas/ext/maas/scripts/optimized/HumanEval/test/graph.py)、[Controller](https://github.com/bingreeky/MaAS/blob/987f3c1bc9a96e844fe090db3791446e3ef0f5c7/maas/ext/maas/models/controller.py)。

TDAGは`ed5ccb3f682b9f27021faa16159e300c7652c417`を確認した。run_increでは全体要求・完了作業・現在作業から担当を生成し、結果を親へ返す。再帰的な担当生成もある。run_adaptには失敗後の再分解があるが、これをTDAGの全報告設定と同一視しない。差分候補は「動的な分解」自体でなく、既に進行した複数担当の作業・成果物・更新責任をまとめる追加効果になる。[方法節](https://arxiv.org/html/2402.10178v2#S4.SS1)、[固定版の実行経路](https://github.com/yxwang8775/TDAG/blob/ed5ccb3f682b9f27021faa16159e300c7652c417/run/run_incre.py)。

GCC v2の方法節では、文脈の分岐・統合に加え、コードと記憶の版管理、別セッションへの引き継ぎを扱っている。従って「状態をまとめる」「引き継げる」だけでは差分にしない。評価設定には本文の32,768と表の327Kという入力長表記の不一致があり、表のMax Tokenはアクセス可能なアーカイブ量も含む説明になっている。今回の全呼び出し入力＋出力の総予算と同じ数値とは扱わない。費用の分析も記載されているため「費用を評価していない」とは言わない。[方法・評価設定](https://arxiv.org/html/2508.00031v2)。

以上は読み取り確認で、これらのコードの再実行・性能再現ではない。GCCの当該版と対応する公式実装、APO改良の保証条件、ATMとの具体的な構成比較は未完了。取得原本のハッシュは`records/sources/20261020_near_work/`、コードの版は[公開記録](../reports/related_work_code_revisions.json)へ保存した。

次の比較実装では、単純な情報整理と中央調整を残す。GCC風の記憶の統合で同じ改善が得られる可能性を先に検証し、担当責任の変更に固有の効果が確認できた場合にのみ、そこを提案技術の中心にする。

APOは原論文の前提・4.1節も確認した。既知の有限領域と制約を持つ分散CSPで、仲介役が関連部分を集中して解き、外部との衝突を受けて関係する範囲を広げる。今回のLLM作業への適用では、制約を完全に列挙できることや、内部の探索が正しく完了することを引き継げない。[JAIR 2006掲載PDF](https://jair.org/index.php/jair/article/download/10451/25053)。

さらに、*Completeness and Performance of the APO Algorithm*（JAIR 33、223–258、2008）の概要と6.1節を確認した。原APOの一部の場合に停止しない問題を示し、CompAPOへ修正している。仲介対象全体の確保と、古いセッションの遅延メッセージを区別するIDも扱う。arXivへの登録は2014年で、掲載年とは異なる。従って原APOの保証を無条件に引用せず、版と前提を区別する。[著者提供の掲載原稿](https://arxiv.org/pdf/1401.3450)、[書誌・DOI](https://arxiv.org/abs/1401.3450)。

実装への示唆として、移管時の停止境界・版ID・遅延出力対策は共通の基盤機能として扱う。これらを追加しただけでは新規性としない。2012年のImproving APO本文、保証の全証明、実装再現は未完了である。

GCCの追加検索で[ImprintLab/git-context-controller](https://github.com/ImprintLab/git-context-controller)などの実装候補を見つけた。確認時のdefault branchはdev、作成日は2026年7月24日。READMEのv2という名前だけでは、論文v2の評価コードと同一だと確認できない。論文の著者提供HTMLから対応する実装の明示的リンクは確認できておらず、公式再現コードとしてまだ採用しない。GitHubの名称・機能が似ていることと、論文の手法・予算・実験条件を再現することは区別する。候補のAPI取得記録は`records/sources/20261020_near_work/gcc_candidate_repository.json`に保存した。

## 実行中の構成変更に直接近い追加候補

2026年10月20日確認。下表は本文確認とコード読み取りであり、性能の再現ではない。

| 研究・掲載先 | 確認した機構 | 本研究への影響・残る確認 |
|---|---|---|
| [Multi-Agent Collaboration via Evolving Orchestration](https://proceedings.neurips.cc/paper_files/paper/2025/hash/f1320d2e2842169c6fc89dcbd80e94d0-Abstract-Conference.html)、NeurIPS 2025 | 状態更新のたびに中央方策が次の担当を選ぶ。品質と費用を用いた学習、トークン費用の分析もある。著者原稿v2の2節・付録A.1–2を確認 | 「実行途中に選ぶ」「費用を減らす」は既出。進行した作業・成果物・更新責任を移す効果が、担当選択だけを超えるか比較する |
| [DynTaskMAS](https://ojs.aaai.org/index.php/ICAPS/article/view/36130)、ICAPS 2025、35(1):288–296 | 動的な依存グラフ、非同期実行、共有文脈、実行中のワークフロー調整。著者原稿v1のIII–IV節を確認 | 「依存に応じて作業構成を変える」も既出。候補生成・評価関数の具体実装は未確認。複数GPUの並列時間改善を、今回の直列実行・全入力出力費用へ置き換えない |
| [Benefits and Limitations of Communication in Multi-Agent Reasoning](https://www.mhahn.info/bibtexbrowser.php?bib=hahn.bib&key=anonymous2026benefits)、著者書誌でICLR 2026を確認 | 著者原稿v2の2–3節で、限定したTransformerモデルと課題における通信・計算・深さの関係を確認 | 理論上のグラフの大きさ・深さは、履歴の再入力を含む今回の総トークンと同一ではない。実リポジトリの作業移管に対する保証として引用しない |

Puppeteerの論文が示す公式ブランチを`b24e6e6bd00bb04d317e0447cb7acb1e4973c83a`へ固定し、`ReasoningPath.step`を読んだ。行動後にglobal_infoを更新してpolicy.forwardを呼ぶ経路と、複数担当を選び分岐する経路がある。「一回だけ構成を選ぶ方式」として比較しない。この公開コード版が掲載実験の正確な版であることは未確認。[固定版の実行経路](https://github.com/OpenBMB/ChatDev/blob/b24e6e6bd00bb04d317e0447cb7acb1e4973c83a/puppeteer/inference/reasoning/path.py)。

取得原本・コード7ファイル・ハッシュは`records/sources/20261020_runtime_reorganization/`へ保存した。掲載PDFと公開原稿の全文一致、学習費用を含む完全な費用監査、コード実行は未実施。DynTaskMASの掲載ページはブラウザで確認できたが、ローカル取得は失敗した。通信の論文はOpenReview本文を取得できず、2026年7月14日付の著者原稿v2を読んだ。[Puppeteer本文](https://arxiv.org/html/2505.19591v2)、[DynTaskMAS本文](https://arxiv.org/html/2503.07675v1)、[通信の本文](https://arxiv.org/html/2510.13903v2)。

次の実装では、固定分担と共有だけの対照を先に作り、その後の動的方式の比較候補にPuppeteerを加える。依存グラフだけの動的化も差分として扱わない。各論文の全基盤を直ちに移植する案は、まだ分担による現象を観測しておらず、モデル・ツール・予算も変わってしまうため先行させない。現在のQ3単一方式の2失敗は、移管方式が必要である証拠にはならない。

## Flowとの重複と指標の対照確認

*Flow: Modularized Agentic Workflow Automation*（ICLR 2025）の掲載本文3節・付録B.6を確認した。途中の進捗・出力を使った作業の追加・削除・変更・再実行・担当変更を扱い、候補を並列性と依存の指標で選ぶ。現在の計画に直接近い比較対象である。付録の費用比較は実時間を用いており、今回の全入力＋出力の予算と同一には扱わない。[掲載論文](https://proceedings.iclr.cc/paper_files/paper/2025/file/ba84da6921f3040b74ee163aa7451f53-Paper-Conference.pdf)。

論文が示す公式リポジトリの`1bbfe1e699e6f35d5d422306c9a5bd637da84759`を読み、実行中の処理を待ってからworkflowを更新する経路、状態・履歴・担当情報を持つ作業管理を確認した。したがって「安全な区切りで再割り当てる」「状態を持つ」ことだけも差分にしない。このコード版と掲載実験との正確な対応は未確認。[実行境界](https://github.com/tmllab/2025_ICLR_FLOW/blob/1bbfe1e699e6f35d5d422306c9a5bd637da84759/flow.py)、[作業構造](https://github.com/tmllab/2025_ICLR_FLOW/blob/1bbfe1e699e6f35d5d422306c9a5bd637da84759/workflow.py)。

依存の観測に既存指標をそのまま採用できるか、4頂点の2つの人工DAGで確認した。直列鎖と、その到達関係を変えず冗長な辺を足したDAGでは、次数の標準偏差は0.5から0へ下がる。固定コードの並列性計算も、複数経路から同じ頂点を再訪するため、この例で1から2へ変わった。実際の層幅は両方とも各層1である。グラフの代理指標を、観測した作業依存の強さと同一視しない理由になる。[計算記録](../reports/flow_metric_controls.json)、[再実行スクリプト](../scripts/check_flow_metrics.py)。

実行したのはハッシュで固定した2つの指標関数だけで、原ソースのimport・初期化・LLM呼び出しは行っていない。人工例での指標確認から、Flowの報告性能全体が誤りだとは結論しない。原本7ファイルと掲載PDFは`records/sources/20261020_runtime_reorganization/flow/`へ保存した。完全な比較では、原論文との版差・指標実装を区別したうえで、共通の予算と評価へ接続する必要がある。

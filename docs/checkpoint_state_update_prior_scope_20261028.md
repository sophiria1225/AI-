# P144: checkpoint state update の先行範囲と比較設計

2026-10-28。新しいモデル実験前の限定レビュー。一次資料の下記節と既存の公開ソース・閉鎖結果だけを参照し、予約12課題、生成本文、評価器本文は読んでいない。旧結果・台帳は変更していない。

## 判断

**保持・更新・削除とホストによる適用は既知の仕組みであり、それ自体を新アルゴリズムとはしない。** 一方、P139–P143の不変な旧要約への追記とは異なる更新規則なので、同一条件の強い再帰要約および追記対照に対する効用仮説として試す理由はある。既知技術との重なりだけで、この別規則の効用まで否定しない。新規性・品質維持・費用改善はいずれも実験前には未成立である。

## 一次資料との重なり

- [Mem0 v1 §2.1・付録B Algorithm 1](https://arxiv.org/html/2504.19413v1#S2.SS1): 新しい事実と類似記憶からADD/UPDATE/DELETE/NOOPを選び、ホストが実行する。今回の操作語彙と直接重なる。Mem0は対話の長期記憶抽出・検索を扱い、今回の単一課題中の限られたcheckpointとは実験範囲が違う。§4.5の記憶量を今回の全role論理入出力と同じ指標にはしない。
- [SKILL.state v1 §3.1–3.2、Algorithm 1](https://arxiv.org/html/2608.26263v1#S3.SS2): モデルがJSONのkey変更・削除を出し、runtimeが検査後にnull削除付きdictionary mergeを行う。型付き更新、決定的適用、状態の上限だけでも独自性にはならない。毎stepの行動との同時出力、分野別状態schema、履歴の非再提示という設計と、今回の時々のfocus更新・直近raw履歴保持を区別する。
- [Mastra Observational Memory「Reflections」](https://mastra.ai/docs/memory/observational-memory#reflections): 新観測を追記し、別閾値で全観測logを書き直して圧縮する。永続的な追記と有界化の組合せは既存である。今回のitem単位patchと同一とはしない。公式docsの取得時点を参照し、製品版を実験再現したとは扱わない。
- [Letta memory blocks「structure」「Modifying a block」「Deleting a block」](https://docs.letta.com/v1-sdk/memory/memory-blocks): 識別子と文字上限を持つ編集可能なcontext block、置換・削除を提供する。外部ホストからの編集や上限付き記憶も既知。公式docsの全block置換を、今回のitem単位編集と混同しない。
- [ACON v3 §3.2–3.3・§4.5 Practical efficiency trade-off](https://arxiv.org/html/2510.00615v3#S3.SS2): 閾値で履歴を要約に置換し、失敗対比から圧縮指示を最適化する。actorとcompressorを含むend-to-end費用も既に評価している。全仕事会計それ自体は新規性ではない。今回の再帰対照、事後の候補選択、compressor費用を含める必要性に直接関係する。

これは限定した重複確認であり、網羅的な新規性証明でも、他方式の再現実験でもない。

## 既存repoとの差

`native_ledger_memory.py` は既に通常のincremental working ledgerを実装し、旧ledgerと新規spanを与えて全ledgerを生成し直し、不正な出力では旧表示を保つ。`context_preservation.py` のLEDGER_PROMPTも、前の記憶は誤り得るとして観測に基づく修正を要求する。P6はこの更新費と局所短縮を調べており、更新費を後続利用で回収できる保証はなかった。

P139の`RepresentationCheckpoint.close_separate/decide`は、再帰なら新objectへ置換し、deltaなら旧noteを不変に残して新noteを付加する。P140は第2delta出力を単一objectと明示するprompt変更で、削除や旧item更新は行わない。既存testsは初回同bytes、旧note保持、8192文字・各field32項目・1項目2048文字、未送信/不採用、最大2機会を既に検査する。

P144の具体的差分は、第2focusに旧itemのfield内indexを示し、各fieldの`keep/update/delete/add`を完全に検査して、ホストが**1つの通常要約object**を構成する点である。keepは旧文字列を再生成せず同bytes保持する。例として、旧状態に「残りA,B」「出力先X」があり、新観測がAの完了を支持する場合、APPENDは旧記述＋「A完了」を残すが、UPDATEは「残りB」へ更新し「出力先X」をそのまま保持できる。再帰要約も同じ最終内容を生成し得るため、意味上の到達可能性が新しいのではなく、再出力と残留の制御が比較対象となる。

## 最小3armsと成立条件

1. TR: 現在の再帰置換を強い通常対照として保持。
2. APPEND: 明示object差分を旧要約へ追記する現方式。UPDATEと同じtrigger・budget・初回入力で比較。
3. UPDATE: 第2focusだけを明示的item編集契約へ変更し、ホスト適用後に同じ採用検査を行う。

承認された案は既知4課題×3arms、固定seed257、共通8192閾値・作業1800秒・最大2機会。seedは未使用であっても、課題と機構選択は過去結果に基づくため独立未見確認にはならない。循環順は実行順交絡を軽減するが、4課題では完全な順序均衡や統計的非劣性を保証しない。

各旧indexをkeep/update/deleteのどれかに厳密に1回だけ分類し、pendingの旧state hashへ束縛する。省略を暗黙の削除にしない。重複・不明index・bool index・旧state不一致・不正な型・上限超過は操作全体を拒否し、途中適用しない。旧順序を保って追加を末尾に置く。生成上限4096、適用後8192文字・field32項目・item2048文字を緩めない。known-paidの不正出力も費用へ入れ、追加修復呼出しを自動で行わない。

初回focusとactor入力は3armsで同じ。indexはfocus側の編集参照であり、不要なactor表示差を追加しない。採用時には指示・tools・予算通知・raw最近2turnを含む全actor入力を計数する。状態の構造適合、局所shorter、旧文字列保持は、内容の正しさや将来必要な情報の保存を保証しない。

主比較UPDATE対TRと、機構比較UPDATE対APPENDを別々に固定する。全条件を残し、成功喪失0・全件usage既知・全仕事費用減・共通成功費用減を満たすかを判定する。実際の非自明なupdate/deleteと採用後actorへの配信を、単なるkeep/noopやoffer数から区別する。prefixの不一致・非発動・不正patchも除外せず報告する。strict/canonical prefix確認は派生metadata依存を明示し、処置後の全軌跡同一や単独因果効果に拡張しない。

12×(1800+60+60+30+60)=24,120秒、6時間42分がcell上限の合計である。16:15開始なら単純上限は22:57だが、共通起動・preflight・activation・回収等は別に予約する必要がある。23:15モデル停止と23:59報告は、その全体deadlineの整合確認なしに保証できない。入らない場合にtaskを都合よく減らして全12完了としない。

## 原稿の肯定的な核を選ぶ場合の境界

P123の通常別呼出し反復は4/4成功、unknown0で単発より12.07%少なかったが、その差はCSVに集中し、同時反復候補の両対照gateはfalseだった。P66の30.15%/26.00%減は同じ既知写真1課題の2構成・各1回と手書き要求契約の範囲であり、新手法・一般品質維持ではない。事前strict prefix一致不成立も残す。

これらを局所的な肯定例として説明することは可能だが、P128の成功喪失・unknown2・全体gate false、P143のTR3/4対TDO2/4・unknown1・固定全体/common nullを省いて、一般的な有効性が確立した物語にしない。異なるcohortの費用を合算せず、普通の反復要約・終了制御の有用性と、新UPDATE候補の未評価を分ける。今回の新試験も旧失敗を置換しない。

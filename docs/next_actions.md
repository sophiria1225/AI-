# 次の作業：P135全6の閉鎖と費用・品質の検算

2026-10-27朝のユーザー指示に従い、就寝中も実験を継続する。通常メッセージでは止めず、明示停止に従う。原稿本文はユーザーが執筆する。条件・有限予算・source・両CIを固定し、全仕事のlogical input+outputと公式課題成功を評価する。

P133は全4条件と所有serverを閉鎖した。producer監査ではseed57は両方式成功・各332588 tokens/API76/model31/focus2、seed157は両失敗・各102035 tokens/API80/model10/focus0。各方式1/2成功・全体434623 tokensで同じ、不明0、予測による要約見送り0、gate false。普通の制御校正による削減差はなかった。報告処理は固定public sourceに含むmaterials6件/papers1件を拒否して失敗（audit/session/report=0/0/1）。別のdata-only recoveryで全4資料を回収済み、追加model/API/eval/tokenizer0、原source/失敗は保存。別系譜の独立検算16788項目と図の相互確認はPASS。全4条件・失敗・復旧を[PR #542](https://github.com/sophiria1225/AI-/pull/542)で公開済み。[P133の結果と限界](experiments/P133_findings.md)。

P134の待機queueはこの報告失敗を検知し、モデル・server・preflight・taskを開始せず停止した。旧P134のsource/plan/queue失敗を保持し、同じ6条件をP135別namespaceで実行する。変更対象は前件復旧の検証と報告path検証、実行識別子であり、機構・guide・tools・科学条件・予算はP134と同じ。P133の成否に基づく条件やseedの選択変更はない。P135は2026-10-27 08:15:47 JSTに開始した。08:18:19 JST時点でpreflight/activation成功、最初のnative actor requestとmodel slot処理中を確認し、全6条件の有限比較を実行中。途中の成否・費用・生成本文は未読のまま閉鎖を待つ。source `d87880f`、plan `5a5b5338`、1498 source、同head両CI成功。[P135仕様](experiments/P135_whole_task_observed_obligations.md)。

P135は従来のraw anchor／残件数のみ／対象IDと不足fieldの3方式×seed57/157、既知CSV1課題の6条件。全方式でtyped観測とcaptureは共通、主2方式のguide/query能力は同じ、rawは元P123 interfaceを保持する。accepted checkpoint後の次actorへ一度だけ有料表示し、open/unknown列挙を残件0にしない。各80calls/450000tokens/1800作業秒/API80、server6時間・18:00 JST上限。P133復旧証明とP134モデル0、source固定、両CI成功を起動前に確認済み。全6条件の閉鎖後に集計・独立検算する。

次の比較では、対象列挙の効果とfield対応付けの効果を区別する。全pending対象の不足fieldが同じなら、集約件数からfield maskは一意であり、field情報が増えたとは言えない。既存FOCUS等にもentity保持・救済がある。新規性、一般品質維持、新方式の全仕事token削減は未確立で、少数seedや共通成功だけを一般効果へ広げない。P123の通常rollingは既知4/4成功で単発比12.07%減を観測済み。原稿用の全条件・失敗・不明費用・機構到達を整理する。

P133開始snapshot189台帳/2290束縛と、その後のglobal190/2300を分離する。P134の未実行予約snapshot190/2300も保存し、P135の開始snapshotも190/2300で固定し、その後のglobal増加を遡及しない。元run/prepと失敗は変更しない。モデルは単一serverで直列、保存された生成Pythonはhost実行しない。保留12シナリオは要求文・データ・正解を未閲覧のまま保つ。

変更先はsophiria1225/AI-と[専用Project1](https://github.com/users/sophiria1225/projects/1)のみ。raw prompt・reasoning・生成task code・課題値・認証・評価器本文は公開しない。原稿執筆・教授への連絡・投稿は行わない。

1. P135全6を固定条件のまま実行し、所有serverの閉鎖まで確認する。
2. 公開済みの[P133全4結果](experiments/P133_findings.md)を、機構未発動・費用差0の閉鎖結果として原稿用の判断へ反映する。
3. P135閉鎖後に全条件の費用・品質・表示到達を監査し、追加表示の実測入力負担とfield対応付けの冗長性を補助分析する。
4. 正の結果でも対象ID列挙とfield対応付けの寄与を区別する。保留12シナリオは手法・強い比較方式・予算・評価項目の固定前には開かない。

[P135開始記録](experiments/P135_execution_start_20261027.md)。

# P144R1の再開記録：停止前に未実行だった10条件だけを継続

2026-10-28、利用者が実験再開を明示した。停止前の2条件を再生成せず、元の固定12条件のうち未実行だった10条件を同じ順番で一度だけ実行する。

## 観測時点の状態

16:00:18 JSTに継続用の背景処理を起動。16:03:58 JSTの運用確認では新規分 0/10条件を評価完了し、`BOC_P144R1_01_THRESHOLD_DELTA_UPDATE` が処理中だった。要求file 3件・応答file 2件の存在と、所有する単一model slotが処理中であることをroot担当が確認した。生成開始そのものの時刻を16:03:58と同定するものではない。これは時刻付きの運用確認であり、成功維持・token削減・新規性の結果ではない。本開始記録の作成では途中の成否・usage・生成本文を閲覧していない。通常の会話では背景実行を止めず、利用者の明示停止に従う。

電源断前の内訳は、実行完了2条件、うち評価済み1条件、未実行10条件だった。再開時に保存466試行ファイル・26 DBファイル等の一致を確認し、評価待ちだった追記方式1条件を固定公式評価器で1回だけ評価した。モデル生成や課題操作は追加していない。元のP144計画・試行・停止報告は保持する。

## 固定条件と時間

MiniMax-M3のIQ4_XS量子化をllama.cppで実行する。既知4課題に対する通常再帰要約／追記／明示的状態更新、model seed257・world seed42、8,192 token閾値・最大2要約機会を元計画から継承する。各条件80 model calls・450,000 logical input+output tokens・作業1,800秒、setup60秒・cleanup60秒・idle30秒・評価60秒。写真API160、他3課題API80。成功率だけでなく要約・失敗・cached inputを含む全仕事費用を測り、不明費用を0補完しない。

新規分は10条件・最大800 model calls・4,500,000 tokens・880 API・10公式評価・20要約。保存済み条件の評価1回は別枠。追加seed、同条件反復、結果による条件変更は行わない。新しいserver leaseは21,000秒、モデル絶対期限は本日23:15 JST、結果処理期限は23:59 JST。

source commitは `4d74325b555a7eeb872807c3eab7b39c4da955e1`、継続計画は `configs/P144R1_continuation_v01.json`、SHA256は `d2b5345351cc70c5d9f7ae6d01af3e96103702ed180bdfb57fb2da272d51efbd`。3,799 source files、開始時214台帳・2,905束縛を確認。ローカル全体3,358件・継続関連30件の検査が成功した。固定headのpush／pull_request CI（各attempt1、各13 step）はともに成功。新serverで12初期入力・6要約template・3actor表現の計21 native計数とactivationを完了した。計数段階のモデル生成・課題API・評価は0件。検査成功は実験効果の成立を意味しない。

## 記録の扱いと原稿

出力IDを `BOC_P144R1_...` として元の予定slotへ一対一に対応づける。元の2条件と新しい10条件について物理ID・session・未実行・未評価を保持し、閉鎖後に別の `reports/P144R1_continuation.json` へ集計する。元のP144報告を置き換えない。

再起動・cache・server sessionの変更を方式差から分離できない。数値上の成功維持・削減条件を満たしても、そのまま方式の因果効果・独立追試・新規性成立とせず、採用gateはfalseを維持する。保留12シナリオは未読・未実験である。

[原稿v03 PDF](../../papers/202610_letter/harness_efficiency_20261028_v03/manuscript.pdf)／[TeX・図一式ZIP](../../papers/202610_letter/harness_efficiency_20261028_v03/source_bundle.zip)／[根拠](../../papers/202610_letter/harness_efficiency_20261028_v03/EVIDENCE.md)。v03は閉鎖済みのハーネス制御の実測を扱う校正稿であり、P144/P144R1の途中結果は含まない。著者情報は仮欄、投稿は未実施。

[固定継続仕様](P144R1_shutdown_continuation_20261028.md)／[機械可読な開始記録](../../reports/P144R1_execution_start_20261028.json)。

# AIハーネス研究

2026-10-30版の原稿 **v27**：利用者のWord原稿に付いた17件のコメントを反映しました。文献引用を文末へ移し、関連研究の比較軸と実験設定の根拠を補い、重複表現・著者記号・節名を修正しました。本文の変数は編集可能なWord数式へ揃え、図表前後に指定の空きを設けています。

[Word原稿](papers/202610_letter/harness_efficiency_20261030_v27/manuscript.docx) ／ [Word参考校正PDF](papers/202610_letter/harness_efficiency_20261030_v27/manuscript.pdf) ／ [参考TeX版PDF](papers/202610_letter/harness_efficiency_20261030_v27/manuscript_tex.pdf) ／ [17件の対応内容](papers/202610_letter/harness_efficiency_20261030_v27/COMMENT_RESPONSES.md) ／ [編集方法・確認範囲](papers/202610_letter/harness_efficiency_20261030_v27/README.md)。

**提出用ZIPを必要な8ファイルだけに整理**しました。[最新の提出用ZIP](papers/202610_letter/submission/final_20261030/submission_files.zip)は1,198,347バイトで、10MB未満です。利用者指定の「桐生_letter_20261030.pdf」、内容が一致する最終Word、図1のEPSと実際の作成元Python、表1・表2のTXT、Excel、図表作成情報TXTを収録しています。README、参考LaTeX、検証ログ、JSONは含みません。Excelは説明専用シートだけを外し、表・元データ・集計の5シートと式を保持しました。

[指定の提出PDF](papers/202610_letter/submission/final_20261030/桐生_letter_20261030.pdf) ／ [対応する最終Word](papers/202610_letter/submission/final_20261030/桐生_letter_20261030.docx)。提出PDFは利用者のファイルをそのまま収録し、本文・表・文献・英文要旨、数式、図1がWordと一致することを確認しています。

あらまし120字、実測値、実験条件、図表、式本体、参考文献12件、実験の独立性と評価範囲を維持しました。新しい実験は行っていません。利用者指定の提出PDFは本文・文献5頁＋英文1頁です。別途残している旧校正PDFはLibreOfficeによる本文・文献6頁＋英文1頁、参考TeXは本文・文献5頁＋英文1頁です。今回のZIPには指定の提出PDFだけを収録しました。投稿は未実施です。

既知4課題・各方式1回の全12実行で成功を確認しました。専用反復方式の総トークン数は専用1回方式より12.07%少なく、この差はCSV処理で生じました。他3課題の両方式の値は同じです。独立した終了制御では、同じ写真課題の2条件で26.00–30.15%の削減を観測しました。要求・応答全文の完全一致基準の不成立と、既知課題・少数試行の開発実験の事後整理という限定を保持しています。

[前版v26](papers/202610_letter/harness_efficiency_20261030_v26/README.md) と [v26の電子データ](papers/202610_letter/submission/electronic_data_20261030/README.md) は保持しています。以下は過去の実験・公開記録です。

P145は **2026-10-29 02:03:36 JSTに全12条件と所有serverを閉鎖**しました。全使用量既知147,313 tokens・不明0・厳密更新検査合格0。P146の起動条件は成立せず、P146の全課題比較は未実行です。[P145の確定結果と拒否内訳](docs/experiments/P145_closed_results_20261029.md)。

P147は **2026-10-29 04:17:58 JSTに全8条件を終了**しました。両方式3/4成功、未知使用量0。写真・精算で更新方式の局所削減を観測した一方、CSVは両方式失敗し、全4課題の合計は通常反復522,372→更新583,690 tokens（＋11.74%）。事前の全体削減ゲートは不成立です。[全条件・費用・機構の確定結果](docs/experiments/P147_closed_results_20261029.md) ／ [機械可読結果](reports/P147_closed_results_20261029.json)。

P148は **2026-10-29 07:57:11 JSTに予定8条件の実行・評価と終了処理を完了**しました。更新方式はCSVでも成功し、通常反復の3/4成功に対して4/4成功でした。全4課題の総トークン数は627,616→740,406（＋17.97%）、両方式が成功した3課題では390,024→385,746（−1.10%）です。使用量の欠測は0。成功数の増加を観測しましたが、事前の全4課題での費用削減基準は満たしていません。[全8条件の確定結果](docs/experiments/P148_closed_results_20261029.md) ／ [機械可読結果](reports/P148_closed_results_20261029.json) ／ [開始時点の記録](docs/experiments/P148_execution_start_20261029.md)。P147とは別のseed357の比較として扱い、過去の結果やprobe費用を合算しません。終了処理後の新しいモデル実験は起動していません。

以下は過去の日付の開始・停止・結果記録です。「実行中」「本日」「最新」は各記録を作成した当時を指し、現在も稼働しているという意味ではありません。

2026-10-28の実行開始時点の記録：利用者の明示的な再開依頼に従い、電源断前に未実行だった10条件をP144R1として継続する背景処理を16:00:18 JSTに起動した。16:03:58 JSTにモデル生成中であることを確認し、その時点では新規分 0/10条件を評価完了、BOC_P144R1_01_THRESHOLD_DELTA_UPDATE が処理中。停止前に実行を終えた2条件は再生成せず、評価待ちだった1条件を保存済みの状態から1回だけ公式評価した。途中の成否・費用による条件変更は行っていない。既知4課題・MiniMax-M3 IQ4_XS・seed257/world42・元の固定科学条件を継承する。新しいserver sessionでの継続を区別し、開始は改善・新規性の証明ではない。モデル期限は本日23:15、結果処理23:59。通常メッセージでは背景実行を止めず、明示停止に従う。[再開時点の記録](docs/experiments/P144R1_execution_start_20261028.md)。

[原稿v03 PDF](papers/202610_letter/harness_efficiency_20261028_v03/manuscript.pdf)／[TeX・図一式ZIP](papers/202610_letter/harness_efficiency_20261028_v03/source_bundle.zip)。原稿v03は閉鎖済みの実測を扱い、P144/P144R1の途中結果を含まない。以下の開始・停止記載は各過去時点の記録であり、再開時点の詳細はその記録を参照する。

2026-10-28の実行開始時点の記録：ユーザーの再開・原稿作成依頼に従い、P144の既知4課題×通常再帰要約／追記／明示的状態更新の固定12条件を14:21:42 JSTに開始した。14:23:41 JSTの保存運用記録は0/12・最初の要求fileあり。途中成否・usage・生成内容は未読で、成果・新規性は未確定。実験はバックグラウンドで有限に継続し、通常メッセージでは停止せず、明示停止に従う。モデルは本日23:15まで、結果・原稿は23:59締切。[P144開始記録と固定条件](docs/experiments/P144_execution_start_20261028.md)。

[原稿v03 PDF](papers/202610_letter/harness_efficiency_20261028_v03/manuscript.pdf)／[TeX・図一式ZIP](papers/202610_letter/harness_efficiency_20261028_v03/source_bundle.zip)／[実測根拠](papers/202610_letter/harness_efficiency_20261028_v03/EVIDENCE.md)。閉鎖済みの通常ハーネス制御の実測を扱う校正稿で、P144結果を含まない。著者情報は仮欄、投稿は未実施。旧v01/v02は保持する。

以下の「P141で実験停止」「原稿はユーザー担当」等は各過去時点の記録である。現在は本日の再開・原稿作成依頼を優先し、古い停止・分担を現在の指示へ読み替えない。

2026-10-28：ユーザーの最終指示に従い、モデル実験はP141を終了点とした。和文Dレターの初稿を作成した（本文・文献4頁＋末尾英文1頁）。[初稿PDF](papers/202610_letter/exposure_timing_20261028/manuscript.pdf)／[TeX・図一式ZIP](papers/202610_letter/exposure_timing_20261028/source_bundle.zip)／[編集用TeX](papers/202610_letter/exposure_timing_20261028/main.tex)／[実測根拠と主張範囲](papers/202610_letter/exposure_timing_20261028/EVIDENCE.md)／[書式上の確認事項](papers/202610_letter/exposure_timing_20261028/FORMAT.md)。著者情報は仮欄、現公式クラス最新版との照合は未了で、投稿は行っていない。以下は各過去時点の記録である。

2026-10-28 P141全3条件を閉鎖・評価：通常閾値TRと閾値object delta TDOは成功し、TDOの確定logical I/OはTRより2,807少なかった。累積再提示量EDOは失敗・unknown1で確定差null。単一既知課題の事後診断で採用評価は実施せず、全gate false・元4課題と保留12の確認範囲を維持する。[結果と限界](docs/experiments/P141_findings.md)／[資料・図の索引](docs/experiments/P141_results_20261028_index.md)。以下は各過去時点の記録である。

[保留12課題の実行接続の準備](docs/reserved_confirmation_integration_20261028.md)：全24枠の予定表、初期状態の照合、有限なreference初期化・終了処理を実装した。合成データでの検証であり、確認実験は未起動。候補の適格性、worker・preflight・全24枠の監査への接続は残る。

2026-10-28 02:18:41 JSTの運用確認：P141は02:15:37に固定3条件を開始し、観測時点0/3完了・最初の通常閾値条件が処理中だった。8事前計数とactivation完了、最初の要求・応答file存在を02:18:41に確認した。slot処理中は先の02:17:35観測からの引継ぎで、02:18:41の再照会ではない。途中成否・usage・生成本文は読まず、これは観測時点の開始記録である。既知Task4だけの通常方式／閾値object delta／累積再提示量object delta、seed57・最大2機会。P140後に選んだ診断であり、全比較gateは結果によらずfalse、元の全4課題比較・保留12確認を置換せず旧結果も合算しない。source5cab33a2／plan5dd2581f／1,736 source、3,139検査・同head両CI成功、開始205台帳2,652束縛。モデル絶対期限05:30、結果処理06:30目標。原稿本文はユーザー担当。通常メッセージでは停止せず、明示停止に従う。

[P141開始記録](docs/experiments/P141_execution_start_20261028.md)。以下は各過去時点の記録。準備中・実行中の記載は当時の状態であり、現在の状態へ読み替えない。

2026-10-28 01:26 JST：P140全12条件・公式評価と所有serverを閉鎖、独立検算と図の作成を完了した。通常閾値＋再帰要約は4/4成功・785,656 tokens確定小計、既存deltaは3/4・861,995既知＋unknown1、object出力を明示した候補は3/4・770,988既知＋unknown1。候補の第二deltaは実採用されたがTask4で30分上限に達して失敗。全体既知2,418,639＋unknown2、全方式の固定totalと固定比較差はnull、主比較・未変更delta比較・両方の採用条件はすべてfalse。成功維持と全仕事token削減は未達で、新規性は未確立。25,307項目の独立検算PASSは記録整合であり科学的採用ではない。旧結果は合算せず、保留12シナリオは未読・未実験。原稿本文はユーザー担当。

次は既知Task4だけの通常方式／閾値＋object delta／累積再提示量＋object deltaの3方式を、失敗後に選んだ診断実験P141として準備する。元の4課題の評価や保留12全体の確認を縮小・置換するものではない。各方式を一度、同seed・同予算で測り、旧失敗を上書きせず、実際の介入前prefixと成功・全費用を比較する。現時点は実装準備で、新しいモデル実行は未開始。通常メッセージで研究は止めず、明示停止に従う。

[P140全12条件の結果と限界](docs/experiments/P140_findings.md)／[結果・図表の索引](docs/experiments/P140_results_20261028_index.md)。以下は各過去時点の記録。

2026-10-27 22:52:14 JST確認：P140は22:46:56 JSTに開始済み。既知4課題×通常閾値・既存E/delta・第二deltaのobject出力明示の3方式、固定12条件、seed57・最大2機会。観測時点0/12完了で最初の条件が実行中。18事前計数（初期12・focus4・actor2）とactivation完了、最初のactor要求・応答file存在を確認し、本文・途中成否・usageは未読。source827298fa／plan635730af／1,675 source、開始203台帳2,592束縛、同head両CI成功。全件閉鎖後に主比較と未変更delta対照を別々に判定する。成功維持・削減・新規性は未証明、旧結果非合算、保留12未読。モデルは10/28 08:00まで、結果資料は09:00目標。

[P140開始記録](docs/experiments/P140_execution_start_20261027.md)。以下は過去時点の記録。現在のP140とは区別し、原稿本文はユーザー担当。

2026-10-27 21:51 JST：P139全16条件を閉鎖・評価。閾値＋再帰要約4/4成功、閾値＋delta4/4だが全仕事18,567 tokens増（+2.36%）。累積再提示量＋再帰要約と＋deltaは各3/4成功・unknown各1。全体既知3,192,403 tokens＋unknown2、全方式の固定総費用null、全5比較と組合せgate false。deltaの実提示9回があっても厳密prefix不一致のため表現だけの因果帰属は不可。独立検算27,230・別担当1,107照合PASSは会計整合であり技術採用ではない。19:44:59 JSTの途中9条件成否/usage閲覧を別途開示。保留12は未読、原稿はユーザー担当。

[P139全16条件の結果・図表・限界](docs/experiments/P139_findings.md)。追加実験は識別したい差と有限条件を別に固定してから開始する。通常メッセージで研究は止めず、明示停止に従う。以下は各時点の記録であり、当時の未閲覧記述を全期間へ拡張しない。

2026-10-27 18:25:06 JST確認：P139は18:22:59 JSTに開始済み。既知4課題×再要約時点2方式×第二要約表現2方式の16条件、最大2機会、seed57。確認時0/16完了・最初の条件が処理中。22事前計数とactivation成功、最初の要求・応答file保存とmodel slot処理を確認した。途中成否・usage・生成本文は未読。source a203874f／plan e05b7a0f／1,617 source、3,022検査・同head両CI成功、開始201台帳2,545束縛。モデル期限10/28 08:00、結果表・判定は09:00目標。これは開始記録で、成功維持・削減・新規性の成立は未証明。

[P139開始記録](docs/experiments/P139_execution_start_20261027.md)。通常メッセージで実行は止めず、明示停止に従う。原稿本文はユーザー担当。以下は過去時点の記録。

2026-10-27 17:09 JST：P138全12条件を閉鎖・評価。通常16kは4/4成功、固定3turnと累積再提示量は各3/4。提案は通常対照の成功を1件失い、共通成功3課題の各費用差・実判断差は0。既知費用は通常785,656、固定689,271＋unknown1、提案740,529＋unknown1。全体既知2,215,456＋unknown2、固定の全方式総費用と全体/common比較差はnull、両gate false。独立検算15,073照合PASSは会計整合であり技術採用ではない。元資料・失敗・不明を保持し、次は要約表現と後続動作の切分けを検討。保留12は未読、原稿はユーザー担当。

[P138全12条件の結果と限界](docs/experiments/P138_findings.md)。通常メッセージで研究は止めず、明示停止に従う。以下は過去時点の準備・開始・閉鎖記録。

2026-10-27 14:32:49 JST確認：P138は14:31:09 JSTに開始済み。固定4課題×3方式の12条件、0/12完了・最初の写真/rolling条件が実処理中。最初のactor送信・応答保存・model slot処理を確認した。途中成否・usage・生成内容は未読。source919b34e9／plan52ef2cbf／1563source、同head両CI成功、開始199台帳2497束縛。これは観測時点の開始記録で、方式の成功や新規性の確立ではない。

[P138開始記録](docs/experiments/P138_execution_start_20261027.md)。通常メッセージで実行は止めず、明示停止に従う。以下は過去時点の準備・閉鎖記録。


2026-10-27 14:26 JST時点：P138の実装・有限比較を準備中。既知4課題×16k閾値／固定3turn／累積raw-prefix再提示量の3方式、seed57、全12条件。保存入力11件の計数でCSVの初回判断差after19（E22,306／直前focus21,419）を確認したが、全仕事の削減・成功・新規性は未実証。最初のtemplate参照誤りを残し合計26 native描画・モデル生成0。新コホートは未開始で、source固定・全体検査・同head両CIを経て起動する。

[P138比較仕様](docs/experiments/P138_prefix_exposure_draft_20261027.md)／[候補と先行範囲](docs/checkpoint_prefix_exposure_candidate_20261027.md)。主対照への成功損失なし・全仕事token減と、固定間隔対照への追加価値を別gateで判定する。原稿はユーザー担当。通常メッセージで研究は止めず、明示停止に従う。

以下はP137閉鎖までの記録。旧失敗・欠測・採否は保持する。


P137は全4条件を閉鎖・評価し成功0。seed57 fieldsは368,024既知tokens＋unknown1、seed157の3方式は各102,035確定で双方失敗の差0・共通成功0組。全体既知674,129＋unknown1で厳密総費用null。seed57単独／seed157だけの記述的比較、採用評価false・旧P136非合算を保持。 [P137閉鎖結果](docs/experiments/P137_findings.md)。追加seedや同条件反復で救済せず、原稿本文は未変更。

[閉鎖結果一覧 v02](docs/closed_results_index_20261027_v02.md)：元7cohort・56行を保持しP135/P136の12行だけを追加、計9cohort・68予定条件／63評価。記録済unknown8呼出しとusage件数欠測5条件を分け、P136補足223,145は非加算。P137は固定開始リンクと「本一覧に未収録」の4予定placeholderのみ。phase横断の合計を効果や独立標本へ解釈しない。

開始時点の記録：P137は2026-10-27 12:29:26 JSTに開始した。12:31:46 JST時点で最初のfields57条件のactor要求保存とmodel slot処理中を確認（その時点0/4完了）。P136で未実施だったfields57→fields157→IDs157→raw157の4条件だけを追加観測する。この開始公開時点では閉鎖結果を未収録とし、当時の実行中の成否・usage・生成内容は読まずに記録した。 [P137開始記録](docs/experiments/P137_execution_start_20261027.md)。

seed57はfields単独、seed157だけが3方式の記述的比較。P136の元6行・欠測・gate falseは置換・合算しない。新P137の採用判定も行わない。初期raw interface・機構は同じで、timeoutの記録経路とworker終了状態を修正。各80calls/450000tokens/1800作業秒/API80、全4最大320calls/1800000tokens/API320/評価4、server4時間・18:00 JST上限。開始196台帳/2433束縛・1547 sourceを固定する。

P136は予定6行を保持して停止・集計を閉鎖した。評価完了1件（raw seed57成功・332,588 tokens）、worker未完1件、未実施4件。全仕事総費用・方式間比較はnull、固定gate false。独立検算57,099項目PASSは欠測を含む記録整合の確認であり、全6評価や方式採用を意味しない。 [P136の結果・欠測と限界](docs/experiments/P136_findings.md)。

全方式の初期raw guide/toolsを揃え、accepted checkpoint後だけIDsまたは同じ選択規則のIDs＋不足fieldを提示する有限比較だった。新query・公開handleはない。開始194台帳/2389束縛と1527 source、元失敗・欠測・図を保持する。途中workerの使用量と停止機序は別補足として扱い、認証済み全仕事表へ加算せず、費用0ともみなさない。 [時点付き開始記録](docs/experiments/P136_execution_start_20261027.md)。

P135は2026-10-27 09:58 JSTに全6条件・所有server・集計を閉鎖した。rawは1/2成功・434,623 tokensで費用既知、counts/entityは各0/2成功・既知小計274,986/302,737 tokensにunknown各1件。主比較の共通成功0、rawへの成功喪失1、詳細entity表示行とqueryは全0、固定gate false。独立検算18,274項目PASSは会計整合の確認であり、方式採用ではない。[P135全6条件の結果と限界](docs/experiments/P135_findings.md)。

2026-10-27朝のユーザー指示に従い、就寝中も実験を継続する。通常メッセージでは止めず、明示停止に従う。原稿本文はユーザーが執筆する。条件・有限予算・source・両CIを固定し、全仕事のlogical input+outputと公式課題成功を評価する。

P133は全4条件と所有serverを閉鎖した。producer監査ではseed57は両方式成功・各332588 tokens/API76/model31/focus2、seed157は両失敗・各102035 tokens/API80/model10/focus0。各方式1/2成功・全体434623 tokensで同じ、不明0、予測による要約見送り0、gate false。普通の制御校正による削減差はなかった。報告処理は固定public sourceに含むmaterials6件/papers1件を拒否して失敗（audit/session/report=0/0/1）。別のdata-only recoveryで全4資料を回収済み、追加model/API/eval/tokenizer0、原source/失敗は保存。別系譜の独立検算16788項目と図の相互確認はPASS。全4条件・失敗・復旧を[PR #542](https://github.com/sophiria1225/AI-/pull/542)で公開済み。[P133の結果と限界](docs/experiments/P133_findings.md)。

P134の待機queueはこの報告失敗を検知し、モデル・server・preflight・taskを開始せず停止した。旧P134のsource/plan/queue失敗を保持し、同じ6条件をP135別namespaceで実行した。変更対象は前件復旧の検証と報告path検証、実行識別子であり、機構・guide・tools・科学条件・予算はP134と同じ。P133の成否に基づく条件やseedの選択変更はない。P135は2026-10-27 08:15:47 JSTに開始した。08:18:19 JST時点でpreflight/activation成功、最初のnative actor requestとmodel slot処理中を確認した。その後、全6条件の有限比較を終了し、閉鎖後に成否・全費用を検算した。source `d87880f`、plan `5a5b5338`、1498 source、同head両CI成功。[P135仕様](docs/experiments/P135_whole_task_observed_obligations.md)。

P135は従来のraw anchor／残件数のみ／対象IDと不足fieldの3方式×seed57/157、既知CSV1課題の6条件。全方式でtyped観測とcaptureは共通、主2方式のguide/query能力は同じ、rawは元P123 interfaceを保持する。accepted checkpoint後の次actorへ一度だけ有料表示し、open/unknown列挙を残件0にしない。各80calls/450000tokens/1800作業秒/API80、server6時間・18:00 JST上限。P133復旧証明とP134モデル0、source固定、両CI成功を起動前に確認済み。全6条件の閉鎖後に集計・独立検算を完了した。

P136は対象列挙とfield対応付けを区別する設計だったが、比較未完のため追加寄与を判断できない。全pending対象の不足fieldが同じなら、集約件数からfield maskは一意であり、field情報が増えたとは言えない。既存FOCUS等にもentity保持・救済がある。新規性、一般品質維持、新方式の全仕事token削減は未確立で、少数seedや共通成功だけを一般効果へ広げない。P123の通常rollingは既知4/4成功で単発比12.07%減を観測済み。原稿用の全条件・失敗・不明費用・機構到達を整理する。

P133開始snapshot189台帳/2290束縛と、その後のglobal190/2300を分離する。P134の未実行予約snapshot190/2300も保存し、P135の開始snapshotも190/2300で固定し、その後のglobal増加を遡及しない。元run/prepと失敗は変更しない。モデルは単一serverで直列、保存された生成Pythonはhost実行しない。保留12シナリオは要求文・データ・正解を未閲覧のまま保つ。

変更先はsophiria1225/AI-と[専用Project1](https://github.com/users/sophiria1225/projects/1)のみ。raw prompt・reasoning・生成task code・課題値・認証・評価器本文は公開しない。原稿執筆・教授への連絡・投稿は行わない。

[引継ぎ後の実験結果一覧・主張可能範囲](docs/closed_results_index_20261027.md)／[P135開始記録](docs/experiments/P135_execution_start_20261027.md)。

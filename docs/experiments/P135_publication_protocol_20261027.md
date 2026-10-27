# P135 全6条件の公開準備

これは結果を読む前に作った公開手順であり、完了・成功・費用削減を報告する資料ではない。通常の図付き18ファイル全件コピーは、全体の閉鎖確認・結果解釈・図の検証後に行う。科学データの分析は全6枠のcollector完了と固定された独立reviewの閉鎖後に進められ、図の完了を前提にしない。所見やPRでは確認済みの範囲を区別する。原稿本文は変更しない。

## 固定する系譜

実行headは `d87880f474c05541d8d0cde0ec318fd262d9fa0e`、plan SHAは `5a5b5338773f4a5b80ab61f9ccae9a3591c4f42ef8f458f2c38e4bc8894d8a2e`、sourceは1,498件。開始時snapshotの190台帳・2,300束縛を使い、公開時のglobal台帳数へ置換しない。公開準備treeはmain `1d3afff01635618d55fffe10a4245704bdbeae80`から分離した。元のrun/prep、固定source、P133報告失敗・別回収、未実行P134待機失敗は変更しない。

対象は既知CSV1課題、seed57/157、`raw_anchor / counts_only / entity_fields`の6条件である。第1反復はraw→counts→entity、第2反復はentity→counts→raw。主比較entity対countsと補助比較entity対rawを別々に示す。6条件を独立6課題と呼ばない。[固定仕様](P135_whole_task_observed_obligations.md)、[時点付き開始記録](P135_execution_start_20261027.md)、[引継ぎ後の結果一覧](../closed_results_index_20261027.md)を参照。

## 分析開始と通常の18ファイル公開コピーを分ける

1. まずcollectorと独立review waiterの終端metadataを確認する。全6枠のcollector完了と固定独立reviewの`pass`・閉鎖・hash照合後に、科学データの分析へ進める。通常の図付き18ファイル全件コピーには、さらにfigure waiterの`complete`と図の検証を要求する。先行失敗、明示停止、欠測、期限超過はそのまま保持し、元実験・監査・rendererを自動再試行しない。
2. 独立review source `93a98042…`、そのwaiter `13c9b859…`、renderer `536bd31c…`、figure waiter `d39244f9…`の完全SHAと固定head/planを照合する。reviewの`pass`は会計・記録の整合を意味し、科学的採用gateとは別である。
3. waiterが束縛したcollector/review出力のSHA、collector startが束縛したclosure SHA、元audit/session/reportのstage順・exit code・成果SHA、元startのregistry文字列/hashを照合する。auditに構造化されたエラーがある場合も、その件数と6行を削らない。session/report自体の失敗を正常閉鎖に読み替えない。
4. 閉鎖されたpublic audit/sessionの所有process停止フラグと、それを原記録から照合した独立reviewを要求する。固定run/prepでhead、plan、1,498 source、開始190/2,300の旧report/全束縛を照合する。private checkerの成功記録だけから現在のprocess状態を推測したり、processを操作したりしない。
5. collectorと独立reviewの閉鎖・系譜確認後に公開aggregateを読み、6行のidentity、全未知費用、公式評価、主・補助比較のgate再計算、CSVとJSON、manifest依存をdata-onlyで確認する。固定rendererの`load_closed`に相当する照合は図の生成を必要としない。監査本体や生成コードは実行しない。
6. 図付き公開には既存のfigure waiterが一度生成した成果を使う。figure waiter完了後にfigure dataを読み、manifestのactual/synthetic区分、全artifact SHA、figure dataとpublic auditの一致を確認し、2 PNGを目視する。通常公開処理からrendererを起動しない。図が失敗した場合も監査済み科学データの分析は止めず、下記のaggregateのみの公開または別版data-only修復として扱う。

## コピーするもの

通常の図付き公開では、ディレクトリ全体やglobは使わず、次の18ファイルだけを明示的に同bytesコピーする。親ディレクトリを含むsymlink、絶対path、`..`、不明ファイル、既存のコピー先は拒否する。全入力を先に検証し、排他的stagingに保存してコピー元/先のSHAを再確認する。途中失敗を自動上書きや再試行で隠さない。

| source群 | 許可するファイル | 公開先 |
|---|---|---|
| collectorの4 reports | `P135_initial_checks.json`, `P135_activation_v01.json`, `P135_comparison.json`, `P135_server_session.json` | `reports/`の同名 |
| collectorの4 materials | `conditions.csv`, `summary.json`, `README.md`, `build_manifest.json` | `materials/20261027_p135_results/`の同名 |
| 既存figureの9ファイル | `whole_job_cost`と`paid_work_and_obligations`のPNG/SVG/PDF各3、`figure_data.json`, `README.md`, `output_manifest.json` | 同materialsの`figures/` |
| 固定renderer source | `draw_p135_results_20261027.py`（536bd31c…と同bytes） | 同`figures/` |

元collectorの`copied_source_sha256`集合は上記8件と完全一致させる。materials manifestはREADME/CSV/summaryの3 artifactを束縛する。figure manifestは画像6件とREADME/figure dataの8 artifactを束縛し、manifest自体はfigure waiterのSHAで検証する。public source依存はcopy許可リストと分離し、repository相対pathの完全hash集合として検査する。依存に古いmaterials/paperが含まれる場合も、固定mapの具体pathだけを使い、一般prefixへ許可を広げない。

raw records、API値、token/credential、モデル入出力、推論、生成コード、capture/noticeの実体、評価本文、private reviewの絶対source path・検査ラベル、ログ全文は公開しない。元公開producerの固定sourceと厳格なfield schemaを根拠にし、追加の文字列検査と人手privacy reviewも行う。単純なNG文字列検査だけで匿名化が証明できるとはしない。collectorファイルに私有情報が検出されたら同bytes公開を停止し、別の明示的projectionと原hashをreviewする。

## 新しく作る公開資料

コピー後、閉鎖解釈を受けて次の資料を作る。準備段階で結果欄を埋めない。

- `reports/P135_closed_independent_audit_20261027.json`: reviewの公開aggregate/flags/check件数と、検証済みfigure rowの6行のみ。元review全体SHA、除去したprivate source mapのSHA/件数を残し、private絶対pathを削除した投影であると明記する。共有monitor/notice encoderと既存producerへの依存、scope hashの条件差を残す。
- `reports/P135_results_copy_manifest_20261027.json`: 18個のコピー元hashと公開相対path、元closure/review/figure proofのhash、同bytes照合結果。private絶対pathは含めない。
- `reports/P135_results_provenance_20261027.json`: 新しい固定公開資料だけを束縛する。旧ledgerを編集せず、後日のmerge後に最新globalを再確認して1件だけ追加する。mutableなREADME/RESUME/trackingを固定成果ledgerへ入れない。
- `docs/experiments/P135_findings.md`: 全6条件の予定/評価/成功、known input/output/unknown、全体費用と共通成功費用、主・raw両対照、各seed、固定gate、実capture/通知到達/累積entity行/query/host時間を短く示す。条件欠測や監査不能も行を残す。
- materials入口READMEへの案内は元builder READMEを上書きせず、別`publication_index.md`から元CSV/JSON・図・findings・監査へリンクする。repo入口のmutable navigationとR32/R33だけを更新し、他118件を保持する。

未知の費用はknown小計と区別し、全仕事の正確な差を`null`のまま残す。空の共通成功群は0削減としない。成功増/成功喪失/双方失敗を分ける。累積entity表示行はunique entity数ではなく、観測field完備は公式課題成功ではない。scopeごとのhandle hashの差があるので、最初の入力差をfield内容だけの因果効果としない。単一課題・2seedでは新規性や一般的品質維持を確立しない。

public redrawは公開済み`figure_data.json`と`output_manifest.json`の公開SHA、同一rendererで新出力先へ行える。再描画は元監査の再認証ではない。PNG/SVG/PDFのmetadata・font/library差によるbytes変化と、科学データの同一性を区別する。

## 失敗した場合

| 状態 | 残すもの・次の扱い |
|---|---|
| collector/closure失敗・欠測 | 元stage/markerとhashを保持。完成資料を仮定せず、運用失敗を別報告。実験再試行なし |
| 独立review失敗 | 科学資料の公開を止め、失敗hashと検査範囲を別記。元reviewの再実行なし |
| figure失敗 | 元failed/partial出力・失敗metadataを保持。図未生成を明記し、検証済みcollectorの8ファイルだけをaggregate公開できる。原因と元失敗を保存した別版のdata-only修復を検証する。既存rendererの自動再実行はしない |
| 科学gate false、課題失敗、unknown | 運用・監査が閉じていれば全6行をそのまま公開。成功だけの選択なし |
| packaging中のhash/privacy不一致 | 新stagingと失敗記録を保持。元成果を修正しない。原因を共有し、既存の継続許可の範囲で別版処理を検証する |

図なしのaggregate公開は通常の18ファイル公開と別のcopy manifestで8件を列挙し、図の未生成・元失敗hashを残す。準備したpure checkerの3者完了条件は通常18ファイル公開専用であり、科学データ分析やこの8ファイル公開の開始条件ではない。通常のdata-only修復に新たなユーザー承認を要求しない。

この準備では新model/API/evaluator/tokenizer/Docker、保存生成code実行、実結果の読取、実コピー、再描画、所見記述、PRを行っていない。

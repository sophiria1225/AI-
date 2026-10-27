# P136 全6条件の公開準備

これは結果を読む前に用意した手順であり、実験の完了・成否・費用効果を示す資料ではない。所見は閉鎖後の全件解釈を経て記述する。原稿本文、固定実験、producer、独立監査、rendererは変更・再実行しない。

## 固定情報と公開先

実行headは `e65fa22d32bd63e80005e7bf807b2c91624e6824`、planは `configs/P136_whole_task_late_obligations_v01.json`、SHAは `ff442f59f9012af6932974469fc5b2fbcb08afc3e8dd9cba4a480a9cc5f36f6a`、sourceは1,527件。実行開始時の194台帳・2,389束縛と、その後の開始記録公開による195台帳・2,401束縛を区別する。後者で元の開始snapshotを置き換えない。

公開準備treeはmain `844c07ff29ec963e3f2fda184e7fb1ad16ff3ede` から分離した `p136-results`。元の `p136-run` / `p136-prep`、予約snapshot、旧台帳を変更しない。後の公開provenanceは新成果だけを束縛し、merge後にその時点のglobalを照合して追加する。mutableなREADME/RESUME/trackingは固定成果ledgerに入れない。

既知CSV1課題、seed57/157、`raw_anchor / ids_only / entity_fields` の全6条件を保持する。第1反復はraw→IDs→fields、第2反復はfields→IDs→raw。主比較fields対IDs、補助比較fields対rawを分離する。同じ課題の6条件を6独立課題と呼ばない。[固定仕様](P136_whole_task_late_obligations.md)と[時点付き開始記録](P136_execution_start_20261027.md)を参照。

## 閉鎖後の入口

1. 通常の図付き18ファイル公開コピーは、全6条件のcollector完了、固定独立reviewの`pass`とwaiter完了、figure waiter完了、rootの全件解釈後だけ行う。科学的gateのfalse、課題失敗、unknownは公開を阻まない。欠測・失敗行も保持する。
2. collector `c292303e…`、wrapper `4054b4e5…`、reviewer `c6581939…`、review waiter `225053d6…`、renderer `36a6102b…`、figure waiter `5c02a385…` の完全SHAをprivate checker定数と照合する。旧P135のproofでは通さない。
3. markerのparsed objectと原bytes/hashを結ぶ。reviewが束縛した元closure SHA、collector-startのclosure SHA、元audit/session/report順序とexit、元start registry文字列/hash、全6 identity、所有process停止の元証拠を照合する。audit errorはexact integerで保持し、0とfalseを同一視しない。session/reportの失敗を正常閉鎖にしない。
4. 固定head、plan、1,527 source、開始194/2,389のreportと全束縛をrun/prepで検証する。公開treeの既存source依存も同bytesであることを確認する。公開時globalの追加を実行開始条件へ遡及適用しない。
5. 完了markerのhashと、独立review、collectorの8ファイル、既存figure manifest/dataの対応を検証する。図は一度生成済みの成果だけを使い、公開手順からrendererを起動しない。全6行、known入力/出力小計、unknown、全体/共通成功比較、gate、CSV/JSON、各artifact依存をdata-only照合し、2 PNGを目視する。

collectorと独立reviewが正常閉鎖した科学データの分析に、図の完了は必須ではない。図だけ失敗した場合は元failed/partialを保存し、検証済み8ファイルのaggregate公開を別manifestで行うか、原因と元失敗を残した別版data-only図修復を検証する。既存rendererの自動再試行はしない。

## 通常コピーの許可リスト

| source群 | 許可するファイル | 公開先 |
|---|---|---|
| collector reports 4件 | `P136_initial_checks.json`, `P136_activation_v01.json`, `P136_comparison.json`, `P136_server_session.json` | `reports/` の同名 |
| collector materials 4件 | `conditions.csv`, `summary.json`, `README.md`, `build_manifest.json` | `materials/20261027_p136_results/` の同名 |
| 既存figure 9件 | `whole_job_cost` と `paid_work_and_obligations` のPNG/SVG/PDF各3、`figure_data.json`, `README.md`, `output_manifest.json` | 同materialsの `figures/` |
| 固定renderer source 1件 | `draw_p136_results_20261027.py` | 同 `figures/` |

ディレクトリ全体やglobではコピーしない。collector mapは8件、figure artifact mapはmanifest以外の8件と完全一致させ、figure manifest自体はwaiterのSHAへ結ぶ。PNG/SVG/PDFも元bytesをそのまま使用する。元READMEは上書きせず、追加の案内は `publication_index.md` に置く。

全入力検証を最初の公開writeより前に完了する。親ディレクトリを含むsymlink、絶対path、`..`、未知ファイル、既存コピー先を拒否し、新しいstagingと排他的`xb`/`x`で保存する。コピー前後の元/先hashを再確認し、途中失敗を上書きで隠さない。private checkerはpureなmap/schema検査であり、実IOのsymlink検査、parsed objectと原bytesの結合、排他write、公開依存hash照合は実copier側の責務である。

raw records、API値、credentials、モデル入出力・推論・生成コード、capture/notice実体、評価本文、private reviewの絶対source path・検査ラベルを公開しない。固定public exporterと厳格な行schemaを根拠とし、文字列検査と人手privacy確認を追加する。NG文字列の不在だけで匿名化が証明されたとはしない。

## 閉鎖後に新しく作る資料

- 公開safe独立review投影：全6行、公開aggregate、flags/check件数、元review SHA、除外したprivate source mapのdigest/件数を保持。共有encoder/monitorとproducer history auditへの依存を残す。private全reviewは転載しない。
- copy manifestと新provenance：18元hash・公開相対path、closure/review/figure proof hash、同bytes検証を保持する。
- findingsとpublication index：全予定/評価/成功、unknown、全体/共通成功費用、主/補助比較、累積ID行とfield行、capture/実actor露出/query0、時間、固定gateを示す。空の共通成功は0削減とせず、未知を含む正確な全費用差はnullとする。
- 必要な入口docsとR32/R33だけ更新し、120項目と他118件を保持する。追加の実験・原稿本文変更はこの手順に含めない。

累積ID表示行はunique entity数ではない。`entity_fields`のfield行と`ids_only`のID行を区別する。同じclosed pending-ID列を条件に同じprefixを選ぶ性質と、独立runの実ID列が一致したという観測を混同しない。queryと公開handleは提供されず、全3方式の初期入力は共通である。表示・取得field完備は公式課題成功ではなく、単一既知課題・2seedだけで一般的品質維持や新規性を確立しない。

## 後から追加する限定補足

固定builder READMEの文言は変更しない。publication index/findingsには、通知JSON body上限2,048 UTF-8 bytesと固定heading43 bytesを区別し、追加system content上限2,091 bytesと明記する。これはHTTP全payloadやtoken数の上限ではない。heading込みの全message viewをnative count/admission/sendへ使い、unknown usageは未知のまま保持する。

rootが閉鎖後一度実行する追加診断は、事前固定された `P136_postclose_diagnostic_plan_20261027.json` の系譜を照合してから、公開safeのcounts/hash/限界だけを別追加資料へ投影する。これは上記18件に含めず、診断未実施/失敗を成功扱いしない。fieldmask割当可能数はentropy、LLMの情報利得、因果効果、新規性ではない。補助診断で元の費用・unknown・採否gateを変更しない。

別途、閉鎖済みP135 rawと旧P122のAPI列・program sourceの一致を調べた診断は、root/peer確認後にP135補足として公開safe投影を検討する。endpoint・call・停止triggerの集約と一致照合の範囲だけを示し、private絶対path、認証引数を含むrequest hash、値、コードは出さない。旧P135 findings/ledgerは変更せず、同じ軌跡を独立反復として数えない。これはP136の実軌跡や効果の診断ではなく、予算・機構変更や新規性の根拠へ直接転用しない。

この準備で実結果・中間report・figure outputは読まず、実コピー、実producer/監査/renderer再実行、追加model/API/eval/tokenizer、commit/PRは行わない。

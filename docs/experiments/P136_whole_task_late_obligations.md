# P136：初期interfaceを揃えた未完了IDと不足fieldの比較

2026-10-27。P135全6条件を閉鎖・独立検算してから選んだ、既知CSV1課題の有限な開発比較。ユーザーの既存の実験継続指示に基づく設計者側の選択であり、P136について新しい個別承認を受けたという記録ではない。準備中であり、この文書だけでは起動・機構到達・改善を意味しない。新規性、一般的品質維持、採録に足る成果は未確立。原稿本文はユーザーが執筆する。

## P135から変える問い

P135ではrawが1/2成功、counts/entityがともに0/2成功、unknown usageは各1件、実entity行とqueryは全0だった。seed57の主2方式はcheckpoint前にAPI上限へ達した。seed157は初回の通知前10要求まで主2方式間で同じで、最初の通知の差はscope依存handleだけだった。全3主通知は補助GET `show_liked_playlists`の未対応を理由にunknownとなり、詳細行を出せなかった。これらの元結果・費用・判定は保存する。

一方、raw seed57の最初のcaptureにはclosedなpending47、title不足44、artists不足47が存在した。これは未表示の観測であり、実効果の証拠ではない。全pendingのmaskは集約件数から一意ではなく、初期interfaceをrawに保った場合に検討する機会がある。P136では「普通のID再提示に不足fieldを加える価値」を問い、初期guide/queryの追加と表示hashの差を除く。P135と同じ条件を追加seedで反復する計画ではない。

## 比較条件

| 方式 | 初期messages/tools | accepted checkpoint後の次actorへの表示 |
|---|---|---|
| raw_anchor | 元P123 raw guide／CODE_TOOLS | 追加なし |
| ids_only | 同じraw guide／CODE_TOOLS | 共通descriptorと未完了ID |
| entity_fields | 同じraw guide／CODE_TOOLS | 同じdescriptor・同じID列と各IDの不足field |

主比較はentity_fields対ids_only、補助比較はentity_fields対raw_anchor。query tool、query guide、初期の追加説明は全方式にない。実行は全方式で通常のrun_python/read_span処理を使う。観測・capture・契約確認は全方式で共通に負担する。

既知の同じ1課題、seeds57/157。順序はseed57のraw→IDs→fields、seed157のfields→IDs→raw、計6条件。各条件を独立6課題と数えない。P123/P133/P135の同じ課題・seed結果と独立反復としてプールしない。保留12シナリオは要求文・データ・評価本文を含め未閲覧のまま維持する。

## 機構と保持する境界

通常の別呼出しrolling checkpoint採用直後に、その時点のtyped観測からsnapshotを作り、次actorの実dispatch一度だけへ通知する。私有のscope・要件・観測prefix・checkpoint revisionへのbindingは維持する。queryのない公開noticeにはsnapshot handleを入れず、runごとに違うopaque hashを表示上の差にしない。

同じclosed pending-ID列に対し、最大descriptorと最大maskを予約する保守的なselectorが、昇順の最大16行のprefixを2048 UTF-8 bytes以内で選ぶ。ID側とfields側は同じ選択を使い、ID側の余ったbytesへ別のIDを詰めない。選択に実maskの長さや実countsの桁数を使わない。この保証は同じpending-ID列を条件とするもので、pending集合やcounts自体のfield状態への依存、独立runの全軌跡の同一性を主張しない。実際の要求列・最初の入力差は全件閉鎖後に確認する。

`open/unknown`は不足件数null・詳細0行を維持し、義務なしと扱わない。累積ID表示行とmissing-field表示行を別々に計数する。後者はfields方式だけに生じる。私有状態のIDやfield値、生成コードを公開しない。

`show_liked_playlists`は固定公開実装の限定された補助readとして対応する。typed receipt、明示dispatch、effect既知、nonce、同じprincipal、対応引数・返却形を確認する。非対応・不明・既存taintは保持し、過去のtaintを消さない。liked playlistの返答値を所有playlist libraryの対象unionへ加えず、そこからmetadataを補完しない。通常の契約対応自体を新技術と呼ばない。

## 有限予算と実行条件

各条件はactor＋focusの共有80呼出し、450000 logical input+output tokens、1800作業秒、環境API80回。setup120秒、cleanup180秒、idle回復60秒、公式評価180秒を別管理する。6条件合計はモデル最大480呼出し・2700000 tokens・API480回・評価6件。要約機会は各最大3回、全体最大18回で共有呼出し・費用に含める。

checkpointは通常rolling_separate、入力閾値16384、直近2turn保持、最大3機会、fresh turn最小3。P133 payback予測は使わない。時間通知なし、推論budgetは従来の-1、初回cache_prompt=false。モデル・量子化・sampling・context・API error policyはP123/P135基盤を維持する。`t_max_predict_ms`やclient graceはこの比較に追加しない。未送達の使用量を推測で既知へ補完しない。

同一所有serverで直列実行する。server最大21600秒、batch最大18000秒、outer wrapper最大23400秒、終了期限18:00 JST。完全なserver leaseが期限内に収まらなければ起動せず、勝手に予算を縮めない。必要なら別の事前固定計画として扱う。

起動前にsource/plan/開始台帳snapshotを凍結し、同じsource headのpushとPRのaccounting-and-syntax成功を確認する。P135の全6閉鎖、元audit/session/reportの0/0/0、collector・固定独立review・figureのhash chain、元所有PID不在を確認する。元P135の1498 source、開始190台帳/2300束縛を変更せず、P136の開始snapshotは新しいglobalから別に確定する。旧実験・監査・rendererを再実行しない。

## 採否と報告

全6条件の公式評価と使用量既知、全契約・会計の成立を要求する。entity_fieldsはIDsとrawのいずれにもpaired成功を失わず、IDsに対する全体費用と非空の共通成功費用が低く、rawに対する全体費用も低いことが必要。さらに主比較の共通成功上で実missing-field行を提示していることを要求する。

失敗・未実施・未評価・監査不能・unknownをすべて行に残す。unknownがあれば正確な総費用・差はnull、空の共通成功群を0削減としない。cached inputを控除せず、要約・追加表示・失敗・修復・制御の費用を含める。host/要約時間はwork/server時間と重なるので加算しない。API削減や入力の短縮を全仕事tokenの改善へ置き換えない。

最初の有限6条件で未到達、成功喪失、unknown、全仕事削減不成立、IDsとの追加差不成立なら、この方式を同条件の追加seedで救済しない。gateを通っても既知1課題・2seedの開発結果に留め、一般品質維持や新規性を確定しない。FOCUS等の防御的保持、構造化summaryのTODO/ID保持、typed検証の既存研究に対する優位は、本比較だけでは測定しない。

結果・図・全条件CSV・費用と失敗の内訳・限界・採否を公開する。公開するのは集約と出所hashであり、raw prompt、reasoning、API値、認証、評価本文を含めない。

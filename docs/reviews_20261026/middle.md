> [レビューの入口](../research_history_review_20261026.md)。本文の `docs/`、`scripts/`、`reports/`、`configs/`、`materials/` はリポジトリroot基準。`records/` は公開していない原記録。

# 中期実験履歴と閉鎖済みCSV診断の統合レビュー（2026-10-26）

対象はP39–P79の全41 phase、P105–P117、および既知CSVのP120/P122閉鎖記録。P0–P38とP80–P104、P118以降の全体比較は統合担当側の分担で、この文書は全repoレビューの中期担当分である。論文原稿はユーザーが執筆するため編集していない。P123途中成績、未見課題、独立評価の追加テスト・正解は読んでいない。実験を停止する操作は行っていない。

判定に直結する点は次のとおり。

- 新規性として繰り返せない既存機構: 古いstdout省略、schema由来区間の参照化、使用後schemaの省略、rich error feedback、値を保持した引数名修復、完全応答cache、ReadView、実行receiptによる過去推論選別、手書き公開証拠による完了制御。
- 局所的な正結果はP66の写真終了制御（全仕事token約26〜30%削減、同じ成功と最終DB hash）。ただし手書き既知文型の通常対照であり、P68 CSVでは不発。一般品質維持や新しい機構の証明ではない。
- P105の遅延取得優位はP106の強い普通cacheで12対12 APIへ消失。P107は対象APIもReadViewも使われず両未達。P111のreceipt選別とP114の推論非再入力は全仕事採用基準未達。
- P117は保持schemaの大量印字を既に診断したが、表示変更は未実装。今回P122 CSV call021にも26個の完全公開schema、17,543文字の再印字がある。ただし「既にactive入力に同一本文が二重存在する」状態ではない。
- P122 CSV全6run・130要求では適格stdout全文の同一入力内重複0。seed157ではcheckpoint前に同一read13回、うちshow_song12回。普通cacheの対象とschema再表示を分けるべきで、単純dedupを新方式として走らせる根拠はない。

新規model/API/tokenizer/保存modelコード/評価器の実行0、Git変更0。ゼロmodel-callの今回診断は [aggregate JSON](../../reports/closed_csv_review_20261026.json) に144読取ファイルのSHA-256とともに保存。生のprompt・task値・生成code・非公開推論・認証値を含まない。

以下は担当別詳細をそのまま収録する。相対パスの基準は `リポジトリのP123準備木`。

---

# P39–P79 閉鎖済み履歴レビュー（2026-10-26）

分担して読んだ実装と所見を統合した記録。

対象root: `リポジトリのP123準備木`。以下の相対パスはすべてこのrootに対するもの。

このレビューはP39–P79の全`docs/P*_findings.md`、関連する実装・固定config、主要比較の公開集計を読んだもの。私有軌跡の再監査・当時の各commitへのcheckout・実験の再実行はしていない。現在の作業木に保持された旧実装を実際に読んでいるが、全旧固定ソースhashを独立に検証したという意味ではない。新規モデル、API、tokenizer、評価器、保存コード実行は０。P123、未見課題、隠れた評価項目、正解、DB内容を読んでいない。変更はこの一時レポートの新規作成だけで、repoは変更していない。

## 結論と取り違えてはいけない点

1. **stdout省略、API仕様の外部参照、一覧と詳細の分離、使用後の仕様省略、詳細エラー返信、値を保持する局所修復は既に実装または比較済み。** 新名称でこれらを主提案に戻さない。
2. **P66は実測された局所的な正結果**。既知写真１文型の手書き公開証拠モニタが、同じ成功・最終DB hashで全仕事tokenを30.15%／26.00%減らした。ただし通常の証拠付き終了であり、一般の要求理解も新アルゴリズムも示していない。P68では同型のCSV終了制御が一度も発動せず、両側未達・費用差０。
3. **P39以降の初回cold、P41の残量出力枠、P51の終端使用量受信、P63の公開名アクセス、P75の推論履歴保持は強い通常基準の整備。** それぞれを新規な削減機構と扱わない。
4. **P55/P71の「全履歴」は全公開履歴であり、過去の`reasoning_content`を含まなかった。** P75で明文化、P76で保持の比較、P78で開始時から全推論保持へ移行している。古い結果と新しい全履歴を同条件として混ぜない。
5. **反復API取得とモデル再表示は別の費用経路。** P77は写真42件の同一要求・同一返却再取得を確認したが、memoizationだけで生成数や論理tokenが減るとは主張していない。P69/P70/P74では、必要列が既知でも完全返答の契約や将来のPython参照を保てない点が明示されている。
6. **時間通知とcacheで未介入の段階から分岐し得る。** P58/P79は１秒差の局所感度。P78返金の大きな差はAPI例外が一度もなく、失敗通知の効果へ帰属できない。

## P39–P41: 比較の校正と通常予算制御

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P39 | 同じ13,552-token入力、seed50、256出力枠でcold/warm各３生成。生成ツールは未実行。v01 slot消去はHTTP501で生成前停止、v02を別記録で実施。 | cold３回内・warm３回内は一致、群間は不一致。cold処理13,552／cache0、warm処理1／cache13,551。６生成82,848論理token。以後は条件初回`cache_prompt=false`かつ実測cache0を確認。完全決定性や新規発見ではない。 |
| P40 | 既知４課題・第８応答後の同じ状態で残API／生成／token／秒の通知ありなし。16生成・120,000継続token・480秒。 | ８予定中６評価、１使用量不明・未評価、１未実行。写真は通知で成功したが費用/API増、返金は成功同士で31,658→83,335継続token。全体採用不可。完遂していない４課題比較を３対の合計で代用しない。 |
| P41 | P40の予約拒否３入力で、最大4,096を毎回予約せず残token−正確な次入力まで出力枠を縮小。 | 2,471／3,878枠の２入力で357／100-tokenの構文適合ツール指示を生成、残枠０の１入力は生成せず。２生成34,057token。ツール・課題評価未実行で、元の時間予算内完了は示さない。残量出力枠を通常対照部品として保持。 |

実装を確認した箇所:

- `scripts/inference_cache_control.py:31`の`cache_measurement`はterminal計数、`cache_n+prompt_n==input`、cold0／warmほぼ全入力を確認する。
- `scripts/budget_signal.py:26`の`snapshot`は使用量不明後の正確残量を拒否し、前半API込み残量と継続token残量を区別。`:47`の通知追加と`:64`以降の初回coldを確認。
- `scripts/residual_output_budget.py:13`の`admission`は`min(output_limit,max(0,remaining-input))`。context制約を維持し、入力を切らない。`:41`以降は正確計数、deadline、永続admission記録、使用量不明時の無料retry拒否。
- 固定config: `configs/P40_budget_notification_v01.json`。
- 結果: `docs/P39_findings.md`、`docs/P40_findings.md`、`docs/P41_findings.md`。P39/P41を課題成功実験と数えない。

## P42–P47: schema/stdout表示、出自認定、失敗時の契約返信

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P42 | 古い成功stdout全体が当該documentation返答の決定的直列化に完全一致するときだけ省略。全４課題12入力を計数。 | 23候補中３出力のみ。全入力48,485→47,102、各課題削減488／801／0／94。２課題で1,000tokenという配分基準に未達、生成比較なし。仕様一般が小さいとの結論ではない。 |
| P43 | 順序を固定した入力成分の追加計数と、P42不一致７出力の全文API文字列への対応分析。44入力計数。 | 仕様APIだけの要求群stdoutは9,832token、他API群17,954。７出力27,343文字中27,077は返却直列化と一致、残266文字。文字列一致は由来証明でも削除許可でもない。 |
| P44 | 保存コードの限定ASTと実要求・返答・stdoutを照合し、document由来のprint区間だけを参照へ変換。literal見出しは保持。 | 23候補中10出力を認定、初回合計48,485→40,399（−8,086）。３課題で1,000以上、次の比較設計へ進む基準を満たす。生成・品質・全仕事削減は未測定。 |
| P45 | 全表示 vs P44仕様区間省略、同じ４課題第８応答後。両方に予算通知・残量出力枠。 | ８予定すべて試行、７評価、全表示CSVは使用量不明・未評価。写真は全表示成功→省略未達、返金成功同士32,209→79,502継続token。既知継続315,308+不明 vs368,745。採用しない。 |
| P46 | P45拒否の時点で既公開契約を返信できるか読取診断。契約全文／引数名だけの部品。 | ７拒否中４件・３課題に既公開契約がある。写真・返金では拒否後に既存`api_schemas`を再表示する構文があった。返信文字数は節約tokenではなく、実効性は未測定。 |
| P47 | 全表示+契約／省略+引数名／省略+契約の３条件×４課題。未送信の未知引数拒否にだけ返信。 | ９評価、全表示CSV１件は未知使用量・未評価、残２未実行。写真は全表示成功、両省略未達。返金継続32,145／63,118／47,185で契約は引数名より安いが全表示を超えない。全体採用不可。 |

実装上の境界:

- `scripts/documentation_exposure.py:17`は成功した非切詰めstdoutと非空のdocumentation receiptを要求し、全体一致だけ認める。
- `scripts/documentation_print_origin.py:40`の`printer_environment_guard`は過去コードのprint/json別名・再定義・反射・未知import等を拒否。`:94`のRecognizerは局所scopeを空から構成し、`:113`–`:173`はliteral、局所変数、認定済み`call_api`、`json.dumps`等だけを扱う。
- 同`:247`の`build_origin_view`は**固定前半の古い出力**だけを処理。documentation-only群、同じcallに属するreceipt、保存コードとstdout全体一致を要求。混合・既存変数の未確認参照・範囲外式を保持する。
- したがって**保持Pythonの`api_schemas.items()`を後のプログラムで再printし、APIを０回呼ぶ場合の動的抑制ではない**。一回の前半編集後は通常どおり履歴を追加する。
- `scripts/contract_feedback.py:21`の`make_feedback`は`api_request_sent=False`、作用既知、厳密な`unknown API parameter`、既公開schemaに限定。全文が16,000文字を超えれば引数名へ縮退、値のecho・修正・retryは０。`:61`のchannelは既存dispatchを唯一の権限として使用。
- P47は６付加返信の次のプログラムに同API送信があり同じ形式拒否なし。ただし写真「省略+契約」は**付加０件**なので、契約を受け取っても修復できなかったとの説明は誤り。
- 固定config: `configs/P45_documentation_comparison_v01.json`、`configs/P47_contract_comparison_v01.json`。どちらも16生成・120,000継続token・480秒。
- 結果: `docs/P42_findings.md`〜`docs/P47_findings.md`。`reports/P47_comparison.json`も読取確認し`development_gate_met=false`。

## P48–P53: 局所修復の変更境界、計測、使用依存の仕様保持

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P48 | P47の65保存プログラム・335内部要求を静的診断。 | 10拒否: 既公開６／未公開４。空契約への余分引数３、写真の２名前対応１、返金で名前と値が変わる２、未公開４。小入力で全部直す案を採らず。直後の生成費用は修復専用費用ではない。 |
| P49 | 未知引数名だけの修復案を作り、値と既存引数をhostに保持する一提案bindingを実装。 | 空契約正規化３、型適合完全対応１、完全対応なし２、受付外４。６packet計5,881文字。モデル提案生成・API送信・Python再開は未実装/未実行。曖昧な候補１件だけを理由に複雑な再開器へ進まない。 |
| P50 | 介入前P24全６nativeとP29全４Pythonの488イベントを診断。 | native拒否０、Python拒否６、値保持名前対応候補２（login・各型上候補１つ）。群の課題が異なりPythonが拒否を増やした因果比較ではない。通常の決定的対応付けを強い対照にする。 |
| P51 | 非stream完了／stream完了／意図的切断の合成３生成でSSEと使用量の権限を校正。 | 完了２回201input+76output、全文一致。切断は観測出力下限４だが入力/出力確定不明。既知554token+不明１。v01 Path JSON化失敗は生成前停止、別v02で記録。計測基盤のみ。 |
| P52 | 詳細契約を「非エラー使用後のみ」または「全引数名が観測された後のみ」省くprefix-only候補を実装。 | 全23候補で７出力/6,454文字、または６出力/3,000文字短縮。未使用move/create/transaction/show_song等は保持。使用成功らしさは将来不要性の証明ではない。生成/計数なし。 |
| P53 | 全履歴・一覧保持詳細省略・P52二候補の全16入力を計数。 | 総初回48,485／44,509／46,510／47,503。P52候補は各課題最大921／596tokenで配分基準未達、継続生成なし。単純詳細省略だけ２課題>1,000となり後のP55へ。 |

実装で確認したこと:

- `scripts/request_repair_binding.py:76`は未送信・作用既知・既公開契約の未知引数拒否だけ受付。`:115`の`RepairBinding`は元要求/schema/値をcanonicalで固定し、値を含まないpacketを作る。`:153`の`evaluate`は一提案だけ消費、古いbinding/宛先重複/型不適合を拒否、dropは空契約のみ。`:200`以降は候補組立だけで、返答に`api_dispatched=False,python_resumed=False`を明記。
- `scripts/streaming_usage_receipt.py:214`はterminal usage+finish_reasonとDONE、完全なtool断片を分ける。確定使用量がなければNone、途中下限は別、`partial_message_may_execute=False`。`:233`は完全streamのみ実行可能メッセージへする。
- `scripts/contract_use_retention.py:32`は渡されたprefixイベントだけでdocument以後の試行・非エラーJSON・引数名を追う。`:71`は失敗/不明試行のある契約、api_docs/supervisorを除く。`:81`はP44と同じ出自認定区間だけ置換。アプリ/API一覧・最新turn・原文を保持。
- config `P49_repair_binding_v01`と`P52_contract_use_retention_v01`は`model_generations=0`。`P53_contract_retention_counts_v01`は1,000token×２課題の配分gateを明示。
- 局所修復を新規に進めるなら、空契約正規化・唯一候補の決定的対応・通常のerror+schema修復・全履歴継続、さらに通常継続へ戻る費用を対照に残す必要がある。P49は外部作用のexactly-onceを証明していない。

## P54–P61: 通常取得/集合照合、一覧保持の再比較、完了手続きの診断

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P54 | 既知57対象の最大値を個別取得／順位走査／１ページ先行取得で取得。実API使用、LLMなし。 | 同じ最大集合。取得57／1／1 API、準備込み62／6／6、全74API。３側とも投影69byte。通常順位走査で十分、先行制御の追加価値０。API差をLLMtoken差へ換算しない。 |
| P55 | 全表示F／詳細省略・一覧保持D／詳細と一覧省略B、全４課題×３、同じ第８応答後。 | 成功1/4／2/4／1/4。全仕事512,565／555,648+不明１／563,774。D既知だけでF+43,083、費用削減不採用、一覧保持の追加価値gate未達。 |
| P56 | P55写真F/Bの保存状態を別世界へ再現し、完了通知なし/１回の４診断。 | F未達→成功、B未達のまま。作業アプリ状態不変、F通知後はDと全DB hash一致。再現344+通知２ API、４評価、LLM０。元成功数は変更しない。 |
| P57 | P55全77生成の終端費用を診断。 | 完了APIだけの４生成64,882token、APIなし20生成248,242既知+不明１。これらには判断/計算があり、安全に除去可能とは言えない。最後の書込後でも必要確認が残り得る。 |
| P58 | P55返金の保存１入力の残時間335/336秒を変更、cold各２回。 | 同じ値２反復一致、群間不一致。４生成63,312token。元warm実行の原因同定・操作実行・課題品質なし。通知非表示や丸めの採用実験でもない。 |
| P59 | P24６成功中最大費用の承認課題を事後選択、既取得11連絡先×26依頼のメール集合照合。 | 観測承認と同じ10件を選択可能。しかし後の６検索返却は先行情報にない行を含み、完全API応答を代替不可。述語/照合キーは分析者指定。 |
| P60 | 完全性・主体・状態版付きの三値所属部品を保存観測で検査。 | 両関係+終端なら10肯定/16否定、同じ行だけで終端なしなら10肯定/16不明。状態版/主体変更なら全不明。実モデル/APIなし、元検索を省いた成功実験ではない。 |
| P61 | P24承認課題の第12応答後から通常nativeと持続Pythonを各１回。P60部品なし。 | 両側成功、追加連絡先検索０。全仕事311,298→305,447（−1.88%）、継続58,696→52,845、生成2→3/API11→12。強い通常基準だけで再検索しなかったため所属cache接続へ追加計算を配分せず。 |

実装上の違い:

- `scripts/ranked_subset_read.py:40`はcaller指定ID集合の最大値を計算。信頼adapterのcoverage/order/snapshot契約がなければpoint取得へfallback、`:137`以降は全体降順の末尾が既知最大より**厳密に小さい**時だけ停止し同点を守る。LLMの対象集合選択器ではない。
- `scripts/inventory_display.py:22`はP44認定区間をdetail/listingへ分類。`:83`に`one_time_boundary_display_change=True`。D/Bで標識を揃え、同じdetailを落とすことを`:98`以降で確認する。後のstdoutやAPI要求を動的に制御する方式ではない。
- `scripts/membership_evidence.py:63`は連続ページ・終端・scope・上限を検査、`:111`の`lookup`は観測witnessで肯定、**全関係の閉じたページ**があるときだけ不在を否定、他は不明。検索全返答は返さない。外部更新検知や自然言語述語抽出はない。
- P61 config `configs/P61_ordinary_continuation_v01.json:34`はno supplied predicate/join/target/P60/future valuesを明示。普通のPythonも履歴の値を利用でき、専用cacheを足したことによる結果ではない。
- `reports/P55_comparison.json`も読取確認し、採用gateとinventory advantageは両方false。P55の「成功増」は写真の終了通知差を含むためP56と併記すべき。

## P62–P68: 公開名アクセスと公開証拠による通常終了制御

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P62 | 既知写真文型の公開元集合・移動前日時・移動先・名前・成功receiptを照合する手書きchecker。 | P55 F/D各42移動・名前保持、B移動０。ただし成功した公開時計がなく全３条件の支持は不明。移動先に合う年を観測した年へ昇格しない。生成/APIなし。 |
| P63 | 標準AppWorldの公開名アクセスと研究harnessの文書露出必須制約を区別し、PublicNameCatalogを実装。 | 旧P29の233要求で２件、P55の631要求で７件が新たに引数キー検査通過（共通前半重複を含む）。静的受付診断だけでAPI成功/節約ではない。公開名アクセスを通常対照として用意。 |
| P64 | 写真・精算の既知２課題を初期状態から文書必須／公開名の２条件で比較。 | 全４成功。文書必須407,678、公開名408,046（+368token）、生成38ずつ。全側公開時計成功。公開名は通常機能として保持、独自効率方式としない。能力説明も変わるinterface package比較。 |
| P65 | P64写真２条件にP62 checkerをそのまま適用する読取診断。 | 公開時計もそろい各42移動を支持。最初の支持call13/12後に各２生成39,323/39,431token。未だ実測節約ではない。旧P55時計不足も維持。 |
| P66 | P62/P65 checkerを逐次実行へ接続。既知文型の根拠がそろった後に通常完了APIを１回だけ実行。 | 文書必須130,439→91,116、公開名151,664→112,233。両成功、各２生成・４確認API減、最終13DB hash一致。全25生成203,349token/199API。不明０。局所採用条件を満たし通常部品として保持。 |
| P67 | 既知CSV export-then-delete文型の公開全ページ・列・内容・順序を読むchecker。元P18/P25/P29の３記録。 | P25は全要求支持、P18は１行不足で矛盾、P29はbackup未確認で不明。P25支持後41,702tokenは後続費用で未実測節約。72IDは観測集合から計算、固定解答埋込ではない。 |
| P68 | 同じCSV初期状態から通常native／同native+終了checkerを各１回。モデル80/450,000token/1,800秒/API80。 | 両未達・API上限、各219,126token/８生成/80APIで差０。全８境界unknown、CSV作成/退会未実行で自動通知０。最終境界で必要データがそろっても作業自体は未完。終了判定だけでは前段取得配分を改善しない。 |

実装で確認した範囲:

- `scripts/public_name_catalog.py:15`はNativeCatalog subclass。Python RPCでは`visible=None`なら固定公開catalog全体を名前受付に使い、明示visible snapshotのnative経路は従来のまま。権限・値・予算・doc取得・retryを足さない。
- `scripts/public_move_evidence.py:32`はcaller定義MoveRequirement、完全inventory、移動前metadata、同じscope、成功移動、観測current_yearを要求。current_yearがなければ一致候補年があってもunknown。移動後日時を元日時に流用しない。
- `scripts/ordinary_completion_control.py:25`は現在の公開prefixのみ。連続call ID、既知usage、イベント/spans全対応、chronological、作用既知、未完了、対応外作用なしを確認し、固定normalizer/checkerへ渡す。checker自身はAPIを呼ばない。
- `scripts/run_completion_control.py:109`以降が**全応答のプログラム実行後**に判定し、`:123`で既存channelと予算を通して１回のcontroller actionを送る。`configs/P66_ordinary_completion_v01.json:69`は手書きknown-templateであることを明示。
- `scripts/public_export_evidence.py:27`は全ページ・同scope・ID/Title/Artists・CSV・正しいwriteの後のdeleteを時系列で検査。`:62`のCSV照合は不足/余分/重複と曖昧ID対応を扱う。`:156`のdeleteは**既に支持されたbackup**に先行しないことを確認。
- `scripts/export_completion_control.py:6`は同checkerを現在prefixへ限定。`scripts/run_export_completion.py:96`以降が通常APIで完了だけ送る。削除やCSV生成を制御器が肩代わりしない。
- `reports/P66_ordinary_completion.json`の25生成/203,349token/199APIと`reports/P68_export_completion.json`の16生成/438,252token/160APIを読取確認。
- P66/P68は要求全文の事前一致がcall ID差で不成立のまま。その後P73が入力列を分析しても、元の事前検査を後付けで合格へ変更しない。

## P69–P74: 再取得の需要と完全値、公開名での表示再比較、入力同一性

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P69 | CSV既知５記録・308詳細要求で、要求前の必要列充足／同一要求完全返答／後の全オブジェクト一致を区別。 | P29８件、P68各９件は列既知、全26件は後の列も一致。ただし完全応答既知０・全オブジェクト一致０。純粋にこれだけのAPIからなる生成境界０。列再利用候補を全応答置換や生成節約にしない。 |
| P70 | P33全12条件181コード出現（117固有）のcall_api返却root利用を静的分類。 | 239構文箇所、144名前束縛/95全体引渡し、直接subscript/get０、read_fields０。限定自動射影候補０で実行系へ追加しない。 |
| P71 | P55と同じF/D/B表示を、公開名アクセスを全条件に与えて再比較。全４×３。 | 成功2/4／1/4／2/4、全仕事500,883／523,407+不明２／557,248。D既知だけでF+22,524、採用不可。全12評価。旧文書制約で生成された第８応答後からの比較であり開始からの公開名方針ではない。 |
| P72 | P71で完了API未送信の全７状態を、無介入/１完了通知の14診断。 | 写真Dのみ未達→成功、精算/CSVの６状態は未達維持。作業DB不変。702再送+７通知API、14評価、LLM０。元成否・費用・自律成功数を変更しない。 |
| P73 | P64/P66写真25対とP68 CSV８対の実効入力再構成/計数。 | 元batchは69再構成後、GGUFテンプレートと実効テンプレートの末尾LF１byte差で停止。別の事後読取では全33対の文章/token列/制約一致、元66入力計数も一致。元事前判定の検証済み０は維持。GPU/RNG状態再現ではない。 |
| P74 | P70の名前束縛を、その後のliteral field/get、明示上書き/delete、ループ等まで静的診断。 | 144保存箇所中15field/get、明示上書き３出現だが限定候補０。未生成の将来コード・例外時状態まで守れると証明できず、自動射影を実行系へ追加しない。 |

実装の境界:

- `scripts/export_acquisition_scope.py`は必要なCSV列を既知と数える診断であり、実際にAPIを抑制するcacheではない。
- `scripts/return_use_scope.py:26`は現在のASTのみを解析し、source20,000文字/AST5,000ノードを上限化。`call_api`別名やdynamic namespace等のhazardを数え、保存コードを実行/変換しない。
- `scripts/boundary_lifetime_scope.py:27`は同じstatement suiteの上書き/deleteを識別、`:38`のfield/get分類、`:56`以降のbinding追跡。正常経路の構文だけで将来の完全値を減らす許可にはしていない。
- `scripts/public_display.py`はP55表示をPublicNameCatalog用の同一能力説明に接続する比較器。詳細/一覧の省略機構自体は`inventory_display.py`と同じ。
- `configs/P71_public_display_v01.json`も16生成/120,000継続token/480秒。`reports/P71_comparison.json`の採用gateと一覧優位gateはfalse。過去のP55とP71を独立８課題として加算しない。
- P73のcall ID規格化は、任意の本文中にある似たID文字列を消す処理ではない。公開の操作内容や入力長だけの一致を意味同一性の証拠にしない。

## P75–P79: 推論履歴、反復取得、typed例外、時計感度

| Phase | 実施したもの | 閉鎖結果・判断 |
|---|---|---|
| P75 | P29前半32+P71継続73の計105保存入力/応答のhistory policyを点検。 | 103既知応答は全て非空reasoning_content、105入力には同fieldなし。101入力には過去推論が存在したが非再投入。P10以来の宣言済み条件でbug修正ではない。全保持のReasoningConversation部品を別途追加。 |
| P76 | 第８応答後から公開履歴のみ／過去推論も全保持、４課題×２。選別/要約/追加modelなし。 | 両2/4（写真・返金）。写真156,754→118,184（−24.6%）、精算+3,444、返金+2,281。CSV両未知１・未達。全体538,323+不明１／470,932+不明１で正確差不明、gate未達。 |
| P77 | P76全43生成・40Pythonを構文/公開API/費用で診断。 | 写真公開のみは同じ42ファイル詳細を再送し返却全42同一、推論保持は再送０。APIなし既知６生成97,972tokenはPython５+原文参照１で無駄判定しない。CSVは取得を含む例外と取得０の処理、後の生成中断を区別。 |
| P78 | 課題開始から全推論保持、同typed bridgeで確認済み呼出例外だけを文字列値V／Python例外Eへ変更。全４×２。 | 両3/4、V670,713／E791,704（E+120,991）、全使用量既知。返金は例外０で−67,518差を通知方法に帰属不可。CSVは最初の例外より前に分岐、両API80未達。採用gate未達。 |
| P79 | P78の例外前分岐２保存入力で残時間元値/+１秒、各３反復の12生成、全cold。 | 同値３反復一致、異値公開出力不一致。99,966token、全既知。生成コード未実行・最終品質/全仕事差なし。元warm状態の原因再現ではなく局所感度。P58と同種校正を追加し続けない。 |

実装で確認したこと:

- `scripts/reasoning_history.py:36`は同じ公開assistantに対応する**過去の**保存responseのみを付加する。`:57`のReasoningConversationは全返却reasoning fieldを選別なし保持、invalid-call text fallbackでも同じfieldを保持。観測を変えず、reasoningを実行証拠とは扱わない。
- `configs/P76_reasoning_history_v01.json:40`は前半８responseと自条件の以後成功responseの全保持、他公開message/observation/API/tool同一を明記。旧前半は推論を再投入せず生成されたもの。
- `scripts/api_error_comparison.py:34`は両armを同じPublicResultProgramで包み、`:56`はhost receiptの`api_execution.status=='raised'`だけをV側で文字列へ変換。業務falseや未知作用を例外に変えず、失敗docから新schemaを公開しない。`:68`は開始からReasoningConversation。Vは旧untyped経路の完全再現ではない。
- `scripts/public_api_result_transport.py:113`以降がtyped値/例外を元channelへ適合し、receiptを保持。`configs/P78_api_error_v01.json`は80生成/450,000token/1,800秒と`all_returned_reasoning_from_start`を明記。
- `scripts/clock_notice_replay.py:17`は保存通知を厳密確認し、最終残時間だけ元/+１、cache falseへ変更。seed56、4,096出力枠等を固定。効果のあるharness制御を実装したものではない。
- `reports/P76_comparison.json`でgate=false、`reports/P78_comparison.json`でgate=falseと`exception_minus_value_whole_task_tokens=120991`を読取確認。

## 今後の候補で繰り返してはいけない主張と、必要な通常対照

| 候補の言い方 | 既にあるもの / 次に必要な差 |
|---|---|
| 「古い出力を参照にして短くする」 | P33/P42/P44/P45/P55/P71。初回短縮だけでは全仕事削減を示せない。必要性の選別・再表示・反復取得まで含む強い対照が必要。 |
| 「使ったschemaだけ消す」 | P52/P53で実装・計数済み。使用済み/全引数名観測は将来不要証明でなく、適用量も小さかった。 |
| 「既存schemaをエラー時に渡せば再printが減る」 | P46/P47の契約返信。fullとparameter-namesも同時対照にする。対象拒否が起きず介入０なら機構の失敗例にしない。 |
| 「小さいLLMで引数名だけ修復」 | P49値保持binding、P50候補census。normalization/唯一対応/通常のerror+schema修復との差と、合流後成功/全費用が必要。 |
| 「同じAPIをcacheする」 | P77は同一返却の実例を確認済み。通常memoizationそのものは新手法ではない。鮮度/作用/例外と、cache後も同じ値をprintする費用を分ける。 |
| 「必要列だけ取り出す／未使用fieldを消す」 | P37/P69/P70/P74。完全返答と部分返答の契約、持続Pythonで将来参照できる完全値が残る問題を解かなければ元動作維持にならない。 |
| 「集合照合／順位付き取得で取得を減らす」 | P54/P59/P60/P61。通常検索/集約/普通のPythonで達成する強い対照が必要。API差をtoken差へ換算しない。 |
| 「公開証拠で早期完了」 | P62/P65/P66/P67/P68。P66の局所正結果を保持するが手書き２文型の通常制御。CSVの作業前段には効かなかった。要求を生成するコストと正しさを無料にしない。 |
| 「推論履歴を保持/省略する」 | P75/P76と後続P110以降。旧“full”の定義を揃える。新しい保持policyだけを独自性としない。 |
| 「例外・残時間・cacheを整える」 | P39/P41/P51/P58/P63/P78/P79。強い通常対照/測定条件の整備であり、そのまま効率機構や主貢献ではない。 |

現在考えるredisplay問題への限定した含意: 中盤実装は**固定境界の古いstdout編集**か**拒否時の契約返信**であり、任意の後続`print(api_schemas...)`を現在可視履歴と比較して抑制するpolicyではない。ただし、P46時点から保持schemaの再print自体は認識済み。単にこの現象を見つけたことは新規ではない。提案候補の最小強対照は、APIやPythonは通常実行したまま、現在入力内に完全な同一本文が残っている場合だけ後のexact duplicate stdoutを参照へ変える通常の重複除去。checkpointで最初のcopyが失われた場合は全文を戻す。これを超えるpersistent-state/source-aware方式の追加価値を別に示す必要がある。

このレビューだけではその重複除去のcoverage、成功維持、token削減、新規性は測定していない。ゼロmodel-callの次診断は、閉鎖済み記録で「同じAPI返答」「同じstdout」「現在入力内に残った同じ本文」「archive/保持Pythonにしかない本文」を区別して数えること。差のある行動を、情報が削除された証拠へ自動変換しない。

**追記（統合担当からの完了済み診断連絡）:** `reports/closed_csv_review_20261026.json`の144読取ソースファイルのhash対応集計について、P122 CSV６run・130 active requestに同一入力内で適格な完全stdout重複は０だったとの報告を受けた。call021の26 schema blockも、それ以前のactive入力にindent2文字列としてなく、その後は各１copy。これは本分担レビューによる私有入力の独立再監査ではないが、上記のexact-dedup案を今回のCSV費用に効く候補として進める根拠がないことを意味する。反復API応答を重複モデル入力へ読み替えない。persistent schemaを必要に応じて再表示することと、既に可視の同一本文を二重表示することを区別し、０coverageを受けて単純重複除去の新規model実験は提案しない。

## 読取確認した主要公開集計

- `reports/P47_comparison.json`: gate=false。全４課題の完全比較は不成立、方式ごとの試行/評価分母が違う。
- `reports/P55_comparison.json`: gate=false、inventory_advantage_supported=false。F/D/B全仕事既知512565/555648/563774、不明0/1/0。
- `reports/P66_ordinary_completion.json`: complete、25生成、203349token、199API、不明0。
- `reports/P68_export_completion.json`: complete、16生成、438252token、160API、不明0。
- `reports/P71_comparison.json`: gate=false、inventory_advantage_supported=false。F/D/B成功2/1/2、全仕事既知500883/523407/557248、不明0/2/0。
- `reports/P76_comparison.json`: gate=false、成功2/2、全仕事既知538323/470932、不明1/1。
- `reports/P78_comparison.json`: gate=false、E−V全仕事120991token。

41phaseすべてを上記表に列挙した。報告内の各phaseの出典は同番号の`docs/P*_findings.md`と、その文書内の固定実験計画/公開reportへのリンク。多数の事後診断を独立した課題・未調整確認群・新成功数へ合算しない。


---

# Closed history review: P105–P117 and P120/P122 CSV diagnosis

Read-only review on 2026-10-26. Repository root: `リポジトリのP123準備木`. Private run root: `records/context_pilot`. This review read closed public reports, plans, implementation code, and the already-known CSV's saved requests/events/program inputs and outputs. It did not read P123 interim results, unseen tasks, independent evaluator extra tests/answers, or private reasoning content. It ran no model, task API, tokenizer, saved model program, or evaluator. The only new file is this report outside Git.

The important conclusion is that API reacquisition, reprinting persistent Python values, repeated history transmission, and multiple identical copies inside one input are four different costs. Earlier work already tested ordinary complete-response caching, old stdout masking, documented-schema substitution, persistent Python, and reasoning-history selection. None can be renamed into a new contribution. A new intervention must identify which cost it actually changes and survive a strong ordinary control.

## P105–P117: actual mechanisms and outcomes

| Phase | Implemented and actually measured | Result and adoption decision |
|---|---|---|
| P105 | Coalesce identical unresolved ReadView references; reuse a complete response when ordinary reads resolve a pending group. Seven handwritten stages, three policies; no model task run. `scripts/coalesced_contract_read_views.py`. | Eager/original deferred/coalesced deferred: 13/16/12 APIs, equal stdout across all stages. Four redundant deferred reads disappeared. The apparent remaining one-API advantage was a missing ordinary-cache lookup in the eager control, not the initially claimed unused-read avoidance. The source report retains and corrects that causal explanation. `docs/P105_findings.md`. |
| P106 | Give both policies an ordinary complete-response cache for pinned, verified `spotify.show_song`, same execution scope, state epoch, and full arguments. Partial values cannot replace full responses. `scripts/ordinary_complete_read_cache.py:39`, `scripts/public_contract_read_views.py:20`. | 12 vs 12 APIs; all seven stdout hashes match both policies and P105. The apparent advantage disappears. No task quality or model-token result follows from this handwritten sequence. `docs/P106_findings.md`, `configs/P106_ordinary_complete_read_cache_v01.json`. |
| P107 | Fresh whole-task CSV runs with the same explicit ReadView interface and ordinary cache, eager vs coalesced deferred. World seed42/model seed57, one repetition, 80 model calls, 450,000 logical-token cap, 1,800 seconds, no automatic code rewriting. `configs/P107_whole_task_read_views_v01.json`. | Both fail at `token_reservation_limit`: 21 generations, 427,234 logical tokens, 53 APIs each. ReadView use0, complete-cache reuse0, and target `show_song` calls0. This is non-use, not evidence that an exercised intervention has no benefit. It fails the fixed gate requiring both successes, known usage, clean audit, and lower whole-task tokens. `docs/P107_findings.md`. |
| P108 | Replay only the host's stored control requests/returns against recorded evidence, not model Python or live APIs. | All42 program records,108 control replies,106 API replies agree; pending reference groups0. Confirms P107 did not exercise the mechanism. No new success or counterfactual savings. `docs/P108_findings.md`. |
| P109 | Closed-record availability and input-composition diagnosis. | Each P107 arm had14 artist lookups, zero prior names in the two inspected sources, and two ordinary exact album-read candidates. Ordinary album caching is a baseline opportunity, not ReadView novelty. Per arm: cumulative tool body573,231 characters, reasoning344,887; those are not token allocations. `docs/P109_findings.md`. |
| P110 | Deterministic input projection for full/recent/execution-gated past reasoning. Eligibility derives from actual successful nonempty API receipts, no pending reads/unknown effects; latest reasoning always retained. Restores original reasoning when current eligibility fails. `scripts/receipt_reasoning_history.py:24,95`. | 444 virtual inputs over148 saved requests. Execution-gated reduces aggregate hypothetical inputs35,722 tokens; recent reduces164,593. Common-prefix totals decrease, so logical savings do not imply cache savings. These are local same-trajectory counts, not new task runs. `docs/P110_findings.md`. |
| P111 | Whole-task full/recent/execution-gated comparison, four known tasks×three policies, same public actions/observations and persistent Python. Config explicitly disables ReadViews and complete-response caches. 80 generations/450,000 tokens/1,800 seconds per cell. `configs/P111_whole_task_receipt_history_v01.json`. | All policies3/4; CSV fails all. Full807,463+unknown1, recent555,031 known, gated663,668+unknown1. Gated's known portion already exceeds all recent cost108,637 (19.57%); its unknown remainder cannot reverse that ordering. Fixed dual-control adoption gate fails. Successful-three-task gated subtotal435,042 is3.07% below full448,825 and4.10% below recent453,632, but cannot replace the all-four gate. `docs/P111_findings.md`. |
| P112 | 612 input reconstructions over204 realized requests, and accounting decomposition of local display shortening vs observed whole-task cost. | Gated photo saves4,003 local input tokens but costs39,100 more overall. Gated successful-three subtotal has8,352 local display savings vs13,783 observed total reduction. The residual is accounting, not a causal mechanism. Noncached input across successful3 rises59,497 full→128,109 gated. P111 remains rejected. `docs/P112_findings.md`. |
| P113 | Closed action/observation divergence analysis, all12 dependent policy pairs over the same4 tasks. | First differing inputs differ only in reasoning;11/12 pairs immediately change public output/Python AST,9/12 change API requests. Fourteen positions have equal nonempty API sequences but different Python; three also have different public tool observations. Equal API counts/results do not prove equal computation. `docs/P113_findings.md`. |
| P114 | Ordinary public-only history: remove all prior assistant reasoning while retaining public code/results and runtime state, fresh task starts. This is a historical comparison against P111, not contemporaneous reruns. `scripts/whole_task_public_only_history.py`, `configs/P114_whole_task_public_only_history_v01.json`. | Same3/4 success,1,000,544 known logical tokens; +445,513/+80.27% against P111 recent, higher cost in every task. CSV425,348,24 generations,69 APIs, token reservation stop. Not adopted as a cheap standard. `docs/P114_findings.md`. |
| P115 | 316 input reconstructions on P114's79 realized requests. | Removing reasoning saves98,019 local tokens across4 tasks, while actual success-three cost increases126,371 against historical full. The hypothetical CSV full trajectory would cost484,362, exceeding450,000; it is not a feasible executed comparator. No ordinary public-only adoption. `docs/P115_findings.md`. |
| P116 | Diagnose all16 P111/P114 conditions,283 requests,820 APIs; distinguish initial observation display from later history retransmission. | Observation bodies total5,427,957 characters:556,027 first appearance and4,871,930 later appearances. Fifty full-argument repeated API requests;31 equal normal results;19 within the conservative six-read-API intervals. These are not safe-hit or token-savings counts. One settlement observation accounts for332,028 cumulative characters with zero same-API repeats in that run. `docs/P116_findings.md`. |
| P117 | Bounded whole-literal match against complete, pinned public function schemas already exposed at program end. `scripts/public_metadata_observation.py:19,54`, using `runtime_recoverability.parse_structured_stdout`. Diagnostic only, no output-changing policy. | Four of263 observations match complete public metadata;95.79% of matched cumulative exposure is one18,202-character settlement stdout displayed18 times. Schema suppression is already conventional; opportunity is concentrated in a rejected control. Additional model generation based on this observation alone was explicitly not pursued. `docs/P117_findings.md`. |

The P111 gate is stronger than matching success totals: against both full and recent, it requires all paired evaluations and usage known, clean audit, no per-task success loss, at least one paired success, and strictly lower both all-task and paired-successful logical-token totals. Unknown usage stays unknown; native input counts or reservation caps cannot fill it in.

## Implementation boundaries that matter now

- `native_data_compute.py:12,51,63` is ordinary Python over explicitly chosen historical public receipts in a fresh isolated container. It returns the result as ordinary tool output. No automatic memoization, persistent namespace, API replay suppression, or stdout deduplication. Later persistent Python already supplies in-process state; adding ordinary computation again is not a new idea.
- `ordinary_complete_read_cache.py:39,59` only dispatches zero APIs for a verified complete same-scope/same-epoch `show_song` response. It does not cache all library/album/schema calls, does not merge authorization scopes, and returns the full ordinary value. Avoiding API dispatch alone does not shrink what the model prints or re-reads.
- `explicit_deferred_read_views.py:34–49` materializes on unsupported field access, iteration, length, or repr. Printing a view can therefore trigger full materialization. This is not an automatic smaller model-visible result.
- `receipt_reasoning_history.py:73,95` explicitly makes a zero-API Python turn ineligible for execution-gated selection. `project` asserts that all non-reasoning history is unchanged. It cannot remove a schema-printing stdout or repeated API observation.
- `documentation_print_origin.py:247` relies on contemporaneous documentation-only receipts and a restricted recognizer whose local scope starts empty. It does not follow a prior program's `api_schemas`, `.items()` traversal, or arbitrary persistent Python provenance. P33/P44/P45/P55/P71 make one boundary display change; they are not continuously applied live output suppression.
- `public_metadata_observation.py` compares the entire stdout literal against complete schema values; it explicitly records `safe_to_omit=False`, no measured savings, and no proven print provenance. A label followed by many JSON documents is outside that whole-literal shape.
- `runtime_recoverability.py` can witness builtin value equality in a bounded live namespace and recheck a route at use. Its own documentation excludes semantic relevance, source provenance, current external truth, and permission to delete output. A stored equal value is not proof the model can cheaply use it.

## Closed P120/P122 CSV: concrete evidence

Private record paths below are deliberately specific to the already-known CSV. They contain sensitive task context; this report publishes only counts, identities, stop reasons, and public API names.

The new zero-model-call analyses are preserved as aggregate data plus SHA-256 bindings for144 read files at `reports/closed_csv_review_20261026.json`. That JSON contains no raw prompts, returned task values, generated code, private reasoning, or credentials. Its source bindings make the130-request duplicate scan and26-schema comparison reviewable without exposing task content.

| P122 repetition/seed | Separate checkpoint | Required inline checkpoint |
|---|---|---|
| R01/57 | Success; `agent_declared_complete`;440,461 tokens;32 model calls including1 focus call;77 APIs | Failure; `token_reservation_limit`;438,073 tokens;28 actor calls;65 APIs |
| R02/157 | Failure; `api_request_limit`;102,035 tokens;10 actor calls;80 APIs | Identical metrics and same stop; checkpoint never offered/installed |
| R03/257 | Failure; `token_reservation_limit`;441,193 tokens;26 model calls including1 focus call;49 APIs | Failure; `wall_limit_during_model_call`;388,363 known tokens plus1 unknown final call;24 attempts;58 APIs |

Sources: `reports/P122_comparison.json`, `docs/P122_findings.md`, and `records/context_pilot/BOC_P122_R{01,02,03}_04_{SINGLE_CHECKPOINT,INLINE_CHECKPOINT}/{summary,events,spans,admissions}.json`. Cleanup is confirmed and API effects are not unknown. Unknown model usage remains unknown.

Input equality and timing:

- R01's first12 full request hashes match across arms; R02 all10 match; R03 first10 match. R01 same-arm P120→P122 full request hashes match for32/32 separate and28/28 inline requests; aggregate metrics also match apart from wall time. Thus P122 R01 is a reproducible recorded trajectory under these settings, not an additional independent task.
- R01 separate intervention follows12 actor turns: full next input17,696, compact next7,143, one focus call21,419 tokens. Inline instruction/schema is offered before actor call013; it executes that call before installing the summary. After13 turns the ordinary next input21,999 becomes11,110. The first actor action after an offer is not yet conditioned on compacted history.
- The inline call013 re-fetches library data that previously appeared, but does so before history compaction is applied. Hence that repetition cannot be attributed solely to deleted summary content. Instruction/schema differences can change actions even before installation.
- R01 inline eventually rejects call029: native input25,906 exceeds remaining11,927 token allowance with output cap0. Actual438,073 usage must not be rewritten as450,000. R03 inline final call024 had a known native input count29,568 but unknown terminal model usage; the former does not fill the latter.

Schema redisplay location:

- `records/context_pilot/BOC_P122_R01_04_INLINE_CHECKPOINT/programs/call_021_01/input_private.json` and `result_private.json`: normal zero-API program, stdout18,348 characters, not truncated.
- Its stdout contains26 complete `file_system` schema objects rendered by `json.dumps(indent=2)`, each byte-identical to its pre-program `api_schemas` snapshot. These full schema blocks account for17,543 characters; the remaining805 characters were not classified as removable.
- Request input rises17,725→23,277 between calls021→022, a5,552-token increment. This includes the generated program and protocol as well as stdout; it is not a measured schema-only removable token count.
- Exact rendered schema blocks occur0 times in call021's visible tool stdout; calls022 and028 contain one full set. This is not evidence that all schema information was absent earlier: other representations, individual arguments, prior memory, or summaries may contain useful information. It is evidence against assuming an already-visible identical schema copy.
- P117's whole-literal matcher does not cover this multi-block-with-labels format. The older contemporaneous documentation-API recognizer also does not apply to this zero-API persistent-schema print.

Repeated API response versus actual duplicate stdout:

- Across all six P122 CSV runs,130 saved model requests were inspected for duplicate nonempty **whole stdout strings inside the same active input**, restricted to successful, nontruncated, no-error, no-unknown-effect, non-completion observations. Duplicate boundaries:0/130. This is not an all-substring/semantic deduplication claim; paged or nonstandard observations are not established duplicate candidates by this scan.
- Earlier seed57 library repetitions were diagnostic equality after excluding access-token values. Authorization was never assumed interchangeable. With full arguments including authentication and the old conservative six-read-API intervals, seed57 and257 have0 repeated-read candidates.
- Seed157 has13 exact same-request/same-result repeats in each arm within those intervals: one `show_song_library` repeat and12 `show_song` repeats. Both arms stop before checkpointing. The12 song repeats are the kind of ordinary complete-response reuse already implemented in P106. A later full response equality is diagnostic evidence, not retroactive cache authorization or a measured12-API saving.
- Same API payloads do not imply identical stdout: Python may select, label, reorder, aggregate, or combine results. P113 had already established this distinction in prior history.

## Decision support after P123 closes

No new intervention should be selected by looking at P123 interim outcomes. The already-authorized run can proceed while this history review remains read-only.

1. Reject **whole-stdout exact deduplication as the immediate CSV mechanism**: the closed130-request scan found no active-input opportunity. It is still a strong ordinary baseline for any future more elaborate duplicate-aware policy.
2. Treat **expanding ordinary API caching** as baseline work, not a novel method. Seed157's12 repeated song reads motivate a compatibility/control check; seed57's large schema print is a different cost. A cache must preserve authorization, state barriers, errors, budget accounting, and full returned values.
3. The narrowest unimplemented display candidate is **replace only complete, exactly matched, already-public schema segments with a stable archive reference while preserving every unmatched label/value, code, receipt, error, and newest complete turn**. Matching must use the already-exposed frozen catalog, not arbitrary task payload similarity. Return full text when matching or visibility is uncertain. This extends P44/P117 coverage to persistent-state/mixed-block stdout, but is conventional selective disclosure and is not an established novelty claim. It does not address the pre-checkpoint seed157 API limit by itself.
4. A minimal informative future comparison would hold task starts, decoder, budget, error policy, state, schema capability, reference access, and common explanatory instructions fixed across **full display**, **ordinary size/recent-output cap with archive recovery**, and **the exact public-schema segment policy**. Otherwise a win over unrestricted history only does not distinguish semantic selection from generic size limiting. If ordinary exact dedup has no activation, report that rather than inventing duplicate opportunities. Count creation/control/recovery costs, actual next actions, total tokens/cache/time, final independent success, unknown usage, and fail states. The policy is only a proposal to consider after fixed-run closure; no implementation or experiment was launched here.

What must not be repeated as a novelty claim: archive IDs, reversible omissions, variable inventories, persistent Python, plain schema compaction/indexing, complete-response memoization, read-result coalescing, state/authorization invalidation, successful-execution-driven reasoning deletion, or local token accounting. Their implementation details and their limits already exist in this repository, and its prior-scope documents also record external overlap. This review does not independently establish the novelty or publication status of any external paper.

## 追加診断の手順と計数上の限定

[正確な判定手順](closed_csv_method.md)を併記する。144は130入力・12 events/spans・2 program入出力の固有ソース数であり144モデル入力ではない。17,543は一致schema blockの長さの合計で、異なるblock間の非重複区間を追加検証した値や削除可能文字数ではない。重複0は定義した正常stdout全文だけの結果で、paged/非標準表現や部分文字列の重複不存在を示さない。

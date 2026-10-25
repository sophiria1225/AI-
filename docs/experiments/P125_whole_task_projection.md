# P125: 部分応答再利用の全仕事比較

状態: 実装準備中。P124の全20プログラム一致、P123の全12条件の評価・監査・所有server閉鎖を確認し、source/planと同一head CIを固定してから開始する。原稿はユーザーが執筆する。

## 目的と比較条件

生成Pythonの限定ループから需要fieldを認識し、同task/revisionで既に得た別APIの応答が十分なときだけ、中間反復の完全readを省く。最後の元rootは元位置で完全な実dictにする。P124の固定応答再生では通常完全cacheの68取得に対し57取得、全20プログラムのstdout/errorと方式間の境界が一致した。ただし実タスク品質や総トークン削減は未測定であり、ここで検証する。

比較軸は `eager_cached` と `automatic_projection_cached` のみ。通常complete-response cache、stateful `call_api` interface、公開schemaのエラー補助、型付きAPI応答、単発checkpoint、元archiveでの全返却reasoning保持、receiptのcolumns/rows表示を共通にする。checkpoint後のモデル入力では古い履歴を要約に置換するが、全費用と元archiveは保持する。元のAPI記録とread_spanは保持する。モデルに明示的read_viewを選ばせない。実装の内部metadataを新しいモデル入力にはしない。

receipt表示の普通の短縮だけで勝ったと誤解しないため、同じ簡潔化を対照にも適用する。省略したfull API本文は元々そのままLLM履歴へ入っていたわけではない。直接差は実際に発生したreceipt indexとその後の再入力、間接差はAPI予算・行動・補修turnの変化として測る。API回数、wire byte、wall timeは総logical tokenと別に報告する。

閉鎖P122の全24試行・432生成プログラムを同じ固定認識器で静的確認したところ、対象になったのはCSV・seed157の4件だけだった（[集計](../P125_prior_static_coverage_20261026.md)）。実行時の部分再利用とは別の判定だが、現時点で適用範囲が狭いことを示す。対象APIをループ内で読む全4件はすでに受理され、構文制限を緩めるだけで追加される対象は0件だった（[適用範囲の診断](../P125_prior_applicability_gap_20261026.md)）。4件は2つの異なるsourceの各2回であり、独立した4種類のcodeではない。この結果を受けても下記条件は変更しない。

## 有限の8条件

- 従来の既知4課題（写真、立替、返金、CSV）を各2方式で最初から実行する。新しい課題要件、reserved scenario、独立評価の中身は参照しない。
- model seed157、world seed42、反復1。seed157は閉鎖済みCSVで適用箇所があったための開発条件であり、未見seedでも効果があるとは主張しない。
- 順序は写真: eager→projection、立替: projection→eager、返金: eager→projection、CSV: projection→eager。初期paired prompt・tool・payload・native入力計数が完全一致することを事前確認する。
- 各cellはmodel80呼出・全役割450,000 logical入力+出力token・仕事1,800秒。agentとfocusの費用は共有。出力cap4,096、context65,536、要求timeoutは最大600秒かつ仕事残時間以下。自動retryなし。
- API上限は元の写真160、他3課題各80。8条件合計800。独立評価は最大8回、各180秒。setup120秒、cleanup180秒、idle回復60秒。server lease21,600秒。全8cellのこれら上限合計18,720秒にserver準備等が加わる。
- 共通checkpointは既存のtrigger16,384入力token、直近2turn保持、機会1回、summary出力4,096、temperature0.7。summary生成・失敗・無効summary・再入力も全費用へ含める。意味保存の証明とはしない。
- P125用の独立namespace/cache/環境を各cellに作る。他方式や元traceのfull値を注入しない。sourceは実行前後で照合し、既存試行・失敗を上書きしない。

事前入力計数は初期8要求と語彙だけのsummary transport1要求。model生成、環境API、評価器はこの段階では0。計数失敗も保存し、失敗した事前計数を消して再実行しない。

## 例外と閉鎖

未知構文、alias、組み込み関数変更など、限定認識器の条件を満たさないcodeは通常実行へ戻す。部分再利用の後に例外・契約違反が発生した場合は、そのcellのinterpreterを閉じ、モデルを再開せず、復元取得を成功として扱わない。既知の作用でcleanupを確認できた `projection_contract_stopped` は独立評価して失敗費用も残し、次の独立cellへ進む。未知API作用、cleanup不成立、一般的な実行基盤の異常、ユーザー停止はbatchを止め、未実施枠も残す。

部分再利用前の通常Python/API例外には従来の修復機会がある。任意Pythonの全例外経路で同値とは主張しない。CSVで見つかった未観測IDの作り直しを、この機構が修正するとも主張しない。ID gateは今回追加しない。閉鎖後の診断でその影響を分ける。

## 固定した判定

8枠すべての独立評価、使用量既知、監査エラー0、projection契約失敗0を要求する。契約停止後のDBが独立評価では成功した場合、その成功と費用は変更せず、方式の採用判定だけを不合格にする。対照が成功したtaskの成功を一つも失わず、全4taskの総入力+出力token合計が減り、両方式が成功したtaskだけでも合計が減ることを要求する。さらに両方式が成功したtaskで提案側の実partial hitが1回以上必要である。成功taskが空、未発動、APIだけの減少、安い失敗、未知費用の0補完は合格にしない。

全8枠を閉鎖するまで途中の成功・tokenを見て条件を変えない。全体結果を見てから次の有限実験を判断する。このplanには追加16枠や自動拡張を含めない。4つの既知task・1反復による開発比較であり、統計的非劣性、未見課題への汎化、技術新規性の成立、採択可能性は別途の検討事項である。

基本的なprogram slicing、query projection、semantic caching、lazy evaluationは先行する。今回の技術対象は、現在の生成codeの需要・既観測API間契約・永続interpreter境界での完全root・後続取得と失敗の費用を組み合わせた限定ハーネス制御である。新しいcache原理や汎用compilerとは記載しない。

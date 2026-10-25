# P124: 同じ保存 prefix で backend 応答消費は 68 → 57、純減 11

2026-10-26。閉鎖済み P122 の既知 CSV prefix の最初の 10 プログラムを、通常 complete-response cache を共通にした 2 条件で各 1 回再生した。全 20 プログラムの元出力との比較と、10 対の境界比較が一致した。保存 backend 応答の消費は 68 から 57 へ、**11 件・16.176% 減少**した。実環境 API は呼んでおらず、全仕事の精度維持・総 token 削減は未測定である。

## 全件の会計

| 指標 | 通常実行＋完全値 cache | 自動 projection＋完全値 cache |
|---|---:|---:|
| 試行・完了・比較したプログラム | 10 | 10 |
| 保存列と対応した論理要求 | 80 | 80 |
| 消費した保存 backend 応答 | 68 | 57 |
| 普通の完全値 cache hit | 12 | 1 |
| prefix の既観測 field による partial hit | 0 | 22 |
| 制御要求 | 100 | 100 |
| うち境界 snapshot | 10 | 10 |
| 制御要求 byte | 16,624 | 17,726 |
| 制御返答 byte | 52,009 | 46,989 |
| プログラム処理時間の合計、秒 | 0.504417 | 0.466103 |
| session 終了処理、秒 | 0.089638 | 0.094769 |

各条件の会計は `論理要求 = 保存 backend 応答 + 完全値 cache hit + partial hit`。**22 partial hit を 22 件の純減とは数えない。** 各条件は別の namespace、provider、完全値 cache を持ち、省いた完全返答を後から無料で cache に入れていない。

| 区間 | 通常側：保存応答 / 完全値 hit / partial hit | projection 側：保存応答 / 完全値 hit / partial hit |
|---|---:|---:|
| プログラム 1–8 合計 | 20 / 0 / 0 | 20 / 0 / 0 |
| プログラム 9 | 12 / 0 / 0 | 1 / 0 / 11 |
| プログラム 10 | 36 / 12 / 0 | 36 / 1 / 11 |

プログラム 9 では中間 11 read を部分値で満たし、最後の read は完全値を得る。次のプログラムでも部分値を使う一方、先に完全取得しなかった 11 件は普通 cache hit にならない。この相互作用を含めた差が `68 − 57 = 11`。各プログラムの要求・応答数、照合 bool、出力・境界 hash は[全 20 行の集計](../reports/P124_projection_replay.json)に残した。

## 確認した境界と、確認していないもの

保存された action の順序・全引数を一対一に対応させ、普通 call、完全値 cache hit、partial hit のいずれかで各要求を説明した。partial lookup はそれ以前に得た公開値だけを使い、その後に保存された返値と必要 field の一致を検査した。将来の保存返値を lookup の種として注入していない。

status、stdout、truncation、error、completion/unknown-effect flags は元記録と全 20 件で一致した。両条件の 10 境界では、対象 root が存在すれば実 `dict` の全値 hash と、対象となる plain namespace の型・構造値 hash が一致した。任意 object identity、全 heap alias graph、外部作用、未知の将来プログラムや例外経路までの同値を証明したものではない。保存プログラム内の対象選択の誤りも、この再生では修正・独立評価していない。

実環境 API、モデル生成、tokenizer、評価器は各 0。内部 result の `api_requests` は保存 backend 応答を消費した simulated ledger の数であり、実環境 API 件数ではない。制御 byte は interpreter と host の通信であり、LLM 入力 token へ換算しない。

再生処理全体は 1.310144 秒、開始・終了 marker の時刻差は 1.312429 秒。境界 snapshot の費用は制御数・byte・処理時間に含む。各 1 回の固定順序で、再生用の保存返答と監査処理を含むため、速度向上を主張しない。両 session の終了、container 除去、exit code 0、OOM なし、各 14 制御項目の成立を確認した。

## 準備失敗と実行回数

最初の head `a999a7cce893eeee63ff067be4f4d4eecd4d4411` の prepare-only は、歴史的な元 cell に存在しない `provenance.json` を要求し、`regular_file_required` で拒否された。manifest は作られず、保存プログラム・モデル・API・Docker の実行も開始していない。元記録は変更していない。この準備失敗を、再生実験の失敗や消去した再試行として扱わない。

実在する source identity / comparison plan と保存 schema map へ準備処理を接続した head `d3eb9cc02dc16d29150522c3014753ea4c734af1` で manifest を固定した。同じ head の push・pull_request CI 成功後、2026-10-26 07:01 JST に実再生を **1 回だけ**実行した。終了時に固定実装の hash 不変を確認した。元の[実行前仕様](experiments/P124_projection_replay.md)は履歴として更新せず保持する。

## 公開集計の検査と次の判断

[集計器](../scripts/build_projection_replay_report.py)は閉鎖 summary、両 session、開始・終了、元 manifest とその copy、準備失敗 marker の計 8 ファイルを hash で束縛し、20 行、対応する 10 対の hash、論理要求の会計、session 件数、終了状態を再照合した。入力 manifest の範囲は private 36 ファイル、公開 schema 22 ファイル、実装 1,095 ファイル。個別 private 名や値は出さず、manifest の件数と mapping hash を残す。この集計工程は元の保存コードを再実行していない。

[合成 reporting 検査](../tests/test_projection_replay_reporting.py) 5 件が成功した。hash 改変、欠落行、境界不一致、会計不一致、未終了 session、実測していない品質主張、private field の混入を検査した。これとは別に[独立監査](P124_independent_audit.md)で200制御返答のwire byte/hashと先行応答からのcacheを再構成し、全件一致を確認した。[監査集計](../reports/P124_projection_replay_independent_audit.json)を公開する。

通常完全値 cache を超える保存応答消費の差と、この固定 prefix の正常境界一致は得られた。次は同じ通常対照を保った開始時点からの有限 online 比較で、全仕事の成功・input/output token・修復・再取得・完全化・制御時間を測る必要がある。API 減少から総 token 削減、新規性、未見課題への一般化を導かない。

[全件資料](../materials/20261026_p124_replay/README.md)／[公開集計](../reports/P124_projection_replay.json)。global ledger 登録と current README の変更は、この結果作成工程では行っていない。

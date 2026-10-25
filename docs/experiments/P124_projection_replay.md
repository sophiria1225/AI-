# P124: automatic field projection の有限 prefix replay

状態: **実装・合成検査のみ。保存プログラム replay は未実行。** ソースと private manifest を固定した後、親の実行担当が一度だけ開始する。

目的は、通常 complete-response cache を共通対照にして、限定 AST projection が保存 prefix で追加の backend-response 省略を起こし、観測可能な正常境界を保つか確認すること。成功率改善、総トークン削減、実環境での反実仮想、新規性の証明ではない。原記録の課題結果を置換しない。

## 固定対象と上限

- 閉鎖済み P122 R02 CSV の SINGLE_CHECKPOINT、最初の 10 Python programs。既知データのみ。具体の run、入力・返答・元出力の全ファイル hash は private manifest に束縛する。
- `eager_cached` と `automatic_projection_cached` の 2 arms、同じ 10 programs、最大 20 generated programs。
- 各 arm は独立した Docker interpreter、namespace、public authority、ordinary cache、revision、simulated request ledger を持つ。最初の program から状態を再構成する。対象 10 programs の `observations` は exact empty list であることを prepare / run の両方で要求し、実行にも空リストだけを渡す。元 trace の非空 observations による、省略 full reply の無料再注入は許さない。非空なら対応関係を推測せず拒否する。
- 各 program 最大 30 秒、全体 600 秒。実行部分は 480 秒で打ち切り、残り 120 秒を既存 container cleanup 上限のために確保する。失敗・不一致・期限切れで打ち切り、残りを自動再実行しない。
- 実 API・model・tokenizer・evaluator は各 0。保存 code を host で `exec` しない。Docker は既存の image pin、network none、mount なし、read-only filesystem 等の制御を引き継ぐ。
- 追加の trusted boundary snapshot は 1 control / program。新たな generated program/API を作らず、control request/reply byte に含める。

## 一対一の要求照合

各 program の保存 request/reply tape は固定する。元の要求は順番通りに次のいずれかで一度だけ消費する。

1. 元と完全一致する ordinary call。実際に保存 backend response を要求した場合だけ既存 provider が `observe` する。
2. ordinary complete cache hit。対象は既存契約の `show_song` の成功 read のみ。cache が返した**完全値**と保存された完全値の一致が必要。
3. cross-API partial projection hit。対象は同じ成功 read のみ。既存 prefix authority の lookup が先に成立し、その後、必要 field が保存値と一致することを検査する。保存値を lookup 入力や cache へ注入しない。

lookup miss は tape を消費せず、後続の普通 call が消費する。不要になったと推測した read を先読みして飛ばす方式は禁止する。未知/非 read の作用、失敗 read、順序・引数の差、未消費/追加 request は不成立とする。省いた完全値は ordinary cache へ入らない。2 programs の savings は各 arm の独立状態から数え、ordinary cache hit と projection hit を単純加算しない。

`SavedResultTransport` は外部 transport を持たない。内部の simulated receipt/ledger の sent 件数は「保存 backend response の消費数」であり、環境 API 実行数ではない。report は両者を明示的に分ける。program ごとの simulated receipt と tape 消費数、arm 全体の transport / ledger / summary 件数および pending 0 を直接照合する。元の pre-dispatch rejection も保存した拒否として再現し、新しい API response を創作しない。

## 比較と停止

各 program で stdout、truncation、status、error text、completion/unknown-effect flags を元記録と比較する。後から例外文を都合よく正規化しない。2 arms でも stdout/error と boundary snapshot を比較する。

snapshot は trusted bootstrap 内で、元の direct `show_song` に束縛された root が absent なら absent、存在すれば実 `dict` の全値 hash を取得する。追加で観測可能な plain namespace の型・構造値 hash を取得する。通常の underscore 変数も含め、除外は既知 runtime binding に限定する。後続保存 code から得た root 名はこの検査にのみ用い、policy / lookup / cache へ渡さない。未知 object に `repr` 等を呼ばない。object identity、heap alias graph、時刻、外部作用、将来プログラムの同値は対象外。受理 compiler は `is` / `is not`、reflection、未知 callback 等を全体 eager に倒す。snapshot の値や元 code を公開 report へ転載しない。

runtime は fresh ordinary-channel reply に基づいて API control wrapper だけを除き、元の例外応答を保つ。replay は保存した API error payload と program error text の両方を完全一致で検査し、文字列の strip / repair は行わない。最適化中の contract failure は既存停止方針に従い、復元取得や retry を行わない。不一致時は次の live 比較へ進む前に原因を閉じる。

## 実行入口（親がソース固定後に使用）

`--prepare-only` は manifest の準備だけを行い、Docker や保存 program を実行しない。

```sh
python3.12 scripts/probe_automatic_projection_replay.py \
  --storage-root /Users/tp26013/AI- \
  --repo-root /Users/tp26013/AI-/.runtime/worktrees/p124-projection-prep \
  --data-root /Users/tp26013/AI-/.runtime/appworld/r18_probe_01/data \
  --manifest /PRIVATE/P124_input_manifest.json \
  --prepare-only
```

準備時に public schema provenance、10 programs の順序、原 input/result/wire/events/spans と現 implementation hashes を確認する。実行 repo と指定 repo の resolve 一致を要求し、scripts / tests 内の全 Python source、固定 container config、この replay 仕様書を manifest に束縛する。実行時も全 hash を再照合し、終了時に implementation hash が変わっていれば不成立とする。同じ引数から `--prepare-only` を除き、新規 private `--output` directory を指定すると最大 20 programs の replay に進む。既存 output / manifest を上書きしない。public AppWorld serializer の固定 hash も実行前に照合する。

最小検査は `test_automatic_projection_replay.py`。合成 host controls と trusted snapshot を検査し、保存プログラムや Docker は実行しない。対応する compiler / runtime の検査も実行担当が source 固定前に確認する。

合格しても、この固定 response 下の観測境界一致と backend-response 消費差だけが結論となる。次の実環境比較で品質・総費用を測る判断材料に限定する。

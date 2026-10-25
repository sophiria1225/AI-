# P124 閉鎖済みreplay独立監査

判定: **PASS**。対象は固定P124 replay v01のみ。保存programの再実行、モデル・AppWorld API・tokenizer・評価器実行は行わず、記録の解析と対象2containerだけのread-only inspectを行った。P123途中結果は閲覧していない。

| 項目 | eager_cached | automatic_projection_cached |
|---|---:|---:|
| 実行・比較済みprogram | 10 | 10 |
| 論理要求 | 80 | 80 |
| 保存backend返答の実消費 | 68 | 57 |
| ordinary complete cache hit | 12 | 1 |
| cross-API partial hit | 0 | 22 |
| control要求 | 100 | 100 |
| control要求payload bytes | 16,624 | 17,726 |
| control返答payload bytes | 52,009 | 46,989 |
| control payload合計bytes | 68,633 | 64,715 |
| interpreter返答wire bytes（schema/header込み） | 120,093 | 115,073 |

追加の保存backend削減は **11件（68件比16.18%）**。partial 22件に対し、普通cache hitが11件減るため、22件をそのまま追加削減と数えてはいけない。program 9で12→1件、program 10は双方36件の保存backend消費。変換はautomatic側program 9・10の2件だけである。

独立に確認した内容:

- 元記録の80要求を両armで順番・引数hashまで再照合。成功した過去の実消費返答だけからarm別にcacheを再構成し、22 partial全件が先行library返答から充足、13 ordinary hit全件が先行full返答から充足することを確認した。省いたfull値を再構成cacheへ入れていない。
- 200 control返答を元の保存値・先行library値・report/snapshotから独立再構成し、実返答wireのbyte数とSHA-256が全件一致。control要求byte数も実wireから再計算した。summaryの集計値を読むだけの監査ではない。
- 全20programのstatus/stdout/truncation/error/completion/unknown-effect flagsが元記録と一致。全10paired境界でrootの全値hash、plain namespace hash、stdout/errorが一致し、未知objectの除外名は全件空。存在する対象rootは全件実dict。
- 元source、入力schema、空observations、候補変換source hash、実行hash、変換有無の開示が一致。sourceを実行せずhashと保存reportを確認した。
- armごとのledgerは0から開始し、各programのspent増分が保存backend消費数と一致。全境界pending=0、stopped=false。sessionは2つの異なるIDで、実装上も状態を別に生成する。
- 両sessionは10program後にclosed、exit code 0、OOMなし、container_removed=true。14個の隔離条件が記録上すべてtrue。対象の正確なcontainer IDだけをinspectし、現在も存在しないことを確認した。
- implementation 1,095 files、原input等36 files、public schema22 filesのhash一致。監査前後とも固定treeはclean、HEAD一致。開始/終了記録・manifest・summary・single-run wrapperのhash連結も一致し、失敗/再試行artifactはない。

固定HEAD: `d3eb9cc02dc16d29150522c3014753ea4c734af1`

Manifest SHA-256: `9ade627e17f4d022d6262af391652586d03846aa236e6a672f215e62dc3a90f4`

Summary SHA-256: `1984ec8bb06acc57e8f298ff7ba4f037d5ba87a61d0a2ee07ac25418640663a9`

実環境API/model/tokenizer/evaluatorは各0。これは保存返答transportに外部transportがなく、固定実装と開始/終了記録がその経路を示すことによる確認で、system全体のnetwork captureによる独立証明ではない。

結論の範囲は、固定返答prefix上の正常境界一致と保存backend消費差である。1.31秒の記録時間やcontrol byte減少を、実環境latency改善やLLM token節約とは扱わない。実タスク最終品質、全仕事logical input+output tokens、live counterfactualは未検証。JSON版にprogram別件数・hashと監査条件を保存した。

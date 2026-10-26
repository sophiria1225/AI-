# P129 会計と再現の境界

全6条件を保持する。各方式1/2成功、seed57はすべてusage1件不明、seed157はすべて成功。各方式514,496は既知小計であり総費用ではない。全体差と事前gateの共通成功差はnull。使用量既知の共通成功1対だけは各295,152、差0と別に記述できる。安い失敗や成功改善を同じ成功の費用削減へ数えない。

feedback block、repair proposal、sent repair、strict repairは全0。strict repairはcontent差・実送信・typed成功返答・同じeffective contentの保存根拠を要求し、公式task successとは別である。seed157では各write check1が元内容supportedで、seed57では対象write check0だった。共通cacheやexplicit fieldの使用を修復の効果と呼ばない。

actor/focus、summary、失敗・notice・回復を全仕事logical入力＋出力へ含む。cached inputは差し引かず、unknownがあればnested input/output/cachedのexact totalもnull。API/byte/timeはtokenへ換算せず、重なる時間を加算しない。固定gate false、元監査エラー0、契約停止0を維持する。

元collector出力と図v01は同bytesで保存した。公開独立監査はprivate path/checkラベルを省いた集約であり、元private reviewのbytesではない。元結果・check集合・source集合のSHAと79,576 checks通過件数を保持する。rendererはこの公開集約でも全6条件と固定sourceを検証できる。元図manifestのprivate review hashと公開集約のhashは異なり、再描画時の新manifestは公開集約を参照する。PDFの作成日時metadataにより再描画PDFのbyte同一性は保証しない。元図を上書きしない。

再描画はrepository rootから次を実行する（matplotlibが必要）。`NEW_DIRECTORY`は存在しないdirectoryにする。

```sh
python scripts/draw_p129_results_20261026.py --repo-root . --closure-record reports/P129_closure_once_end.json --collector-record reports/P129_report_collector_once_end.json --collector-start reports/P129_report_collector_once_start.json --pipeline-start reports/P129_pipeline_once_start.json --independent-review reports/P129_closed_independent_audit_20261026.json --output-dir NEW_DIRECTORY
```

純粋monitorとformatter等の固定実装共有、producer rolling監査への依存を残す。保存生成code/evaluator本文の再実行や意味検証は行わない。1既知課題×2seedの通常校正で、新規性・一般品質・採択は未確立。

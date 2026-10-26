# P125: 閉鎖後の独立再計算

全8条件と所有serverが閉鎖し、元audit・server会計・資料生成・collectorが正常終了した後に実施した。元auditor/summarizerをimportまたは実行せず、別の標準ライブラリ実装で再計算した。v02は25,566検査がすべて通過した。

固定実行head、planの1,125 source、全8枠、元usage/admission/terminalの対応、request/response hash、official評価boolとhash、API events/typed receipts/reservations、program/control/lookup/cacheの保存件数、全体・方式別・共通成功の費用、固定gate、server時間の分解とmemoryを照合した。保存生成コード、モデル、実API、tokenizer、評価器を追加実行していない。

独立結果も、各3/4成功、各766,875 token、共通成功3課題の各618,487 token、未知使用量0、全8合計1,533,750 token、154モデル呼出し、488実API、partial hit0、通常cache hit0、projection契約失敗0、採用gate falseで一致した。CSVだけが両方式ともAPI上限80で失敗した。監査通過は方式の採用を意味しない。

## 初回の監査失敗を保持

初回v01は末尾の `sampled_swap_peak` だけで失敗した。全1,280 sampleのswap値はfloatの0.0、固定server実装のpeak値はintの0だった。初回の独立監査が数値として同じ0を厳密JSON型比較で不一致にしたためで、実験中のunknown usageやメモリ記録の欠落ではない。

v02では、固定server実装と同じくbaselineと全sampleを含め、各値の `or 0` を適用したpeak定義で再計算した。v01のscript・FAILED JSON・説明を保持し、別名のscriptと出力で再監査した。元P125実験source、元audit、server record、usage、評価、collector、採用規則は変更していない。

v01失敗を受け、図の自動待機処理は描画せず終了した。v02のPASSを確認後、同じ検証済みrendererで最初の実データ図を別のpostprocessing記録の下で生成した。追加モデル実験や失敗cellの再実行は0である。

## 範囲

request/responseのhashは元保存物との一致、費用・評価boolは元記録との再計算を確認する。独立評価器の本文を調べたり、その正解をモデルへ渡したりしていない。control reply byteはhashで束縛された保存metadataの和を照合し、wire responseを独立に再生成したものではない。hash整合だけで、保存物の作成以前にまで遡る真正性や一般的な品質維持を証明するとはしない。

[独立監査v02の公開集計](../reports/P125_closed_independent_review_20261026_v02.json)／[初回失敗と修正の来歴](../reports/P125_independent_review_correction_20261026.json)／[全結果](P125_findings.md)。

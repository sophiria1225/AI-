# 初稿の実測値と出典

この初稿は、P123・P140・P141を別の実験群として扱う。モデル実験はP141で終了し、執筆中に条件・seed・予算の追加や再試行を行っていない。未知の使用量は実入力計数値や出力予約値で埋めない。

|本文の記述|出典（repository root基準）|位置づけ|
|---|---|---|
|単発893,529、別反復785,656、同時836,922、各4/4成功|`docs/P123_findings.md`, `reports/P123_comparison.json`|通常対照の選定根拠。提案機構の効果に数えない。|
|P140 TR4/4、ED/EDO3/4、既知小計と不明件数|`docs/experiments/P140_findings.md`, `materials/20261028_p140_results/conditions.csv`|元の全4課題比較を保持。|
|P140 EDO表示入力14,027→6,058|`reports/P140_comparison.json`, `materials/20261028_p140_results/model_calls.csv`|同一境界の表示比較と採用後の実入力。全体成功・削減とは別。|
|P141 TR332,588成功、TDO329,781成功、EDO317,920既知＋不明1失敗|`reports/P141_comparison.json`, `materials/20261028_p141_results/conditions.csv`|元Task4の事後選定・各1回・固定順の診断。|
|TDO−TR = −2,807（−0.843987%）|`materials/20261028_p141_results/pairs.csv`|両行の全role使用量が既知の記述的差。全3条件の固定totalがnullであることとは区別。|
|actor差−2,753、focus差−54|`materials/20261028_p141_results/model_calls.csv`|要約処理込み。API要求は76→78で、全資源が改善したわけではない。|
|最初の時機差after19、strict false／canonical true、実送信役割差と両使用量既知|`reports/P141_comparison.json`, `materials/20261028_p141_results/summary.json`|protocol IDだけの対応。意味・隠れた状態の同一性は保証しない。|

P141実行sourceは `5cab33a2e239f3e6d90e63e32c54ba0764b1c594`、plan SHA-256は `5dd2581f4aae9fc8831768018a9fe00835c74e8b4f8506d0b77bda5f155ac18d`。実行と結果処理を閉鎖し、所有プロセスの終了を確認してから結果を読んだ。原集計・原監査・評価器の再実行はない。

全体の会計に使用量不明1件があるため、元の全3方式一括 `total_tokens_by_mode` はすべてnullのまま残す。個別のTR/TDOは使用量がすべて既知で、両者の対応差だけが確定する。すべての科学的採用フラグはfalseであり、診断結果を採用判定へ変更しない。P140の非介入3課題を合算してTDOを4/4確認済みとせず、未見12課題の確認も実施していない。

## 方法と先行研究

Eは前回の費用既知focus以後のactor実入力について、対象raw除去前後のnative計数差の正の部分を累積する。raw除去の起点は前回の採用位置であり、Eのreset起点とは別。Cは不採用を含む直前の有料focus実入力＋出力。P140/P141の最大2機会には未送信・不採用も含む。P123の反復上限は3で、実際の採用は最大2回だった。

差分計数自体はTCA、長文脈圧縮はLongLLMLingua、エージェントの圧縮方針最適化はACON、キャッシュを考慮した履歴管理はTokenPilotの先行成果である。ACONも要約器を含む費用・実行時間を評価しており、全体費用評価そのものを新規性としない。本稿では具体的な発動規則と、保持表現／時機の限定比較を研究対象にする。世界初・最適性・一般的非劣性は主張しない。

文献の正式版は `references.bib` の各URLで確認した。TokenPilotはFindings of EMNLP 2026正式版の著者一覧を用い、ACONはICML 2026/PMLR版を用いる。TCAは査読済み掲載先を確認できていないためプレプリントと表示する。

投稿前に必要な著者側の確認は、著者名・所属・会員種別・住所、原稿全体の研究上の主張、公式クラス現版での最終組版である。初稿PDFの作成は投稿を意味しない。

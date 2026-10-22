# 公開証拠による通常終了制御 — 全２条件の結果

[５枚PDF](AI_harness_ordinary_completion_20261023.pdf)／[HTML・説明メモ](index.html)／[全結果・限界](../../docs/P66_findings.md)／[全監査](../../reports/P66_completion_audit.json)。全５頁を目視確認、レイアウト不一致０。表紙は題名のみ。

既知の写真１課題の２条件は両方公式成功。文書取得必須は130,439→91,116 token、公開名アクセスは151,664→112,233 token、約30.1％／26.0％の減少を観測した。各２生成・４ API減、完了通知は残す。全25生成203,349 token、199 API、２評価、使用量不明０。判定＋digestは合計0.028224秒で、保存や通知も全体時間に含む。

実行した公開APIの前半と最終13 DBは一致。一方、呼出しIDが異なるため要求・モデルメッセージ全文の完全一致は不成立で、事前基準を変更しない。[ID差分の読取診断](../../reports/P66_identity_differences.json)。既知１課題・各１回の局所的な改善で、手書きの通常検査を独自手法や一般的品質維持へ昇格させない。

監査1,721項目不一致０、所有推論器1,059.910秒で正常停止、保留群０。[固定計画](../../docs/experiments/P66_ordinary_completion.md)／[設定](../../configs/P66_ordinary_completion_v01.json)。出典と生成処理のハッシュは[manifest](build_manifest.json)。再生成は `scripts/build_completion_control_report.py --pdf`。

[前段P64/P65の５枚資料](../20261023_p64/README.md)／[現在の研究状態](../../docs/current_status.md)。原稿の中心貢献・公式様式・著者情報は未確定のまま、10月31日の投稿を目指す。

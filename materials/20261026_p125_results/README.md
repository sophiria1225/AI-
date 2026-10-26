# P125: 全 8 条件の監査済み集計

既知 4 課題 × 2 条件の全枠を残す。両条件は通常 complete cache、同じ lossless receipt 表示、単発 checkpoint を共有する。要約・失敗・修復・再取得を含む全仕事の token と、共通成功課題の費用を別に示す。未実行・未評価・監査エラー・使用量不明を 0 や成功へ置き換えない。CSV の空欄と JSON の null は欠測を表す。known subtotal は確定総費用ではない。

API、制御 byte、時間は token と別の指標である。program/control/lookup は仕事時間内、cell と評価は server 時間内なので重複加算しない。共通成功課題だけの小計は全 8 条件の代わりにしない。mechanism failure flag と事前の採用規則を保持し、一般的な精度維持や新規性をこの builder が認定することはない。

[全条件](conditions.csv)／[集計](summary.json)／[出典と生成物 hash](build_manifest.json)／[監査](../../reports/P125_comparison.json)／[server 会計](../../reports/P125_server_session.json)。課題値、コード、推論、プロンプトは転載していない。実験解釈と原稿への採用判断は別途行う。

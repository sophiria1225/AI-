# 再開の入口：P127全8条件閉鎖・未発動原因を診断（2026-10-26）

P127は2026-10-26 13:08 JSTに全8条件・所有server・collector・後処理を閉鎖した。両方式とも3/4成功、全仕事logical入力＋出力695,217 token、共通成功352,584 tokenで差0。全132 programで静的受理・変換・automatic partial hit・明示field要求は0、CSVの通常完全cache hitは各72。使用量不明0、契約停止0、監査エラー0、固定gateはfalse。CSVは両方式とも117 APIで完了宣言したが独立評価は失敗した。

[全件所見](docs/experiments/P127_findings.md)／[全8条件資料](materials/20261026_p127_results/README.md)／[実図](materials/20261026_p127_results/figures/README.md)／[会計注記](materials/20261026_p127_results/INTERPRETATION.md)。

## 再起動しないもの

P127は11:45 JSTに一度開始し、13:08 JSTに閉鎖した。実行head `0219f774326e7e4e2fdacc6aaaf0c45ea381cfc0`、plan SHA `49edf3731b6d4caf79ef7b90f84b928cb7269ebb541148687e444c2bb9557bff`。`p127-run` と `p127-region-online` は凍結済みで編集しない。prepare、pipeline、wrapper、collector、独立監査、図の自動後処理を再起動しない。

[閉鎖marker](reports/P127_closure_once_end.json)はaudit/session/reportすべてexit0、[collector](reports/P127_report_collector_once_end.json)と[後処理v02](reports/P127_closed_review_wait_v02_end.json)はcomplete。所有server停止と所有PID不在を閉鎖後監査で確認した。後処理v01は待機中だけ期限判定を修正し、model実験は中断していない。[修正記録](reports/P127_closed_review_wait_v01_prelaunch_correction.json)。

結果公開木は `p127-results`。元結果と図は同bytesのcopy、解釈・会計注記は追加fileへ分離する。P127には開始snapshot179台帳/2,122束縛を使用した。後で増えたglobal台帳を旧凍結木へ当て、新file不足を破損と扱わない。

## 次に行うこと

[全132 sourceのAST診断](docs/experiments/P127_admission_diagnosis.md)は終了。対象2 program/方式は完全応答を永続dictへ保存するため拒否され、構文緩和だけで安全な取得省略にできない。限定したmechanism gapがなければ同条件反復・seed探索をしない。次のモデル比較は結果に根拠がある有限計画に限定し、source/CI/全条件/予算/採否/期限内閉鎖を固定して説明してから実施する。単一local serverを共有する。現在新モデル比較は未開始。

[次の作業](docs/next_actions.md)／[現在の状態](docs/current_status.md)。原稿はユーザー担当。普通のメッセージは停止扱いにせず、明示停止を優先する。未見12課題は確認計画固定前の未閲覧を維持する。

## 旧記録

[P126](docs/experiments/P126_findings.md)は保存prefix48件の局所再生、[P125](docs/P125_findings.md)は両3/4成功・766,875 token・機構未発動、[P123](docs/P123_findings.md)は各4/4成功・同時反復gate false、[P124](docs/P124_findings.md)は保存20 program再生。全旧wrapper/collectorを再実行しない。旧失敗・未知費用・原稿・固定sourceを保持し、条件の異なるphaseを同一反復へプールしない。

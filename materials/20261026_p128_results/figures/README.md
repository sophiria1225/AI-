# P128 閉鎖後の図

全16条件を保持した実図。両方式の総費用は未知を含むためopen triangleで既知小計を示す。seed別の品質差、全体と共通成功を分離する。2seedは同じ既知4課題の反復。新規性・一般品質維持を主張しない。

元自動描画v01は同bytesで保存: [課題別token・成否 PNG](v01/p128_task_tokens_outcomes.png) / [PDF](v01/p128_task_tokens_outcomes.pdf)、[全体・共通成功・成功数 PNG](v01/p128_totals_success.png) / [PDF](v01/p128_totals_success.pdf)。[元data](v01/figure_data.json) / [元manifest](v01/output_manifest.json) / [元再現手順](v01/README.md)。

v01総費用図のseed57/全seed panelではunknown注記が一部重なる。元図を上書きせず、注記位置だけを直したv02を別保存した。**全16行dataはv01と同bytes**、集計・判定・検証条件は同一。

閲覧用v02: [課題別 PNG](v02/p128_task_tokens_outcomes.png) / [PDF](v02/p128_task_tokens_outcomes.pdf)、[全体・共通成功・成功数 PNG](v02/p128_totals_success.png) / [PDF](v02/p128_totals_success.pdf)。[data](v02/figure_data.json) / [manifest](v02/output_manifest.json) / [再現手順](v02/README.md)。

v01は閉鎖時の自動描画、v02は同じ公開集計からの表示修正。v02は公開safe監査集約を読み、元private reviewのhashと109,295 checks通過件数を保持する。再現は新出力directoryへ行い、元図を上書きしない。

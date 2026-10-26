# P133: 有料要約の実測予測による採否、全4条件

既知CSV1課題×rolling_separate/empirical_payback×事前固定seed57/157を全件保持する。P123と同じ通常interface、full receipt、API80、反復要約を共通とし、初回focusは両側で通常許可する。2回目以降だけ、過去の採用済み入力短縮量、paid focus費用、既知actor/focus時間、残call/timeに基づく予測を適用する。予測は償却、将来時間、完了、品質の保証ではなく、通常controller改善の校正である。新規性や一般品質維持を主張しない。

要約、失敗、actor、制御、通知、回復の全logical input+outputを数える。cached inputを差し引かない。未実施、未評価、監査不能、unknown usageを0に置換しない。未知があれば全体だけでなくinput/output/cachedのexact totalsもnull。品質改善、品質損失、共通成功、両失敗を分け、cheap failureを効率改善としない。

payback_rejectionsは共有screen通過後に新規則が実際に未送信としたrepeat focus数。shadow rejectionは通常条件の仮想判定で、実介入ではない。既存call/token/context screenの拒否は別のrolling制御であり、この件数へ加えない。初回共通許可、過去のclosed prefix、count/send入力、未送信に偽usageがないことを監査する。wallはhostの記録された観測と時系列を検査し、独立時計で測り直したとは主張しない。

固定gateは全4条件の評価とknown usage、seedごとの成功損失なし、全体と非空の共通成功のtoken低下、共通成功上の実payback拒否を必要とする。2seedsは独立2課題ではない。予測式固有の優位は、単なる終了間際予約を行う強い通常対照との追加比較も必要になる。

work・要約・制御は重なり、server時間はsetup/work/evaluation/cleanupを含むため加算しない。raw prompt、reasoning、summary、生成code、API値、認証値、private pathを公開しない。

[全条件](conditions.csv)／[集計](summary.json)／[hash](build_manifest.json)／[監査](../../reports/P133_comparison.json)／[server](../../reports/P133_server_session.json)。

## Reporting recovery v01

原実験・監査・server集計は再実行せず、旧report失敗を保持する。旧path検査が拒否した、元planにhash固定済みのmaterials6件とpapers1件のみを追加検証対象にした別集計である。元run/prep/source/計画/失敗markerは変更しない。

# P135 実行開始 — 2026-10-27 08:15 JST

P135は08:15:47 JSTに一度だけ起動した。source `d87880f474c05541d8d0cde0ec318fd262d9fa0e`、plan SHA `5a5b5338773f4a5b80ab61f9ccae9a3591c4f42ef8f458f2c38e4bc8894d8a2e`、1,498 sourceを固定した。source PR [#540](https://github.com/sophiria1225/AI-/pull/540)の同じheadについてpush/PR両CIが成功した。

モデル準備とpreflight/activationを通過し、既知CSV1課題、3方式×seed57/157の6条件を直列実行中である。この記録時点では最初のraw anchor条件のnative request保存とmodel slot処理中を確認した。途中の生成内容・成否・費用は読まず、全6条件の閉鎖後に集計・独立検算する。実行開始は成功や削減効果の証拠ではない。

P133は全4条件を終え、元の報告処理だけが失敗した。別data-only recoveryの固定証明と、P134の待機失敗がモデル・server・preflight・task未開始である証明を起動前に検証した。P135は元P134と科学条件・乱数・予算・guide・tools・処理本体を変更しない。P133集約成績は既知だが、それに応じた条件選択はない。旧失敗記録を消したり再実行したりしない。

開始時snapshotは190台帳/2,300束縛で固定し、その後のglobal台帳数を遡及しない。各条件80 shared calls、450,000 logical input+output tokens、1,800作業秒、API80。所有serverは最大6時間、18:00 JSTまでに全leaseが収まる条件で起動した。通常メッセージでは止めず、明示停止に従う。終了後はaudit→server accounting→aggregate report→別独立検算へ進む。

[固定仕様](P135_whole_task_observed_obligations.md)と[開始記録](../../reports/P135_execution_start_20261027.json)を参照。新規性、一般的品質維持、新方式による全仕事token削減は未確立である。原稿本文はユーザーが担当する。

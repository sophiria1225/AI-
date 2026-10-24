# 研究と実行の引き継ぎ

2026-10-24更新。ユーザーは就寝中も「こちらが何か言うまで実行継続」を指示した。新しい停止指示はない。再度の許可は不要で、新しい停止指示には直ちに従う。最終目標は必要情報・処理と成果品質を保った全仕事費用の削減。25日まで追加確認・採否、29〜30日原稿、31日投稿完了を目指す。新規手法・一般品質維持・採録に足る中核は未確立。

[現在状態](docs/current_status.md)、[次の作業](docs/next_actions.md)、[AGENTS](AGENTS.md)、[当初の引き継ぎ](docs/handoff_20261022_account_switch.md)を読む。古い停止記録は保存し、現在の停止指示と混同しない。

## 保存先と作業木

| 用途 | 場所 |
|---|---|
| モデル・環境・私有記録 | `/Users/tp26013/AI-` |
| 編集木 | `.runtime/worktrees/p84-prep`。現在のブランチはgit statusで確認 |
| P84の実行木 | `.runtime/worktrees/p84-run`、`1dfa3cafb9e111cffaea2b563513db890e85ebce`固定・実行中。変更しない |
| P82の終了済み実行木 | `.runtime/worktrees/p82-run`、`ce81c87ed4a456543859ee98e5aec9e7c5703b77`。終了出力を保持 |
| P82旧資料木 | `.runtime/worktrees/p82-prep`。初回配置失敗の資料・監査を保持。切替や清掃をしない |
| P84旧接続木 | `.runtime/worktrees/p84-controller`、`8af247a90e9b6994c263e387f7c63f13bd45f705`。停止済みの接続処理を再起動しない |

Pythonは保存先の`.runtime/p3_ci_venv/bin/python`、資料は`.runtime/reporting-venv/bin/python`。TeXは`.runtime/letter_tex/v2026.10/portable/TinyTeX/bin/universal-darwin`。AppWorld・vendor・モデルはGit管理外で、cloneだけでは復元しない。

## 現在動いているP84

09:25 JST、[別途の初回実行判断](docs/P84_manual_execution_decision_20261024.md)後に固定実行器を一度起動した。全６初期計数は一致し、生成中。実行セッションは51432。６入力×３反復、18生成、総予約481,671論理token、１生成480秒、生成段階10,800秒、推論器12,600秒。生成コード・環境API・評価は実行しない。

状態は`records/context_pilot/P84_pipeline_v01/status.json`、`P84_preflight_v01/status.json`、`P84_fallback_output_v01/status.json`。推論器記録は`records/p2_servers/20261024_092534`。途中の出力で順序・入力・上限・seedを変えない。未知使用量や通信失敗で停止し、再試行しない。

停止には保存先の`.runtime/P84.stop`を作り、所有実行器と推論器の終了を確認する。研究全体の停止では`.runtime/P82.stop`も作る。停止印・lockを勝手に削除しない。

P84の元自動接続はP82資料の配置失敗を受けて停止し、元の終了後資料待機も停止した。`.runtime/P84_continuation_status.json`と`P84_closure_status.json`はその記録であり、現在のP84実行状態ではない。再起動しない。元の`.runtime/P84_execution_decision.json`は作らず、別の`.runtime/P84_manual_execution_decision_20261024.json`へ判断を保存した。P82不明４件も元の自動条件も維持した。

P84終了後は、所有推論器停止・PID不在を確認し、出力がまだない場合だけ固定木で`audit_fallback_output.py --storage-root /Users/tp26013/AI-`、続いて資料Pythonで`build_fallback_output_report.py --pdf`を各一度手動実行する。全18枠と全15比較を保持し、全頁目視後に同一hashで編集木へ取り込む。既存出力は上書きしない。

## P82は全件終了

全24条件、426生成、既知4,602,713論理token、不明４生成、1,156 API、24評価、監査不一致０。M成功は3/4・2/4、H/Lは両反復3/4。全４採用基準未達。所有推論器停止・両PID不在済み。[全結果](docs/P82_findings.md)。

初回資料の２ページで表が注記に重なり、資料待機・原稿待機・P84接続待機が停止した。監査・経路・セッション・呼出し集計はすでに成功しており再実行していない。元の`.runtime/P82_closure_status.json`と`P82_manuscript_status.json`を変更せず、別の`.runtime/P82_manual_closure_status_20261024.json`に終了レビューを保存した。

編集木の`materials/20261024_p82_results`に初回失敗、`_v02`に表修正、`_final`に表紙・凡例・全８表示位置を含む最終８頁を保存した。全CSVはbyte一致。全８頁を確認済み。原稿は`papers/202610_letter/late_time_control`の本文３頁＋英文１頁を全頁確認済み。組版私有出力は`.runtime/P82_manuscript_manual_render_20261024`。準備済みの元TeX・READMEは出典固定のため保持し、新しい`RESULTS.md`が実結果の入口となる。

狭い区間解析は一度実行し、Hの未知２件に正の生成進捗がなく停止した。４欠測・既知422件の照合結果は`reports/P82_interval_failure_20261024.json`。元の区間コードは変更せず、`P82_usage_intervals_20261024.json`は未作成。区間入力を必要とする準備済み資源集計も実行していない。

代わりに公開計数だけを集計した`materials/20261024_p82_observed_resources`を作った。未知の非負性だけでL−Mは少なくとも＋197,929論理tokenといえるが、両側欠測のL−Hは未確定。これは失敗した区間解析の再試行・代替値ではない。全24行と48側別区分を保存した。

## 原稿・公開の注意

P84が閉じた後、準備済み`build_closed_control_draft.py`では区間を明示的に省略する`--without-resource-intervals`を使い、失敗理由を記録する。実結果のあらまし・結論と観測計数集計は別版で統合する。固定済み原稿や出典台帳を上書きしない。

続いて`build_observed_control_draft.py`を一度実行し、`papers/202610_letter/observed_control_results`へ観測資源と実結果のあらまし・結論を作る。[追加処理の準備](materials/20261024_observed_control_preparation/README.md)は６境界検査・全1232検査を通過した。P84合成値を使った私有予行で本文４頁＋英文１頁を確認しただけで、実結果稿は未生成。実結果は既存の`render_bound_letter_draft.py`で新しい私有出力先へ組版し、全頁を確認する。

教授用の日英題名・456字あらましは保持。著者・所属・順序は未設定、現行公式クラスの確認も未完了。外部送信・投稿は行っていない。新規性や採録見込みを実装数で判断しない。保留12課題は未閲覧のまま維持する。

P84実行中に[外部３ライブラリの９ファイル](materials/20261024_framework_reference_review/README.md)を固定版で静的に確認した。本文へIDを含める経路は他にもあるが、添付の出所を表す用途もあり一括削除しない。外部実装は実行していない。元コードは私有の`.runtime/framework_source_review_20261024`に保持し、公開物にはURL・hash・読んだ行範囲だけを載せた。

[終了済みHの20条件と全24群間比較](materials/20261024_closed_reference_cohorts/README.md)も一度集計した。P82のH書出し両反復の14生成目は、P83の保存統一入力C/Dと完全な要求JSONが一致するが、両方未達。P84はcacheを無効化した別の診断なのでwarm状態の再現としない。P84途中応答は読んでいない。最終稿にはこの接続と未達も記載し、入力整合だけで品質回復を主張しない。既存の準備処理はこの追加分析より前の固定版なので、出力は保存して必要な追記を別版へ行う。

GitHub変更先は`sophiria1225/AI-`と[専用Project](https://github.com/users/sophiria1225/projects/1)のみ。実モデル開始とmain統合は正確なHEADのpush/PR両CI・ジョブ成功後。全115件の作業ボードを部分集合で上書きしない。以前の引き継ぎは[固定版](https://github.com/sophiria1225/AI-/blob/76436a4a66adcdbec9be9e5b98660bae9b9ee1d1/RESUME.md)に保存した。

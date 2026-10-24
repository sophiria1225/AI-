# 研究と実行の引き継ぎ

2026-10-24更新。ユーザーは就寝中も「こちらが何か言うまで実行継続」を指示した。新しい停止指示はない。再度の許可は不要で、新しい停止指示には直ちに従う。最終目標は必要情報・処理と成果品質を保った全仕事費用の削減。25日まで追加確認・採否、29〜30日原稿、31日投稿完了を目指す。新規手法・一般品質維持・採録に足る中核は未確立。

[現在状態](docs/current_status.md)、[次の作業](docs/next_actions.md)、[AGENTS](AGENTS.md)、[当初の引き継ぎ](docs/handoff_20261022_account_switch.md)を読む。古い停止記録は保存し、現在の停止指示と混同しない。

## 保存先と作業木

最新のP86は[全855要求の出力枠点検](materials/20261024_output_budget_scope/README.md)を一度だけ実行済み。13上限到達＝途中切れ引数７＋公開操作なし６、推論専用token計数なし。次の[P87固定計画](docs/experiments/P87_fixed_reasoning_budget.md)は同じ既知CSV課題の２保存文脈×上限なし／推論ブロック2,048×２反復、計８生成。元入力17,696/31,211、元seed69/74を維持し、cacheは全件false。最大228,396論理token、生成段階5,400秒、推論器7,200秒。115依存を束縛した通常対照の局所診断であり、課題実行・品質主張はしない。

実行は別の固定木から `run_fixed_reasoning_budget_pipeline.py --storage-root /Users/tp26013/AI- --expected-commit 固定SHA`。同じheadのpush・PR CI/job成功を確認して開始する。`P87_pipeline_v01`、`P87_preflight_v01`、`P87_fixed_reasoning_budget_v01`を保存し、`.runtime/P87.stop`で停止する。全件終了と所有推論器停止後に `audit_fixed_reasoning_budget.py` を一度実行し、全８枠を資料化する。途中は状態・費用だけを表示し、出力本文・指紋は読まない。P86の解析・旧実験・旧待機を再実行しない。

| 用途 | 場所 |
|---|---|
| モデル・環境・私有記録 | `/Users/tp26013/AI-` |
| 編集木 | `.runtime/worktrees/p84-prep`。現在のブランチはgit statusで確認 |
| P84の終了済み実行木 | `.runtime/worktrees/p84-run`、`1dfa3cafb9e111cffaea2b563513db890e85ebce`固定。切替・清掃・再実行をしない |
| P82の終了済み実行木 | `.runtime/worktrees/p82-run`、`ce81c87ed4a456543859ee98e5aec9e7c5703b77`。終了出力を保持 |
| P82旧資料木 | `.runtime/worktrees/p82-prep`。初回配置失敗の資料・監査を保持 |
| P84旧接続木 | `.runtime/worktrees/p84-controller`、`8af247a90e9b6994c263e387f7c63f13bd45f705`。停止済みの接続処理を再起動しない |

Pythonは保存先の`.runtime/p3_ci_venv/bin/python`、資料は`.runtime/reporting-venv/bin/python`。TeXは`.runtime/letter_tex/v2026.10/portable/TinyTeX/bin/universal-darwin`。AppWorld・vendor・モデルはGit管理外で、cloneだけでは復元しない。

## P84は全件終了

09:25 JST開始、10:38:40 JST終了。セッション51432は正常終了。全18生成、422,475論理token、使用量不明０、監査不一致０。全６入力の３反復が完全・非空で安定し、元ID一対A/Bは公開出力一致０/９対、統一入力C/Dとnative参照対照A/Nは各９/９対。固定診断は成立したが、１保存文脈の次出力だけを測った結果である。[全結果](docs/P84_findings.md)。

全件cache入力０、初期計数６件、生成コード・環境API・課題評価０。推論器稼働4,386.052秒、パイプライン4,386.153秒。推論器PID42849・supervisor42848の不在を確認した。`records/context_pilot/P84_pipeline_v01/status.json`、`server_final.json`、`P84_fallback_output_v01/status.json`と`records/p2_servers/20261024_092534`を保持する。

固定実行木で`audit_fallback_output.py`、`build_fallback_output_report.py --pdf`を各一度だけ手動実行し、全18枠・全15比較と５頁を確認後、同一hashで編集木へ取り込んだ。監査・資料の再生成は不要。進捗確認の１回で途中のstatusにある出力hashを表示した事実を`reports/P84_interim_status_read_20261024.json`へ開示した。応答本文と推論の意味内容は読まず、入力・順序・上限・停止規則・解析規則も変更していない。

元のP84自動接続と終了後待機はP82資料配置失敗で停止したまま保持する。`.runtime/P84_continuation_status.json`、`P84_closure_status.json`は古い停止記録であり、最終実行状態ではない。再起動しない。元の`.runtime/P84_execution_decision.json`を作らず、別の`.runtime/P84_manual_execution_decision_20261024.json`で初回実行を判断した。元の停止印・lockを勝手に削除しない。

## P82の欠測と不採用を保持

全24条件、426生成、既知4,602,713論理token、不明４生成、1,156 API、24評価、監査不一致０。M成功は3/4・2/4、H/Lは両反復3/4。全４採用基準未達。所有推論器停止・両PID不在済み。[全結果](docs/P82_findings.md)。

初回資料の表重なりで自動処理が止まり、元の`.runtime/P82_closure_status.json`と`P82_manuscript_status.json`を保存した。別の`.runtime/P82_manual_closure_status_20261024.json`がレビュー記録。`materials/20261024_p82_results`に初回失敗、`_v02`に表修正、`_final`に８頁の最終資料を保持。全CSVはbyte一致。単独稿`papers/202610_letter/late_time_control`も本文３頁＋英文１頁を確認済み。

狭い区間解析はHの未知２件に正の生成進捗がなく一度の試行で停止した。元の区間コードは変更せず、`P82_usage_intervals_20261024.json`は未作成、区間入力を要求する準備済み資源集計も未実行。代わりに公開計数だけを別集計した`materials/20261024_p82_observed_resources`を作った。未知の非負性だけでL−Mは少なくとも＋197,929論理token、両側欠測のL−Hは未確定。失敗した区間解析の再試行・補完値ではない。

## 実結果稿と組版

`build_closed_control_draft.py --without-resource-intervals`、`build_observed_control_draft.py`、`build_closed_results_final.py`を各一度実行した。中間稿を残し、最終派生先`papers/202610_letter/closed_results_final`を`render_bound_letter_draft.py`で組版した。本文４頁＋英文１頁・14文献、全５頁を確認済み。私有組版先は`.runtime/P84_final_manuscript_actual_render_20261024`。

既存ミラーと固定組版処理を使う新しい選択処理`build_final_results_mirror_preview.py`でも一度予行した。本文３頁＋英文１頁、全４頁確認済み。私有先`.runtime/P84_final_mirror_preview_20261024`、公開先`materials/20261024_closed_results_mirror_preview`。公式ZIPは再取得していない。中間稿・最終稿・各PDFを上書きして新しい結果へ置き換えない。

日英題名・教授用456字あらましを保持。実結果稿の日本語要旨84文字、英文42語。著者・所属・順序は未設定、現行公式クラスとの同一性も未確認。外部送信・投稿は行っていない。

## 次の独立作業

終了済みP80/P81/P82の全48条件・855生成の点検は一度完了した。公開先は`materials/20261024_truncated_code_prefix_scope`、私有初回出力は`.runtime/P85_first_diagnosis_20261024`、準備コードは`.runtime/p85_prefix_preparation`。７不正引数は同じ１コードで、1,883文字22文の構文上の前半を確認。全体1,912文字は構文エラー。後続52枠（未観測６）の全22文AST一致は１件だった。先頭loginはPOSTであり、GET限定の通常規則ではそのまま受理できない。DBへの永続書込みは動的に検証していない。

ソース照合時、展開されたspotify/apis.pyがwheel RECORDに直接なく初回lookupがStopIterationとなった。api_lib.pyはRECORDに一致し、両ファイルhashと読取範囲を`reports/truncated_prefix_local_source_review_20261024.json`へ記録した。元の解析や失敗記録を再実行・上書きしない。新しい境界検査10件を含む全1247検査が通過した。

次は固定backendにおける推論・公開コードの出力上限と既存制御を公開ソース・計数から確認する。内部推論の意味内容は読まない。通常の予算設定を新方式とせず、具体的な規則・対照・有限予算を固定する前に新しいモデル実験へ進めない。

[先行実行・処理列再利用](materials/20261024_execution_reuse_priors/README.md)には既存のAppWorld研究がある。[H群の照合](materials/20261024_closed_reference_cohorts/README.md)では、参照統一後も書出し両反復が未達。失敗した方式の再試行や通常手法の改名に進まない。

GitHub変更先は`sophiria1225/AI-`と[専用Project](https://github.com/users/sophiria1225/projects/1)のみ。実モデル開始とmain統合は正確なHEADのpush/PR両CI・ジョブ成功後。全116件の作業ボードを部分集合で上書きしない。以前の実行中の引き継ぎは[固定版](https://github.com/sophiria1225/AI-/blob/ed4a6a5d0756b9e419e064947d79c166e82cd74a/RESUME.md)に保存した。

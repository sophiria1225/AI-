# AIハーネス研究

**必要な情報・処理と最終品質を保ち、制御・失敗・再取得を含む仕事全体の費用を減らす。** AIオーケストレーションのハーネス制御を研究する。現在は単一作業役の局所検証で、複数担当の通信削減を測った段階ではない。[研究目的](docs/research_objective_20261022.md)／[10月22日朝の説明資料](materials/20261022_morning/AI_harness_progress_20261022.pdf)。

2026年10月23日更新。**P66で既知写真課題の局所的な費用減少を観測したが、新提案手法の中核と一般的な品質維持は未確立。** 10月23日に主要主張・結果・あらましを絞り、25日まで不足確認、29〜30日に原稿整備、31日までのレター投稿完了を目指す。[金曜の判断表](docs/letter_friday_decisions_20261022.md)。

## 現在の実行と原稿

[P68の固定２条件](docs/P68_findings.md)は両方API上限で未達、各219,126 tokenで削減なし。書出し・退会に進まず、制御からの完了通知０回。全16生成・438,252 token・160 API・２評価、使用量不明０、1,348監査不一致０、推論器正常停止。各80生成・450,000 token・1,800秒・80 APIの条件を変更していない。[P68資料](materials/20261023_p68/README.md)。

[現在の４ページPDF](papers/202610_letter/candidate_cost_completion.pdf)／[原稿案内](papers/202610_letter/README.md)／[主張・根拠・限界](docs/letter_claim_scope_20261023.md)。P55の全12表示条件、P56の４診断、P66/P68の別条件の終了制御を区別して記載。和文111字・英文45語、汎用クラスで２段組４ページ、全頁目視確認済み。公式様式・著者情報・採録に足る中心貢献は未確定。

## 現在の研究判断を支える結果

| 検証 | 全結果に基づく判断 |
|---|---|
| [P55・表示省略](docs/P55_findings.md) | 既知４課題×３表示を全て評価。成功1/4・2/4・1/4。詳細省略は既知分だけで全表示より43,083 token多く、さらに不明１生成があり、費用の採用条件に未達 |
| [P56・終了手続き](docs/P56_findings.md) | 写真Fは同じ作業状態から完了通知だけで未達→成功。Bは通知後も未達。実作業と終了通知への作用を分ける局所診断 |
| [P61・通常取得](docs/P61_findings.md) | 通常ツールと持続Pythonが追加連絡先検索０で成功。専用所属キャッシュをこの課題の主方式へ拡張しない |
| [P62](docs/P62_findings.md)・[P63](docs/P63_findings.md) | 旧写真の公開時計不足と、説明取得前の公開名も拒否する接続制約を明確化。元の成否を保持し、主表の適用範囲を限定 |
| [P64](docs/P64_findings.md)・[P65](docs/P65_findings.md) | 通常２接続×既知２課題は全成功。公開名条件の合計費用削減なし。新写真２条件は時計を含む宣言済みの公開検査を支持 |
| [P66・通常終了制御](docs/P66_findings.md) | 既知写真２条件とも成功・最終13保存ファイル一致。全体token130,439→91,116、151,664→112,233で30.1％／26.0％減。呼出しIDによる要求・応答全文の不一致を保持 |
| [P67・CSV公開証拠](docs/P67_findings.md) | 既知１課題の旧３記録で欠落・支持・不明を区別。正しい書出し後の退会まで確認。後続41,702 tokenは実測節約額ではない |
| [P68・CSV終了制御](docs/P68_findings.md) | 新しい通常対照も制御も未達・削減なし。必要な作業に到達しない実行を、終了判定だけでは改善できなかった |

主費用はcached inputを含む全入力＋全出力。API・時間・資源を別記する。失敗・不明使用量・未実行を補完せず、未達で早く止まることを効率のよい成功としない。保留12シナリオは方式・比較・予算・評価の固定まで未閲覧で保持する。

## 資料と進捗への入口

| 読みたいもの | 場所 |
|---|---|
| 最新の状況と次の判断 | [現在地](docs/current_status.md)／[次の作業](docs/next_actions.md)／[採録・新規性の現状評価](docs/letter_assessment_20261023.md) |
| 主な説明資料 | [P55・表示比較](materials/20261023_p55/README.md)／[P56・終了診断](materials/20261023_p56/README.md)／[P64・通常接続](materials/20261023_p64/README.md)／[P66・終了制御](materials/20261023_p66/README.md)／[原稿資料](materials/20261023_letter_cost_completion/README.md) |
| 原典との対応 | [終了制御](docs/termination_control_overlap_20261023.md)／[停止・検証費用の補足](docs/ordinary_completion_literature_20261023.md)／[表示と証拠](docs/evidence_delivery_overlap_20261023.md) |
| 実装・固定条件・集計 | [scripts](scripts/)／[configs](configs/)／[reports](reports/) |
| 進捗管理 | [専用Project](https://github.com/users/sophiria1225/projects/1)／[作業ボード](docs/task_board.md)／[中心判断 #70](https://github.com/sophiria1225/AI-/issues/70)／[主要比較 #71](https://github.com/sophiria1225/AI-/issues/71)／[原稿 #72](https://github.com/sophiria1225/AI-/issues/72) |
| 環境・再開 | [モデル選定](docs/model_selection.md)／[環境手順](docs/repository_setup.md)／[引継ぎ](docs/handoff_20261022_account_switch.md)／[再開状態](RESUME.md) |
| 過去の全経緯・資料 | [整理前のREADME](README_before_P68_20261023.md)／[意思決定記録](docs/decision_log.md) |

過去の実験・失敗・不採用案を保存する。旧READMEの「次の作業」は当時の記録であり、現在の実行指示にはしない。大規模文書のP15は月末投稿への集中のため保留中。研究全体では2027年12月までに情報保持・共有・実行制御を含む構成原理を対象とし、今月のレターは実測で支えられる問いへ絞る。

## 実装と記録

GitHubの変更先は **sophiria1225/AI-とその専用Projectだけ**。[作業ルール](AGENTS.md)に従い、固定条件・失敗・採否を残し、CIと記録確認を経て反映する。モデル重み、元データ、模擬資格情報、完全な履歴、独立評価の追加情報はGitへ登録しない。原記録は実験機の`records/`、独立評価は`private_eval/`へ分離する。

実験機はM3 Ultra・メモリ256GiB。同時にモデル重みを複製しない。共通検査にはPython 3.12と`requirements-ci.lock.txt`を用いる。

```bash
# 作業ボードの生成（外部への書き込みなし）
python3 scripts/sync_tracking.py
# このリポジトリのIssueと専用Projectへ同期
python3 scripts/sync_tracking.py --publish
# 共通の検査
python3 -m unittest discover -s tests -v
```

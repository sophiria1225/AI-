# AIハーネス研究

必要な情報・処理と最終成果の品質を保ち、不要な取得・共有・モデル呼出し・実行・検証を減らす。制御・失敗・再取得を含む仕事全体の費用で評価する。

2026-10-24更新。**新提案の中核、一般的な品質維持、採録に足る新規性は未確立。** 25日までに不足確認と採否を絞り、29〜30日に原稿を整え、31日までのレター投稿完了を目指す。

## 現在の実行

| 対象 | 状態 | 次の判断 |
|---|---|---|
| P82：残時間を常時表示M／非表示H／後半表示L | 共通の表示前参照統一で、既知４課題×２反復、全24条件を固定順に実行中 | 全件終了・所有推論器停止後に監査し、全４採否比較を判断する |
| P82終了後の資料・原稿 | 一度だけ動く処理を待機中。監査→全件資料→原稿数表・PDFの順 | PDFの目視と解釈は生成後。監査失敗や停止時は進めない |
| P84：文章化ID差の次出力への局所効果 | 全６保存入力×３反復を準備済み、未開始 | P82終了後に必要性を判断。生成コードは実行しない |

[現在の結果と限界](docs/current_status.md)／[次の作業と採否](docs/next_actions.md)／[同じ環境での引き継ぎ](RESUME.md)／[専用Project](https://github.com/users/sophiria1225/projects/1)。停止はユーザーの最新指示に従う。終了済みの実験を古い記録から再開しない。

## 閉じた結果から分かっていること

- P80/P81の既知４課題×３反復では、M/Hとも各反復3/4成功。採用基準は全反復未達。書出しは全６条件で未達だった。[全結果](docs/P81_findings.md)。
- Hの論理tokenは条件付きで合計約0.79〜1.02％少ないが、cacheを除く入力は既知分だけで7.09％以上、出力は39.30％以上多く、作業時間は実測32.26％長い。不明２生成を保持し、論理tokenをGPU計算量や時間と同一視しない。[全件集計と図](materials/20261024_p81_resource_accounting/README.md)。
- 文章化された通信参照の露出は全429保存要求中20要求、Hの書出し３反復だけだった。露出のないMの書出しも未達であり、失敗全体の原因とはいえない。[先行研究と露出範囲](docs/identifier_prior_and_exposure_20261024.md)。
- P83の再構成では、文章化前の参照統一で該当２入力のtoken列が一致した。次出力・課題成功・全費用への効果は別途未検証。[P83](docs/P83_findings.md)／[モデル不要の最小再現例](materials/20261024_protocol_minimal_reproducer/README.md)。

## 原稿と資料

| 成果物 | 内容と状態 |
|---|---|
| [P80/P81の検討稿](papers/202610_letter/time_visibility_intervals/README.md) | 全24条件・429生成と条件付き費用区間。本文・文献４頁＋英文１頁を確認済み。新しい資源別集計と追加先行研究は最終統合時に反映する |
| [P82原稿の準備](papers/202610_letter/late_time_control/README.md) | 全24条件・全４採否比較・表示開始位置を取り込む処理。実結果の表とPDFは終了後に生成する |
| [教授用の題名・あらまし](materials/20261023_professor_brief/README.md) | 合意した日英題名と456字あらましを保存。著者・所属・順序は未確定 |
| [P81の７枚資料](materials/20261024_p81_results/README.md) | 成否・全費用・経路の照合を全件掲載 |
| [費用指標の１頁図](materials/20261024_p81_resource_accounting/README.md) | 論理token、cacheを除く入力、出力、時間の方向差 |

投稿先は電子情報通信学会論文誌Dのレター（研究速報）を想定する。現行稿は公式クラス未使用・著者未設定で、投稿可能な最終版ではない。教授への送信・実投稿は行っていない。

## 実装と記録

[表示前の参照統一](scripts/protocol_stable_history.py)、[後半の時間表示](scripts/late_time_observation.py)、[P82の固定実行系](scripts/run_late_clock_pipeline.py)、[P84の固定計画](docs/experiments/P84_fallback_output.md)、[作業ボード](docs/task_board.md)。半分閾値、参照正規化、記録整備をそれ自体で新規手法とはしない。

[研究目的](docs/research_objective_20261022.md)／[金曜時点の判断表](docs/letter_friday_decisions_20261022.md)／[アカウント引き継ぎ](docs/handoff_20261022_account_switch.md)。過去の詳細な経過は[更新前READMEの固定版](https://github.com/sophiria1225/AI-/blob/6e38556bcff00b2cfb509da6a645e736f5fcce23/README.md)に保存されている。

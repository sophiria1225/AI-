# 時間通知比較の実装・記録・資料の対応

対象は[P80の初回](experiments/P80_budget_visibility.md)と[P81の追加２反復](experiments/P81_budget_visibility_repetition.md)。公開集計から図表を再生成すること、ローカルの完全記録を再監査すること、新しいモデル実験を行うことを区別する。以下の資料生成は、P81終了後の監査JSONがそろってから実行できる。

## 実行した条件の所在

| 対象 | 固定版・設定 | 記録からの確認 |
|---|---|---|
| P80全８条件 | `e23b74727f7c2ff0c881a487940a4b6dbf764fd1`、`configs/P80_budget_visibility_v01.json` | `reports/P80_comparison.json`、`reports/P80_server_session.json` |
| P81追加16条件 | `39af0d0c7a4ca8a0937676a84f714eb36cf7bdf3`、`configs/P81_budget_visibility_repetition_v01.json` | `reports/P81_repetitions.json`、`reports/P81_server_session.json` |
| 同一条件の全24対 | 固定版の `compare_budget_visibility_repetitions.py` | `reports/P81_trajectory_stability.json` |
| 欠測と照合範囲の補足 | `summarize_budget_visibility_prefixes.py` | `reports/P81_prefix_coverage.json` |
| 文章化された通信参照 | `inspect_budget_fallback_references.py` | `reports/P81_fallback_reference_diagnostic.json` |

元のモデル・課題設定は `configs/P29_stateful_code_v01.json`、推論器の出所はそこから参照する選定・取得記録に結ぶ。各計画と開始記録はsource hashと固定HEADの両CIを保持する。環境seed42、モデルseed57＋呼出し番号、初回coldと後続cache、全推論保持、実期限とAPI上限を合わせる。これだけで同一出力になるとは保証しない。

## 公開結果から資料へ

Python 3.12、matplotlib、日本語フォント、PlaywrightとChromiumを用いる。新しい出力先を指定して、全24行・全24対を含む資料を作れる。

```sh
python3.12 scripts/build_budget_visibility_repetition_report_v02.py --output /tmp/P81-report-rebuild --pdf
```

この処理は監査済みの公開JSONを読み、モデル生成・環境API・再評価を行わない。図表のデータは同じでも、フォント・OS・描画器によるPDFのbyte一致は保証しない。資料の全頁確認は生成とは別に実施する。

原稿は `papers/202610_letter/time_visibility_repetitions/draft.tex`、自動表は同ディレクトリの `results.tex` と `stability.tex` に対応する。生成用 `build_time_visibility_repetition_draft.py` は既存の結果表とmanifestを上書きしない。再構築時には別の使い捨てcheckoutで派生ファイルだけを取り除き、元の保存物を残したうえで生成する。描画には `render_time_visibility_repetition_draft.py` と固定したTeX環境を使う。著者未設定・公式クラス未確認の検討稿であることは別途保持する。

## ローカル監査と新規実行

完全な要求・応答、模擬資格情報を含む履歴、保存DBと個別評価内容は公開Gitに含めていない。従ってcloneだけで過去の入出力列の全hashを再計算したり、過去のGPUやcache状態を復元したりはできない。

ローカル記録がある場合の全件監査は、実行時の固定版から `audit_budget_visibility_repetition.py` を使う。最初の全件出力は保持し、再確認は別の出力場所を持つコピーで行う。読取診断は使用量の不明を補修せず、保存された要求・応答と各生成の計数の対応を検証する。

新規実行にはAppWorldの同じ版とデータ、同じモデル・量子化・ランタイム・コンテナ接続が必要であり、別の試行IDと有限計画を固定する。公開初期情報の取得は `appworld_typed_bridge.py` の `load_ground_truth=False` を用いる接続に対応する。旧ディレクトリの削除や旧結果の上書きを再現手順とはしない。新しく得た成否・費用・欠測は別の実測値として報告する。

[研究目的](research_objective_20261022.md)／[反復の全件資料作成器](../scripts/build_budget_visibility_repetition_report_v02.py)／[検討稿](../papers/202610_letter/time_visibility_repetitions/README.md)。

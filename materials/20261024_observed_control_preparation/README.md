# 観測済み資源と終了判定を統合する原稿処理

2026-10-24、準備。P82は全件終了、P84は固定した初回実行を継続中。実結果の統合稿はまだ生成していない。

[生成処理](../../scripts/build_observed_control_draft.py)は、既存の全24条件・全18予定枠の統合表を保持し、P82の観測済み資源、失敗した区間解析の理由、実結果に合うあらましと結論を別版へ加える。狭い条件付き区間を再試行せず、欠測の非負性だけによる片側境界と、両側欠測で未確定の差を分ける。成功同士・失敗同士・成否不一致も同じ全件集計へ照合する。

P84の判定不能、一致、差を別の文として扱う。判定不能を「影響なし」へ変えない。「完全」は出力上限による終了でないという定義であり、構文妥当性、実行可能性、課題成功ではないことも本文へ加える。生成後の実行や継続後の品質は評価していない。

P84の終了監査・資料確認後に、編集木で次の順に実数を生成する。既存出力を上書きしない。現在の実行木・固定コードは変更しない。

```sh
/Users/tp26013/AI-/.runtime/p3_ci_venv/bin/python scripts/build_closed_control_draft.py --without-resource-intervals
/Users/tp26013/AI-/.runtime/p3_ci_venv/bin/python scripts/build_observed_control_draft.py
```

出力先は `papers/202610_letter/observed_control_results`。その後、既存の `render_bound_letter_draft.py` にこの `--folder` と新しい私有 `--output-dir` を指定して組版し、全頁を確認する。固定済みの原稿・出典台帳や教授用456字あらましは上書きしない。著者・所属・順序は未設定、現行公式クラスとの同一性は未確認のため、投稿可能な最終版ではない。

[６境界検査](../../tests/test_observed_control_draft.py)では、両側欠測を確定差にしないこと、全件資源の不一致や採否の改変を拒否すること、判定不能と無差を区別すること、日英あらましの上限、既存出力の保持を確認した。全文の1232検査を通過した。

私有の組版予行では、終了済みP82の公開値と**P84の合成値**を使い、本文４頁＋英文１頁、文献14件、あらまし88字・英文42語、はみ出し・未解決参照０、全５頁目視を確認した。これはP84の結果でも実結果稿でもない。PDFは公開せず、[予行の検証記録](../../reports/observed_control_layout_preparation_20261024.json)だけを保存する。実結果のPDFは終了後に改めて確認する。

[P82の全結果](../../docs/P82_findings.md)／[観測計数だけの集計](../20261024_p82_observed_resources/README.md)／[当初の統合稿準備](../../papers/202610_letter/closed_control_integration/README.md)。追加生成・入力計数・環境実行・課題評価は０。

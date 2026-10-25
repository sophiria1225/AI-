# P124: automatic projection の保存 prefix 再生結果

2026-10-26。既知の閉鎖 prefix の 10 プログラムを 2 条件で再生し、20/20 が比較に一致した。両条件に普通 complete-response cache を与えた上で、保存 backend 応答消費は **68 → 57（純減 11、16.176%）**。projection の 22 partial hit のうち 11 件は、通常側の完全値 cache hit と置き換わるため、22 件を純減とは数えない。

| 資料 | 内容 |
|---|---|
| [所見](../../docs/P124_findings.md) | 全会計、境界一致、準備失敗、限界、次の検証 |
| [公開 JSON](../../reports/P124_projection_replay.json) | 全 20 行、条件別集計、8 出典 hash、終了状態、明示的な未実証項目 |
| [実行前の固定仕様](../../docs/experiments/P124_projection_replay.md) | 2 条件・最大 20 プログラム・600 秒の元仕様。歴史的な「未実行」表記は保存 |
| [集計器](../../scripts/build_projection_replay_report.py) | 閉鎖記録だけを読む再集計。コード再生やモデル/API 実行はしない |
| [合成 reporting 検査](../../tests/test_projection_replay_reporting.py) | hash、会計、欠落、終了状態、非公開値の混入など 5 検査 |

実環境 API・モデル・tokenizer・評価器は各 0。2 session の終了と container 除去を確認。全仕事の精度・総 token 削減、実環境の反実仮想、速度向上、新規性は未実証である。最初の prepare-only 失敗 1 件を残し、実再生は修正後の固定 head で 1 回のみ。[独立監査](../../docs/P124_independent_audit.md)で200制御返答とcacheを再構成し、全件一致を確認した。

元の program、返却値、課題本文、プロンプト、resource ID、namespace 名は公開していない。報告生成は、既存出力を上書きしない次の入口を使う。

```sh
python scripts/build_projection_replay_report.py \
  --private-root /PRIVATE/P124_projection_replay_v01 \
  --start /PRIVATE/P124_replay_once_start_20261026.json \
  --end /PRIVATE/P124_replay_once_end_20261026.json \
  --manifest /PRIVATE/P124_replay_input_manifest_v01.json \
  --prepare-attempt /PRIVATE/P124_prepare_attempt_01_20261026.json \
  --output /PRIVATE/new_P124_projection_replay_report.json
```

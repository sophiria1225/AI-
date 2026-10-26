# P126: 全 48 枠の固定前線再生

全 48 枠の事前比較条件が一致した。これは正常終了 48 件を意味しない。program 1–11 の 44 境界は 40 `ok`＋4 既知 `execution_error`、方式間の対応境界は 22 組で一致した。残る 4 枠は事前指定の保存前線で停止し、末尾の正常 final-root 同値や課題完了を主張しない。automatic の 2 前線は sticky stop により `harness_error` として保持される。

各元トレースの saved backend responses は通常 80→automatic 67、部分値再利用は 13 件だった。通常 complete cache hits は両側 0。logical requests は拒否・前線を含め各 82 件で、往復制御 bytes は各 103,385→104,832（1,447 増）だった。これらを全仕事 token や精度の改善へ換算しない。追加 API・モデル・tokenizer・評価器呼び出しはすべて 0。

- [元 summary の同一 bytes 公開版](../../reports/P126_region_projection_replay.json)
- [集計と比較](summary.json)
- [4 条件の件数・制御 bytes・program 時間](conditions.csv)
- [全 48 program 枠と original/actual status](programs.csv)
- [作者による保存物の整合確認](author_verification.json)
- [出典・生成物 hash](build_manifest.json)
- [結果と限界](../../docs/experiments/P126_findings.md)

全体再生時間 2.827542 秒は setup・program・cleanup を含み、条件別 program 時間と重複加算しない。4 コンテナすべての閉鎖・削除を確認した。元課題の token・評価成功は本診断では測っておらず、JSON の null を 0 や成功と解釈しない。

既存 join、明示 field 能力、ordinary cache は共通の通常部品である。保存 source は変更しておらず、新しいモデルが明示 field 能力を選択する比較ではない。同じ既知 CSV 課題の 2 閉鎖トレースを独立課題数に数えない。作者確認は独立監査ではなく、reply bytes は保存 metadata 突合、partial/full 値の一致は凍結 runner の記録を根拠とする。課題値・ID・code・prompt・reasoning・私有 path は転載していない。

[閉鎖独立監査](../../reports/P126_closed_independent_audit_20261026.json) は 4,283 checks、[保存 control の別再構成](../../reports/P126_closed_control_reconstruction_20261026.json) は 838 checks に合格した。後者は 26 partial 値・request/reply 双方の bytes・関連会計を保存 control から再照合するが、producer と同じ loader/Host/Provider を共有する。別アルゴリズムによる意味保存の証明ではない。両確認とも追加の実験・生成 code 実行はなく、既存の作者確認の記録を置き換えない。

# P126: 保存前線までの region projection 再生結果

P125 の閉鎖済み CSV 2 トレースを、元コードを変更せず各 2 方式で再生した。事前固定した全 48 枠の比較条件が一致し、automatic 側で各トレース 13 件、計 26 件の部分値再利用が観測された。これは有限の保存前線に対する実行診断であり、全仕事の token 削減、課題成功、精度維持、新規性は未確立である。[元 summary の同一 bytes 公開版](../../reports/P126_region_projection_replay.json)、[全枠と集計](../../materials/20261026_p126_results/README.md)。

## 結果

| 指標（各元トレース） | explicit_joined_fields | automatic_region_joined_fields |
|---|---:|---:|
| 比較した program | 12 | 12 |
| logical requests（拒否・保存前線を含む） | 82 | 82 |
| saved backend responses | 80 | 67 |
| ordinary complete cache hits | 0 | 0 |
| observed partial hits | 0 | 13 |
| interpreter–host 往復制御 bytes | 103,385 | 104,832 |
| 固定された保存前線での停止 | 1 | 1 |

両元トレースで saved backend responses は 80→67（13 件、16.25% 減）となった。一方、制御 bytes は各 1,447 増えた。これらは保存返答の利用回数と interpreter–host 通信量であり、環境 API の新規実行やモデル入力 token ではない。実際の新規 API・モデル・tokenizer・評価器呼び出しはすべて 0。再生全体は 2.827542 秒、所有した 4 コンテナすべての削除を確認した。条件別 program 時間は [conditions.csv](../../materials/20261026_p126_results/conditions.csv) に残し、全体時間と重複加算しない。

program 1–11 の計 44 境界には、`ok` 40 件と既知の `execution_error` 4 件が含まれる。「通常境界」は元の実行経路の境界を意味し、44 件すべてが正常終了したという意味ではない。元の status/stdout/error が一致し、方式間の比較可能な plain namespace と root fingerprints は 22 組で一致した。未対応オブジェクトの内部状態まで同値とは主張しない。

program 12 の計 4 枠は、元の最後の予算拒否要求を、trace・program 番号・logical index・action hash で事前指定して停止した。通常側 2 件は `execution_error`、automatic 側 2 件は部分値利用後の固定前線により `harness_error` となった。後者の sticky stop も隠さず `projection_stop_due_to_fixture_frontier` に記録している。全 48 件の `matched` は各枠に定めた比較条件の一致を表し、全 48 件の正常終了を表さない。

前線では provider lookup、ordinary cache、予約、保存 backend 返答の利用より前に停止し、未知の suffix を実行しなかった。末尾 4 枠に正常な final-root snapshot はなく、その同値や課題完了を主張しない。assembled transformed artifact は review 用であり、実際の segment 選択・完了状態・hash を別に記録した。

## 根拠と確認範囲

入力 manifest は 70 実装依存ファイル、元保存物の hash、公開 schema、146 元 source の AST-only coverage、別途実施された 83 synthetic contract tests の証拠を束縛している。元の 146 observations はすべて空 list である。再生後も元 source・実装 bytes は不変だった。

作者による読取確認では、元保存物 180 ファイル、実装依存 70 ファイル、再生保存物 428 ファイルの hash と、各 program の元 source・observable/segment hash・保存 tape の順序/件数・模擬予算・22 組の境界・4 前線・4 コンテナの閉鎖を照合した。[作者確認](../../materials/20261026_p126_results/author_verification.json) は独立監査とは別であり、保存 program を再実行していない。制御 reply bytes は保存 evidence との整合確認である。部分値と対応する full reply の一致は、凍結 runner の各 logical request に対する検査を根拠とし、作者確認が新しい独立実行で再証明したとは主張しない。

追加の [閉鎖独立監査](../../reports/P126_closed_independent_audit_20261026.json) は 4,283 checks（178 ledger・2,082 binding 照合を含む）に合格した。また [保存 control の別再構成](../../reports/P126_closed_control_reconstruction_20261026.json) は 838 checks に合格し、48 program の 26 partial 値、request/reply 双方の bytes、budget・field・projection・report の一致を確認した。この追加処理は保存 control を同じ固定 Host/Provider で再構成したもので、生成 code は AST 解析のみ、API・モデル・評価器・Docker・保存生成 code 実行は 0 である。loader/Host/Provider は producer と共有しており、別アルゴリズムによる意味保存の証明ではない。作者確認、閉鎖監査、共有実装による control 再構成を区別して記録する。

対応する将来 full reply は、先行観測から得た部分値の照合にだけ用いた。省略した full reply を provider・full cache・API receipt に注入していない。既知の型付き例外と schema feedback を元の文字列のまま保持し、二重装飾や成功への変換はしていない。

## 解釈の限界

既存 joined authority、明示 `read_fields`、ordinary complete cache、公開 schema feedback は両方式の共通部品であり、それら自体の新規性を主張しない。元保存コードは `call_api` のままで、明示 field 能力をモデルが選ぶ新しい trajectory は生成していない。したがって、この再生は ordinary explicit join をモデルが使う場合との全仕事比較を代替しない。

元トレースは同じ既知 CSV 課題の閉鎖済み 2 条件であり、独立した 2 課題や新しい成功反復ではない。13 件の再利用は、この固定 prefix の機会を確認した値である。API 予算の通知、receipt、モデルの後続行動、課題成功、全仕事 token に与える効果は、この診断からは確定しない。前線以後の返答・仕事の進行・品質も未評価のままである。

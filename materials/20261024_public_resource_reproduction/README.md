# 公開ファイルだけで資源別集計を再計算

公開Gitへ登録済みの67ファイルだけを別フォルダーへコピーし、Python 3.12を `-I -S` で起動した。vendor、Git管理ディレクトリー、私有records、モデル重み、追加Pythonパッケージをコピーせず、元の資源別集計を再計算できた。これはimport経路の隔離であり、OSのファイルアクセス制限をかけた実験ではない。

全24条件、32区分、429保存生成、不明使用量２件を保持した。結果JSONは再計算そのものの経過秒以外の全項目が一致し、全24行CSVと全32区分CSVは元ファイルとbyte単位で一致した。Pythonプロセスは0.051秒で終了した。この時間に出典コピーや外側の照合は含めていない。

通常のcloneでも、Python 3.12と公開ファイルがあれば次で再計算できる。出力先は未作成のものを使う。既存の結果は上書きされない。

```bash
python3.12 -I -S scripts/summarize_closed_resources.py --output ./P81_reproduction_output
```

この確認は公開済みの監査結果と数値の整合性を再計算したものである。元のモデル実験、私有履歴の監査、条件付き区間の生ログからの再構成は実施していない。図表の再描画も今回の確認には含めない。モデル生成、入力計数、環境API、独立評価の追加は０。新しい有効性の実証ではない。

[確認記録と67出典hash](../../reports/P81_public_aggregate_reproduction_20261024.json)、[元の全件資源表](../20261024_p81_resource_accounting/README.md)、[最新原稿](../../papers/202610_letter/resource_prior_review/README.md)。

# Pro V2の1環境の導入確認

対象は[固定済みの計画](../../configs/pro_environment_feasibility_v01.json)のAnsible 1課題。主実験への正式採用とモデル試行はまだ行わない。[候補と代替案を選んだ理由](../main_task_feasibility.md)を維持する。

## 先に実装した準備処理

`scripts/prepare_pro_environment.py`は、次の順に処理する。

1. P3の4試行の計画SHA、実行完了、使用量、監査、独立評価、最終成果物の一致を確認する。正しく評価された不合格は有効な結果として受け入れる。
2. 専用VMで別のコンテナが動いておらず、VM15GiB・ホスト20GiB以上の空きがあることを確認する。
3. AnsibleのV2イメージ1件を固定digestで取得し、プラットフォーム・イメージ設定digest・展開容量を照合する。
4. ネットワークなし、ホストマウントなし、1 CPU・4GiB・PID上限256の新しいコンテナで、Python、基点コミット、変更、参照、stash、到達不能オブジェクト、既知の評価用配置を調べる。
5. 成否・時間・容量・メモリ観測・原ログを一回限りの記録先へ保存する。削除するのは、この呼び出しが作った確認用コンテナだけである。

Git履歴と配置の確認は範囲を限った検査であり、あらゆる漏洩が存在しないことの証明ではない。未知の容量や未取得のメモリ値を0として報告しない。既存のモデルや無関係なイメージ・コンテナを削除しない。

## 起動前の検証

6検査で、進行中の実験、使用量不明、評価の基盤エラー、成果物の後変更、記録パスの逸脱、想定外の基点・評価情報の存在、空き容量不足を拒否することと、正しい不合格を受け入れることを確認した。

実際のP3記録を読み取る確認でも、P3-03が実行中であるため、Docker APIを呼ぶ前の検査関数が拒否した。[検証記録](../../reports/pro_environment_preflight_controls.json)。これは起動制御の検証であり、Pro環境や評価器が動いたという結果ではない。

## 実行方法

P3完了後、研究用コンテナ設定を通して実行する。別のworktreeで実装している場合でも、データと原記録の場所は`--storage-root`で研究ルートへ固定する。

```bash
sh /Users/tp26013/AI-/scripts/with_container_env.sh \
  /Users/tp26013/AI-/.venv/bin/python scripts/prepare_pro_environment.py \
  --storage-root /Users/tp26013/AI- --run-id PRO_ENV_01
```

同じrun-idの記録先が存在したら拒否する。失敗を消して同じ試行をやり直さない。環境エラーを診断して条件を変更する場合は、元の試行と理由を保持し、別の記録として扱う。

## 後続の独立評価

準備・起動確認が通った後、別の新しい環境で空差分と参照修正を評価する。V2の検査ファイルと参照修正は固定版から機械的に評価側へ取得し、本文を研究者・生成側へ表示しない。実行ログと評価入力も生成側へ戻さない。

`scripts/evaluate_pro_environment.py`へ評価側の処理を実装した。固定した6ファイルだけを取得し、Git blobとSHAを照合する。空差分用のコンテナへ参照修正はコピーしない。rewardの欠損・非数値・非二値を0点へ変換せず、評価エラーとして保持する。評価用tarのパスをホストへ展開せず、所定の小さなrewardファイルだけを読み取る。

4つの追加検査で、空差分側への参照修正の不在、許可ファイル・phaseの制限、不明rewardの拒否、tarの不正パス・リンクの拒否を確認した。実際の評価ファイル取得と正負対照はまだ実行していない。

準備が通った同じrun-idで、次を順に実行する。正負対照にはそれぞれ新しいコンテナを用い、原記録を上書きしない。

```bash
sh /Users/tp26013/AI-/scripts/with_container_env.sh \
  /Users/tp26013/AI-/.venv/bin/python scripts/evaluate_pro_environment.py \
  --storage-root /Users/tp26013/AI- --run-id PRO_ENV_01 --phase negative_control
sh /Users/tp26013/AI-/scripts/with_container_env.sh \
  /Users/tp26013/AI-/.venv/bin/python scripts/evaluate_pro_environment.py \
  --storage-root /Users/tp26013/AI- --run-id PRO_ENV_01 --phase reference_control
```

正負対照と使用資源が確認できて初めて、追加モデル試行の条件を決める。旧Verifiedの評価コードやV1の課題用イメージへ置き換えてV2と呼ばない。

## 容量の読み取り確認

準備処理の容量取得だけを確認し、VM内35,025,260,544バイト、ホスト315,944,472,576バイトの空きを観測した。実行中のP3を止めず、イメージ取得や新しいコンテナは実行していない。取得直前にもう一度測る。[記録](../../reports/pro_storage_readonly_probe.json)。

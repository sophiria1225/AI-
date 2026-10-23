# 指標別費用と識別子の先行研究を統合した検討稿

2026-10-24。[PDF](draft.pdf)は本文・文献４頁＋英文末尾１頁。旧[P80/P81区間稿](../time_visibility_intervals/README.md)を保持し、閉じた全24条件・429生成、不明２生成、全24対の表を変更せずに別版へ統合した。P82は実行中、P84は未開始で、その結果はこの稿に含めない。

追加した中心点は、論理tokenの条件付き減少と、cacheを除く入力・出力の既知分の増加、実測時間の増加を区別することである。成功部分の減少を失敗部分が上回る全件の分解も記載した。入力処理と出力生成を足してGPU計算量とせず、実時間の差を因果的な速度差としない。[全件CSV・数値と図](../../../materials/20261024_p81_resource_accounting/README.md)に対応する。

ID改名への感度と正規文脈を扱うMercado・Lomuscioの先行研究を関連研究へ追加し、参照正規化そのものを新規性に含めない。全429要求中20要求の露出を、独立20事例や書出し未達全体の原因とはしない。[原典確認と範囲](../../../docs/identifier_prior_and_exposure_20261024.md)を参照する。

## 形式と検査

- 合意した日英題名を維持。和文あらまし115字、英文47語、日英各５キーワード、文献11件。
- 全５頁目視確認、Overfull・Underfull・頁外文字・未定義引用／参照０。
- 99出典をhashで照合し、旧稿の全24条件・費用区間・経路の数値表は同じファイルを使用する。
- モデルseedを「初回57から生成ごとに１増」と明記した。生成条件の変更ではない。
- 教授用456字あらましは別文書として保持。著者・所属・順序は未設定。
- 公式クラスではなくjsarticleでの検討用組版。投稿可能な最終版・新手法・一般的品質維持・採録の保証とはしない。

[生成台帳](build_manifest.json)／[表示検査](layout.json)／[目視記録](visual_review.json)。組版はTinyTeX v2026.10のuplatex/dvipdfmxを使い、shell escapeを無効化した。途中の組版はローカルへ保存し、数値資料と旧稿を上書きしていない。

## 再生成

リポジトリのルートで、[数表生成器](../../../scripts/build_resource_measurement_draft.py)と[組版器](../../../scripts/render_resource_measurement_draft.py)を使用する。数表は閉じた台帳と全件・欠測を照合し、既存数表が違う場合は上書きしない。組版後の目視記録は自動で完了扱いにしない。

```sh
python3.12 scripts/build_resource_measurement_draft.py
python3.12 scripts/render_resource_measurement_draft.py --tex-bin /path/to/TinyTeX/bin --output-dir /tmp/resource-manuscript
```

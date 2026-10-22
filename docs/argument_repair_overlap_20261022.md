# 引数修復の通常対照と、値を保持する部品の差

2026年10月22日、[SchemaShield-Lite v1](https://arxiv.org/html/2610.23342v1)の§3、4.1–4.3、5.1、5.4–5.6と、公開実装の３ファイルを確認した。論文全体・リポジトリ全体の再現ではなく、正式採録も未確認。[版・ハッシュ・閲覧範囲](../reports/argument_repair_source_review_20261022.json)。

固定コミットは `fbac15632f1ef8133fe83ce8eccb2ee071f0891e`。実装は読んだだけで実行していない。

| 項目 | SchemaShield-Liteの確認した実装 | P49の部品 |
|---|---|---|
| 修復入力 | 課題、選択した公開ツールカード、拒否要求、検査エラー | 未知引数名と型、既存引数名、未使用の公開引数仕様。課題と元の値は渡さない |
| 対象 | 選択済みのAPIへ名前を固定し、引数全体をJSONで再出力 | API・元の値・既存公開引数を固定し、未知名から未使用名への１対１対応を提案 |
| 変更範囲 | 不足引数の補足、名前・型・enum等の修復を促す | 値の補足・変換は不可。削除は原契約の引数集合が空の場合だけ |
| 適用前判定 | API名、必須項目、未知引数、一部の型・enumを検査 | 限定したスカラー制約、衝突、元要求・契約の一致、１回だけの提案受付を検査 |
| 未対応時 | ツール候補の再選択と対象修復を区別。oracle対象は別条件 | 辞退・拒否を返す。通常継続への接続は未実装 |
| 評価範囲 | 論文は主に関数呼出しの正解照合。報告値は未再現 | 保存10拒否の適用範囲のみ。生成・最終タスク品質は未評価 |

修復入力と出力規則は [repair_prompt.py](https://github.com/AniruddhaChattopadhyay/tool-drift/blob/fbac15632f1ef8133fe83ce8eccb2ee071f0891e/defense/repair_prompt.py)、検査範囲は [validator.py](https://github.com/AniruddhaChattopadhyay/tool-drift/blob/fbac15632f1ef8133fe83ce8eccb2ee071f0891e/defense/validator.py)、予測した公開APIとoracle対象の分離は [repair_targeting.py](https://github.com/AniruddhaChattopadhyay/tool-drift/blob/fbac15632f1ef8133fe83ce8eccb2ee071f0891e/defense/repair_targeting.py)で確認した。独自の対照実験を行う場合は検査器と予算を共通化し、既存実装の制約や不整合を提案側だけの優位性にしない。

値の保持と編集範囲の制限は具体的な差だが、最小修正・拘束付き編集そのものの新規性を意味しない。値を隠すと判断に必要な意味まで失う可能性があり、公開enum等から値が推測されない保証もない。型上の完全対応を意味的な正解と呼ばない。

[P49結果](P49_findings.md)では、３件は通常の空契約正規化、２件は完全な名前対応なし、４件は未公開APIで、非自明な名前対応の候補は１件だった。この分布では、入力が短いという理由だけで実行器を広げない。合流後の品質と辞退・再計画を含む総費用を比較できる根拠が必要。

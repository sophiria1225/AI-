# P113: 履歴選別後の実行内容の全件診断

全12条件、204モデル要求、12方式対の219対応位置を保存した. 同じ生成順の対応であり、意味的に同じ処理段階を整列したものではない.

| 課題 | 比較 | 初めて入力が異なる位置 | 初めてPython構文が異なる位置 | 初めてAPI要求列が異なる位置 |
|---|---|---:|---:|---:|
| 34d9492_1 | full / recent | 3 | 3 | 3 |
| 34d9492_1 | full / execution_gated | 5 | 9 | 10 |
| 34d9492_1 | recent / execution_gated | 3 | 3 | 3 |
| 3c13f5a_1 | full / recent | 3 | 3 | 3 |
| 3c13f5a_1 | full / execution_gated | 6 | 6 | 6 |
| 3c13f5a_1 | recent / execution_gated | 3 | 3 | 3 |
| 60d0b5b_1 | full / recent | 3 | 3 | 4 |
| 60d0b5b_1 | full / execution_gated | 4 | 4 | 4 |
| 60d0b5b_1 | recent / execution_gated | 3 | 3 | 7 |
| 6104387_1 | full / recent | 3 | 3 | 3 |
| 6104387_1 | full / execution_gated | 3 | 3 | 3 |
| 6104387_1 | recent / execution_gated | 4 | 4 | 4 |

「観測なし」は全位置の一致を意味しない. 未知応答、ASTのない出力、先に終わった条件は比較不能として全表に残す. API要求列が一致してもPython状態や出力観測の一致は保証されない. 空のAPI列の一致を取得処理の一致として数えない.

全要求の指紋は予算通知、引数、transport ID、seedを保持する. 推論だけを除いた指紋は別に記録し、元の完全要求を変更しない. Python構文の照合では変数名と定数、処理順を保持し、ソース位置だけを除く. 生の推論と要求は公開しない.

新しいモデル生成、API、コード実行、評価、DB閲覧、未見12課題の閲覧は０. 因果効果や状態の意味的同値性、新規手法の証明ではない.

[全204要求](all_calls.csv)／[全219対応位置](all_pair_positions.csv)／[全指標の最初の差と欠測](all_first_differences.csv)／[完全集約](summary.json).

# P104: 手書き遅延読取の入力経路を全件計数

終了済みの同じ６段階を現在の会話形式へ通し、２方式×２表示×６段階後の全24入力を一度計数した. 新しいモデル生成・API・Python実行・評価は０. 同じプログラム、既知課題、説明、表示上限を使った事後の比較用入力であり、過去に送信されたLLM要求や生成された課題解決過程ではない.

元の実APIは即時11対遅延10で、６段階のstdoutは一致する. 下表の負値は、この限定入力において遅延側が短いことを示す. 入力数の合計を実際の全仕事使用量とはしない. 第６段階後は終端の表示確認で、実際の次のモデル呼出しではない.

| 表示 | 段階後 | 即時入力T | 遅延入力T | 遅延−即時T | 入力列一致 |
|---|---:|---:|---:|---:|---|
| harness | 1 | 3719 | 3719 | 0 | True |
| harness | 2 | 3942 | 3922 | -20 | False |
| harness | 3 | 4239 | 4239 | 0 | False |
| harness | 4 | 4462 | 4442 | -20 | False |
| harness | 5 | 4667 | 4627 | -40 | False |
| harness | 6 | 5202 | 5184 | -18 | False |
| content_attribution | 1 | 3576 | 3576 | 0 | True |
| content_attribution | 2 | 3768 | 3768 | 0 | True |
| content_attribution | 3 | 4054 | 4054 | 0 | True |
| content_attribution | 4 | 4246 | 4246 | 0 | True |
| content_attribution | 5 | 4420 | 4420 | 0 | True |
| content_attribution | 6 | 4902 | 4902 | 0 | True |

harnessは通常の実API数・受領参照・登録順span IDを含む. content_attributionはstdoutと成否等を残し、そのメタデータを除いた計測用表示で、品質保持を検証済みの制御方式ではない. 入力列が全て一致する場合、その表示における本文由来のtoken差はない.

[全24入力](all_24_renderings.csv)／[全12組](all_12_boundary_pairs.csv)／[全４描画処理](all_4_renderer_batches.csv)／[固定した比較](../../docs/experiments/P104_read_view_input_footprint.md).

固定の語彙専用rendererを使用し、推論contextとdecodeは０. 実エージェントの生成履歴や各時点の予算通知は再構成せず、共通説明・手書き提出・通常の外側観測を会話へ通した範囲を計数する. 上限・失敗・元記録を変更せず、計数用の時間と標本化RSSを別に保存した. 強い通常方式との実課題比較、生成token、最終品質、再取得や制御費を含む全仕事の改善は未確認. 新規手法の成立を示す結果とはしない. 原稿の逐次改訂は保留を維持する.

# P125 図の再生成

リポジトリ直下で、matplotlib 3.11.2を利用できるPythonから実行する。出力先は未作成のディレクトリを指定する。

```sh
python materials/20261026_p125_figures/draw_p125_results.py \
  --repo-root . --output-dir /tmp/p125-redraw
```

同梱のrendererは初回実データ描画に用いたものと同一bytesで、`source_manifest.json` と `render_evidence.json` にhashがある。元audit・server会計・全8条件の資料を検査してから描画する。PDF/SVGの作成metadataなどにより、再描画画像のbytesが同じになる保証はない。数値の比較には `figure_data.json` を使う。

初回の独立監査はswap値0.0と0の厳密型比較で失敗し、自動描画待機は描画せず終了した。修正版の独立監査通過後に初めて実データ図を生成した。実験の再実行はしていない。[訂正来歴](../../reports/P125_independent_review_correction_20261026.json)を保持する。

# 閾値型要約の再帰置換と差分保持：和文レター校正稿 v02

`manuscript.pdf` が閲覧用PDF、`source_bundle.zip` が編集・再ビルド用のTeX一式です。本文・図表・文献4頁と末尾英文1頁で構成します。**著者・所属等は未設定**です。投稿済み・採択済み・投稿準備完了を表すものではありません。

本稿はP143の閉鎖済み全8条件を収録します。再帰置換TRは3/4成功、旧要約保持・object差分・ホスト結合TDOは2/4成功でした。写真操作のTDOに使用量不明1呼出しがあり、全体の確定費用差・削減率は示しません。差分が届いた共通成功課題の精算でも35,578トークン増え、品質を保つ全仕事費用削減は確認できませんでした。全表と図は失敗条件も含みます。

## ファイル

- `main.tex`、`abstracts_p143.tex`、`results_p143.tex`：和文本文、和英あらまし、全8条件の結果。
- `figures/architecture_p143.*`、`figures/p143_cost.*`：方法図と実測費用図。PDF/SVGはベクトル、PNGは閲覧用、EPSは投稿作業用です。
- `figures/*_source*.py`、`prepare_p143_result_text.py`：図・表の再生成用source。通常のTeX再ビルドにはPythonは不要です。
- `references.tex`、`references.bib`：7件の文献。本文は検証済みの手書き文献表を使います。
- `result_table_data.json`、`result_data_manifest.json`、`figures/figure_data.json`、各図manifest：閉鎖入力と派生資料のhash。
- `EVIDENCE.md`：選定経緯、会計と解釈の範囲、原資料への対応。
- `FORMAT.md`：和文Dレターの組版条件とクラスの制約。
- `preparation_sources_p143.json`：結果を見る前に固定した方法図の出所。`results_unread`等は準備時点の履歴であり、現在の原稿の状態ではありません。
- `bundle_manifest.json`：配布ZIP内の各ファイルのSHA-256。ZIP自体と閲覧用PDFはリポジトリ側のprovenanceで別に束縛します。

## TeXの再ビルド

外部のTeX環境と`ieicej.cls`を用意し、ZIPを任意の新しいフォルダへ展開して次を実行します。Git外でも動作します。

```sh
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
```

`TEX_BIN`には`uplatex`、`dvipdfmx`、`kpsewhich`、`extractbb`が必要です。日本語、`newtxtext`、`newtxmath`等を含むTeX環境を使用します。`build/main.pdf`が生成されます。図の寸法は事前に`extractbb`で抽出し、shell escapeは使用しません。クラスの既定SHA-256は`FORMAT.md`記載値と照合します。

使用クラスは固定ミラーの**ieicej v3.4a**です。公式一覧の現版v3.4bは通常取得がHTTP403で、archive bytesとの同一性を検証できていません。現公式最新版への厳密適合を認証したPDFではありません。クラス本体・TeX環境・ビルドログは配布ZIPに含めません。著者情報と公式最新版の照合は投稿前に必要です。

## 再生成と履歴

費用図・表を再生成する場合は、リポジトリの`materials/20261028_p143_results/`にある公開閉鎖資料と、固定manifest/summary SHAを指定します。既存出力先の上書きは拒否します。これは派生資料の作成であり、原実験・監査・評価器を再実行しません。

```sh
python prepare_p143_result_text.py --input-dir /path/to/materials/20261028_p143_results --manifest-sha256 941e24ef3c8e3e0b080e33724a9768244b75da20ed3f9743d7849a63d91fc120 --summary-sha256 1634c2ce24055ae01a25fe71b482d75ff64e18b1dbc621f4ca19cd87b6db848f --closed-inputs-approved --output-dir /new/text-output
python figures/p143_cost_source.py --input-dir /path/to/materials/20261028_p143_results --manifest-sha256 941e24ef3c8e3e0b080e33724a9768244b75da20ed3f9743d7849a63d91fc120 --summary-sha256 1634c2ce24055ae01a25fe71b482d75ff64e18b1dbc621f4ca19cd87b6db848f --closed-inputs-approved --output-dir /new/figure-output
```

Pythonによる図の生成にはMatplotlibが必要です。生成本文は数値を含むレビュー用素材であり、配布本文の考察を自動で復元・上書きしません。旧v01とP142準備版は別に保存され、このZIPには現P143原稿で使うsource/assetsだけを選んで含めています。旧結果を新結果へ合算せず、未見12課題も使用していません。

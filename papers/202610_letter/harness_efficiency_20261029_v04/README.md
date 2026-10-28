# 通常ハーネス制御の実測評価：和文レター v04

本稿は、通常のハーネス制御で実際に観測した正例を、強い対照と適用範囲とともに示す校正稿です。新しい圧縮・終了原理の提案や未見課題での品質保証ではありません。閉鎖済みP123とP64/P66を別々の実験として扱い、将来の追加実験が成功することを前提にしていません。

- 実験A：単発・別呼出し反復・同時反復の全12条件。各4/4成功。SeparateはSingle比12.07%減（全減少はCSV）、InlineはSeparate比6.53%増。
- 実験B：同じ写真1課題・2interfaceの通常継続と証拠付き終了、全4観測。全て成功し、30.15%／26.00%減。既知文型の手書き規則で、要求・応答のstrict prefix一致は不成立。
- 同時反復は単発要約比6.34%減だが、別呼出し反復比6.53%増。この比較元の「通常」は単発要約であり、無要約方式の測定値ではありません。
- 後続P144/P144R1の全12条件も補足資料へ収録。各方式3/4成功で、状態更新は通常再帰要約比74.54%増。明示的な更新処理の実適用は0回。追記方式の使用量不明1件と、電源断前後の別sessionを保持します。
- P128のseed間不一致とP143の成功喪失・不明使用量はEVIDENCEに残し、本文では追加改善が未確立である限界を簡潔に示します。異なる実験をpoolせず、全研究が成功したという主張には使いません。

配布用PDFは[manuscript.pdf](manuscript.pdf)、編集可能な一式は[source_bundle.zip](source_bundle.zip)です。`main.tex`が本文、`abstracts.tex`が和英あらまし、`tables.tex`が主実験の全対象条件の表です。[補足PDF](supplemental_results.pdf)は追加比較の全12条件を載せた独立1頁です。`bundle_manifest.json`でZIP内の各ファイルを照合できます。主原稿は本文・図表・文献4頁＋英文1頁、文献は正式会議録7件です。全5頁を目視確認し、全フォント埋込み・はみ出し警告0・引用と参照の解決を確認しました。著者・所属は未設定で、投稿は行っていません。

## 再ビルド

```sh
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh supplemental_results.tex supplemental_build
```

Git外でも利用できます。`uplatex`、`dvipdfmx`、`kpsewhich`、`extractbb`と日本語・newtxフォントを含むTeX環境を用います。shell escapeは使わず、図の寸法を先に抽出します。使用クラスは固定ミラーのieicej v3.4aで、公式v3.4bのarchive bytesはHTTP403のため未照合です。クラス本体とTeX環境を配布しません。詳細は`FORMAT.md`を参照してください。

補足PDFは汎用articleクラスを用いる別資料で、学会の補足書式や添付許可を確認したものではありません。主原稿と補足のページ数を合算してレター本文のページ数とはしません。

## 出所と再描画

`evidence_sources.json`は公開済み原資料の固定hashです。`prepare_evidence.py --repo-root /path/to/repo --output /new/results_data.json`は原資料のhashと全12＋4行を検査し、本文用の集約値だけを生成します。実験・モデル・環境API・評価器は起動しません。追加の閉鎖済み結果は `P144R1_results_data.json` と `P144R1_all_conditions.csv` に分離し、全12条件の表は `supplemental_results.pdf` / `supplemental_results.tex` に収録します。本文の主な正例を置換・合算しません。

`figures/render_figures.py --data results_data.json --output-dir /new/figures`はPython/Matplotlibで構成図と、二つの集計範囲を分離した費用図を描きます。PDF/SVG/EPSはベクトル、PNGは閲覧用です。TeXの通常ビルドではPythonは不要です。

既存v01/v02/v03や元の実験資料は変更していません。新しい実験を後から使う場合も、全条件の閉鎖と独立照合後に別の出所を追加する必要があります。未見12課題はこの原稿のために閲覧・使用していません。

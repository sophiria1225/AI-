原稿・図表の電子データ（提出項目2・準備版）

この一式は2026年10月30日時点の原稿v27を収録しています。
原稿は調整中です。最終提出時には、提出項目1の印刷見本PDFと
一致する最終稿に編集用データを更新してください。
このZIPに印刷見本としての原稿PDFは含めていません。

主原稿
  manuscript.docx      Wordで直接編集する原稿。図1と表1・表2を含む。
                      図は埋め込み済み、表と数式は編集可能。

図1
  figures/control_points.png   原稿に挿入した画像。元の解像度を維持。
  figures/control_points.svg   ベクトル形式。
  figures/control_points.pdf   図1単体のベクトルPDF。原稿PDFではない。
  figures/control_points.eps   図1単体のEPS。
  figures/render_control_points.py
                              図の文言・配置を編集する作図コード。
  SVG/PDF/EPSの文字はアウトライン化済み。
  ラベルの編集は作図コードで行い、必要な形式を再生成する。

表1・表2
  results_tables.xlsx          表と集計式を編集できるExcelブック。
  results_data.json            表の元となる実験結果データ。
  create_results_tables.py     元データからExcel表を生成するコード。

参考LaTeXソース
  main.tex                    本文。
  abstracts.tex               和文・英文要旨とキーワード。
  tables.tex                  表1・表2。
  references.tex              本文で読み込む参考文献。
  references.bib              参考文献の書誌データ。
  build.sh                    LaTeXの組版用スクリプト。

Wordを主原稿とし、LaTeXはv27と同じ本文を持つ参考ソースとして収録。
Wordの編集はLaTeXへ自動反映されません。原稿確定後にZIPを再作成する際は、
参考ソースも最終稿と整合させてください。

再生成に使う環境
・Word原稿の編集・印刷見本PDF作成はMicrosoft Wordで行う。
・Excel再生成はPythonとXlsxWriterを使用する。
  python create_results_tables.py --data results_data.json --output-dir build/tables
  出力先は新規ディレクトリとする。
・図の再生成はPython、Matplotlib、CairoSVG、PyMuPDF、Pillow、および
  日本語フォントを使用する。macOS標準の対応フォントがない環境では
  環境変数JAPANESE_FONTに日本語フォントファイルを指定する。
  python figures/render_control_points.py --output-dir build/figure
・LaTeX再生成にはTeX環境とIEICEクラスieicej.clsを別途用意する。
  TEX_BIN=/path/to/tex/bin IEICEJ_DIR=/path/to/ieicej bash build.sh
  既存組版で使用したクラスはv3.4a、SHA-256は
  36b2731a97ecbb86f02b1aff50cf38d10ae57c6f1a6448f5fc9956226412a56a。
  TeX環境、クラスファイル、OSのフォント本体は同梱していない。

収録元
  リポジトリ: https://github.com/sophiria1225/AI-
  収録版: papers/202610_letter/harness_efficiency_20261030_v27
  元ファイルの一致確認: 外側のpackage_manifest.jsonのSHA-256一覧を参照

旧版、原稿の校正PDF、実験ログ、検査記録、他者の参考原稿は収録していない。
梱包時は図表の解像度、収録版の原稿本文・実験結果を変更していない。

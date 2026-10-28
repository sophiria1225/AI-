# 組版条件

第一候補は電子情報通信学会・和文論文誌Dのレター（研究速報）。[公式規程](https://www.ieice.org/jpn/shiori/iss_2.html)の標準は2頁で、初回5頁以上には超過理由書が必要。本稿は本文・図表・文献4頁＋末尾英文1頁で組む。著者・所属は未設定、投稿済みや採択可能性を認証したものではない。

クラス・文字サイズ・行間・段幅は改変しない。使用する`ieicej.cls`は固定ミラーcommit `09affdda87853ac52313ec92ae90e0f14a43a20d`、宣言2023/11/21 v3.4a、SHA-256 `36b2731a97ecbb86f02b1aff50cf38d10ae57c6f1a6448f5fc9956226412a56a`。2026-10-28の公式一覧にはv3.4bがあるが、通常取得はHTTP403でarchive bytesを照合できていない。リポジトリの見出しだけで最新版と認定せず、公式クラスを改変・同梱しない。

`build.sh`はv02から同bytesで継承した。外部`TEX_BIN`/`IEICEJ_DIR`を指定すればGit外でもビルド可能。extractbbで図の寸法を先に取り、uplatex→必要ならupbibtex→uplatex×2→dvipdfmxを実行する。shell escapeは無効。本文は手書きの`references.tex`を読み、正式会議録・論文誌12件を使う。現環境に`sieicej.bst`がないため、別styleへ黙って置換しない。

和文あらましは120字以内、英文は50語以内、keywords各5件。図は幅130mm、最小文字7pt、線幅0.5pt、白黒対応でPDF/SVG/EPSとPNGを保持する。現在の校正PDFは本文・図表・文献4頁＋英文1頁。全5頁の目視、使用16フォントの埋込み、引用・参照解決、はみ出し警告0を`typesetting_validation.json`に記録する。和文あらまし118字、英文41語（英数字を保守的に分割すると46語）である。ZIPのGit外ビルド照合は`reports/harness_letter_v05_author_validation_20261029.json`に記録する。これは作成担当による検証であり、独立査読や採択の認証ではない。

公式最新版の未照合と未設定の著者情報は投稿前の確認事項として残る。既存v01/v02/v03の検証記録を新稿の検証済み証拠に流用しない。

2026-10-29 v04は閉鎖済みの追加比較を本文の短い限界記述と別添補足表へ反映する。投稿条件の再照会や新版クラスの取得はしておらず、上記のクラス来歴と未確認事項を継承する。補足表は汎用articleクラスによる独立1頁で、学会の補足用テンプレートや添付許可を確認したものではない。補足も目視確認し、はみ出しと未解決参照がないことを確認した。

2026-10-29 v05: 12 formal references; 4 main pages plus 1 English page. Experimental tables, data, and manuscript figures are byte-identical to v04. All 5 pages were visually reviewed; overfull and unresolved-reference counts are zero.

The Word companion uses Pandoc 3.13 and python-docx 1.2.0. It is A4 single-column editable content, not an official IEICE Word template. OOXML, text, two editable tables, two images, and one display equation were validated; the first-page macOS Quick Look preview was visually reviewed. Full pagination in Microsoft Word/LibreOffice is not verified. See word_validation.json.

All four Japanese architecture candidates are supplied separately and remain unselected. They do not change the figures or results in the manuscript.

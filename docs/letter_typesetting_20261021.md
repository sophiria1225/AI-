# レターの組版準備

2026年10月21日。対象は暫定的に和文論文誌Dの研究速報。ユーザー訂正後の原稿目標は２段組４ページ。公式の標準２ページとは区別する。
実験の新規性と結果はまだ確定していないため、組版準備の完了を投稿原稿の完成とは扱わない。

公式LaTeXテンプレートは[公式配布一覧](https://www.ieice.org/ftp/tex/ieicej/LaTeX2e/)の
[ieicej3.4b.zip](https://www.ieice.org/ftp/tex/ieicej/LaTeX2e/ieicej3.4b.zip)を使う。
Wordの配布案内は[別ページ](https://www.ieice.org/jpn/shiori/template.html)にあり、両者を混同しない。
Macからの直接取得がHTTP 403となったため、許可された当リポジトリのGitHub Actionsから
同じ公開配布先への取得を一度試す。認証情報は使わず、URL・日時・ハッシュまたは失敗内容を保存する。

取得できたアーカイブはローカルの無視対象ディレクトリで内容と利用条件を確認する。
確認前に配布ファイルをリポジトリへ転載したり、未知の処理を実行したりしない。
古い第三者テンプレートや手作りの２段組を、現行の公式様式と呼ぶ案は採用しない。

TeXが未導入のため、必要なら公式TinyTeXの固定版を研究ディレクトリ内へ置く。
システム設定やシェルの既定PATHは変更せず、ダウンロード容量とハッシュを残す。
公式クラスで組版し、文字・図表・参考文献を入れたPDFのページ数を確認するまでは、
「目標４ページに収まった」とは記録しない。

取得結果：当リポジトリの[手動実行](https://github.com/sophiria1225/AI-/actions/runs/39548895750)も取得に失敗した。
GitHub側はHTTP 202を受け取り、内容がZIPでないため検査で停止した。Mac側の403とは異なる。
ZIP本体は保存されず、失敗manifestをArtifactから回収した。
[公開する取得記録](../reports/ieice_template_fetch_20261021.json)に日時と結果を残す。
再試行を繰り返さず、公式配布物の取得と実組版の確認を未完了として、本文・実験を続ける。

その後、TinyTeX v2026.10のmacOS用配布を公式リリースのSHA-256と照合し、
研究用の無視対象ディレクトリ内へ展開した。必要な日本語処理・フォントを追加し、
`jsarticle`の確認文書で日本語・数式・表を含むPDFを生成、文字抽出と１ページの目視確認まで完了した。
これは描画基盤の確認であり、公式様式の確認や研究原稿の完成ではない。

初回導入で管理器の更新要求、PDF生成でフォント対応表とCMapの不足が生じた。
更新と必要パッケージの導入で解消し、失敗ログも残した。
システム全体の設定やシェルのPATHは変更していない。
導入元・容量・版・ハッシュ・確認範囲は[組版基盤の記録](../reports/letter_tex_toolchain_20261021.json)を参照。
全体版のTeX配布を入れる案は、当面必要な組版に対して保存量が大きいため採らなかった。

17時台には[公式Word配布一覧](https://www.ieice.org/jpn/shiori/template.html)の情報・システムソサイエティ／レターから、[DのWordファイル](https://www.ieice.org/jpn/shiori/jd/iss_lettertemplete.docx)を確認した。LaTeXに限定せず投稿用様式を取得する候補だったが、この経路もMacからの１回の取得がHTTP 403となった。Web読取器ではバイナリ形式非対応で、内容は読めていない。[失敗記録](../reports/ieice_word_template_fetch_20261021.json)を残し、取得成功・公式組版確認とはしない。再試行を繰り返さず、４ページの主張と実験を優先する。

16時台の追加確認では、[公式の研究会案内](https://www.ieice.org/jpn_r/event/kenkyukai/index.html?id=teishutu)が、和文技報と和文論文誌で `ieicej.cls` を共用すると説明し、[3.4aの別配布先](https://www.ieice.org/jpn_r/event/kenkyukai/assets/files/ieicej3.4a.zip)へリンクしていた。この別の公開経路もMacからはHTTP 403だった。取得は１回で打ち切り、失敗をローカルの `.runtime/letter_tex/ieicej34a_official_20261021/error.json` に保存した。3.4aを3.4bと同じ版と扱わず、取得できたことにもしない。認証の回避や非公式なクラスの代用は行っていない。

22時台に[OverleafのIEICE名義テンプレート](https://www.overleaf.com/latex/templates/template-for-ieice-journals-technical-reports/kxtxxvzpzgkg)も確認した。表示は2019年のv3.2で、レターのマクロ例を確認できるが、現行3.4bと同じとは扱えない。「テンプレートを開く」はログイン画面へ移り、クラスのダウンロード・新しい外部プロジェクトの作成はしていない。最新版と公式ページ数の確認を、この古い公開例で完了扱いにしない。

23時台には、論文誌との同時査読を案内する[MIRU2026の公式投稿ページ](https://miru-committee.github.io/miru2026/author/submission/)から公開のLaTeX配布を取得できた。ただし、収録クラスは`miru2026j.cls`で、ヘッダーはIPSJクラスからの改変を明記している。`ieicej.cls`は含まれず、IEICE論文誌の現行様式を得たことにはならない。別の４ページ規定を論文誌へ流用する案は採らず、クラスの実行・転載も行わない。[取得・不採用の記録](../reports/miru_template_scope_20261021.json)。同じIEICE配布先への再試行を繰り返したものではない。

10月22日13時台に同じ現行3.4bの公開URLを再確認したが、再びHTTP 403だった。[取得失敗記録](../reports/ieice_template_fetch_20261022.json)。これは新しい入手経路の検証にはならず、以後このURLへの反復取得は行わない。公式クラスと４ページ組版は未完了のまま、実験と主張の確定を優先する。

10月23日に別の公式ディレクトリ `ftp/tex/tech_rep/LaTeX2e/` とその説明PDFの冒頭を確認したが、一覧は2003年、説明はクラスv1.3だった。現行3.4bの代用にはせず、アーカイブ取得を試みていない。失敗した現行ZIPの同一URLは再取得していない。

## 2026年10月23日：公開ミラーの版を点検

[mar-tusita/ieicej-platex](https://github.com/mar-tusita/ieicej-platex/tree/09affdda87853ac52313ec92ae90e0f14a43a20d) は説明にv3.4bとあるが、固定commitの `ieicej.cls` は `2023/11/21 v3.4a` を宣言していた。４ファイルのGit blob IDとダウンロード内容を照合した。公式2026年1月19日v3.4bとの一致は確認できず、最新版として採用しない。クラスや外部スクリプトの実行、失敗済み公式ZIPの再取得は行っていない。[検査記録](../reports/ieice_mirror_check_20261023.json)。

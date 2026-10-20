# 主課題候補の導入条件

2026年10月20日。公開12候補の調査では、大規模な分担作業の主課題を確定できなかった。次にSWE-bench Pro V2とTheAgentCompanyの公式配布・評価手順を確認する。研究対象は作業の分担・共有・再編であり、ベンチマーク名や難易度ラベルだけで採用を決めない。

[取得した説明文のURL・版・SHA](../reports/main_task_source_versions.json)を保存した。この段階では新しい環境を起動せず、モデル実験も行っていない。

| 候補 | 確認できた条件 | 次の確認と順序 |
|---|---|---|
| SWE-bench Pro V2 | defaultは642課題、11リポジトリ。要求・新しいインターフェースが生成側の入力。正解差分と追加テストは別用途の列 | コード変更・最終差分・独立評価という既存基盤との対応を先に点検する。個別の公開要求から作業依存を確認してから導入対象を選ぶ |
| TheAgentCompany | 模擬企業の複数サービスを使う175課題。環境のNPCと一部評価にもLLMを使う | 状態が変わる業務への候補として保持。複数サービスとNPC履歴の復元、環境側の費用、評価の確定性を先に設計する |

Proの課題説明と版は[固定版データカード](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro/raw/2d52cb3df914a3fcf80c7f66738b3a88ae37fc50/README.md)、業務環境の構成は[公式説明](https://github.com/TheAgentCompany/TheAgentCompany/blob/98b68ef82a47690c316f42fddb05baafaab56851/README.md)に基づく。どちらもこのMacでの課題成功や必要容量を実測した結果ではない。

## Proを先に調べる理由と、まだ未確認の点

固定したコード版は`66f92766bba642462d4bbe5479e83f91f9211862`、データ版は`2d52cb3df914a3fcf80c7f66738b3a88ae37fc50`。公式V2では、生成時のネットワークを制限し、取り出した差分を新しい環境で再評価する。mini-swe-agent向けの接続も公開されている。従来のDocker Hub用列・評価スクリプトはV1用なので、V2へ流用しない。[V2の手順](https://github.com/scaleapi/SWE-bench_Pro-os/blob/66f92766bba642462d4bbe5479e83f91f9211862/v2/README.md)。

公式の実行例はHarborとModalを用い、1課題50分を設定している。ローカルのColima・llama.cpp・総トークン予算へ接続した場合は条件が変わるため、公式スコアの再現とは呼ばない。イメージはlinux/amd64であり、Apple siliconでの実測が必要。課題ファイルの配布容量と、イメージ・ビルド・検査・モデルの容量は別に測る。

HARD-51はモデル群の失敗に基づく部分集合で、作業依存の強さを分類したラベルではない。今回の依存課題の候補抽出では、このフラグや正解差分の規模を順位付けに使わない。公開要求の内容を確認する前に、V2全体が今回の主題へ適していると確定しない。

## TheAgentCompanyを後の候補に残す理由

公式手順は30GB以上の空き容量とDocker・Composeを挙げるが、ローカルLLMと一緒に動かす必要メモリを保証していない。Mac向けにはネットワークや仮想化方式の注意もある。[導入手順](https://github.com/TheAgentCompany/TheAgentCompany/blob/98b68ef82a47690c316f42fddb05baafaab56851/docs/SETUP.md)。

環境初期化は依存サービスのデータをリセットする。NPCとLLM評価器の設定も結果へ影響し、課題によっては実行履歴が部分点に使われる。そのため、会話とコード差分だけを保存する現在のP3から、そのまま同一状態の分岐比較へ移すことはできない。まず、サービス状態、会話、評価器、費用の境界を調べる。[評価手順](https://github.com/TheAgentCompany/TheAgentCompany/blob/98b68ef82a47690c316f42fddb05baafaab56851/docs/EVALUATION.md)。

公式のOpenHands実行例は基盤エラーの課題をスキップする場合がある。採用時には失敗・未完了を台帳へ残し、黙って分母から除外しない。[基準実装の説明](https://github.com/TheAgentCompany/TheAgentCompany/blob/98b68ef82a47690c316f42fddb05baafaab56851/evaluation/README.md)。

今すぐサービス一式を導入する案は、進行中のP3の資源条件へ干渉し、依存機構の比較前に環境・ブラウザー・NPCという変更を増やすため採用しない。環境の不適合やベンチマークの劣位を実証したという意味ではない。

## データプレビューで生じた研究者の正解閲覧

配布状況を確認するためProのデータセットページを開いたところ、HTMLの自動プレビューにNodeBB課題の正解・追加テスト等の列が含まれた。正解を読んでいないことにはせず、表示された課題IDの範囲と閲覧経路を[別データセット用の露出台帳](../configs/benchmark_exposure_registry.json)へ記録した。

今後、NodeBBの課題を未調整の確認評価に使わない。今回表示された解決策に基づいて分担や候補を設計しない。生成側へもこのプレビューを渡さない。以降の取得は、固定版README・メタデータを先に確認し、実データは列を限定してから表示する。Proの正式な確認評価・課題選定はまだ開始していない。

## 次の作業

1. 固定版の配布ファイル照合と公開入力の分離は完了した。
2. 6リポジトリ×2件の抽出規則と候補IDを、問題文を読む前に固定する。
3. 全候補の公開要求を確認し、依存を調べる候補と見送る候補の理由を保存する。
4. 元コードで依存候補を確認し、最初の1環境の容量・基準状態・独立評価の対照を測る計画を作る。

新たなモデル試行、全イメージの一括取得、課題群の正式採用は、この説明文の確認だけでは進めない。各段階の記録を残してから実行する。

## 公開入力の分離を実施

[配布情報](../configs/pro_v2_data_source.json)を固定し、6,511,689バイトのParquetをSHA-256照合付きで取得した。元ファイルはGit対象外の`private_eval/pro_v2/`へ置き、列を限定してから行をPythonのデータへ変換する。生成用本文はproblem_statement・requirements・interfaceの3列で、読取対象の残り6列は課題・版・イメージ等のメタデータである。

642件からNodeBBの38件を除外した604件・10リポジトリを、別の公開調査入力へ出力した。2,461,832バイトで、正解差分・追加テスト・採点対象のテスト名・評価用初期化コマンドを含まない。これは調査用の範囲であり、公式642件の評価を完了した意味ではない。[抽出結果とSHA](../reports/pro_v2_public_projection.json)。

3つの制御検査で、公開入力への正解列混入、許可列の拡張、露出台帳を無視する除外設定を拒否し、未閲覧の別リポジトリは残ることを確認した。元ファイルや実際の行はGitへ登録しない。新しいイメージの取得とモデル呼び出しは0件である。

## 公開要求を読む前に固定した次の候補

[抽出規則](../configs/pro_public_task_screen_v01.json)と[候補ID](../reports/pro_public_task_candidates_v01.json)を先にコミットする。固定した種とデータ版・リポジトリ名のSHA順で6リポジトリを選び、同様に各2件を選ぶ。対象はtutanota、flipt、openlibrary、teleport、navidrome、ansibleの12件となった。言語、HARDラベル、修正規模、モデル成績による順位付けは行っていない。

12件とした理由は、公開要求と基点コードの確認を段階的に進め、今のP3を終える前に大規模な環境導入を増やさないためである。残るwebclients、element-web、qutebrowser、vulsの4リポジトリの問題文は、この計画では読まない。適性を否定したのではなく、調査範囲外として保持する。後から追加する場合は別の計画と理由を残す。今回読む12件は開発用とし、未閲覧の確認用課題として扱わない。

選択処理の3検査で、行順の変化に対する候補の一致、調査外リポジトリの保持、正解列・閲覧済みリポジトリ・重複ID・入力ファイル変更の拒否を確認した。結果を見て候補を差し替えない。公開要求から複数箇所の実装が予想されても、元コードや実行を確認するまでは大規模な作業依存が実証されたとはしない。

## 12候補の公開要求を確認した結果

選択をコミット`90f2347`へ保存した後に、12件すべてのproblem_statement・requirements・interfaceを確認した。正解差分、追加評価テスト、HARDラベル、モデル成績は選定に使っていない。[候補ごとの全文要約・理由・基点版](../reports/pro_public_task_review_v01.json)を保存する。

| 番号 | 課題の内容 | この段階の扱いと理由 |
|---|---|---|
| 1 | tutanota：メール詳細の復号キーを各読み込み経路へ渡す | 基点コードまで調査。ローダー・転送・返信・索引・ルールとキーキャッシュが関係する |
| 2 | tutanota：保存資格情報の復号失敗を適切な例外へ変換 | 局所対照候補。指定された二層の例外変換が中心 |
| 3 | flipt：JWTだけの認証でDBを不要にする | 基点コードまで調査。設定・起動・定期処理の整合を確認する |
| 4 | flipt：ログのconsole/json設定 | 局所対照候補。型・定数・既定値を含む設定層の変更 |
| 5 | openlibrary：著者識別子の共通生成 | 局所対照候補。共通関数と展開時呼び出しが指定されている |
| 6 | openlibrary：Amazonの言語情報を取り込む | 局所対照候補。フィールド抽出と許可項目への転送 |
| 7 | teleport：必須MFA時の最後の装置削除を防ぐ | 局所対照候補。一つの削除処理の条件分岐が中心 |
| 8 | teleport：表の文字省略と脚注 | 局所対照候補。複数仕様はあるが単一描画部品内の処理 |
| 9 | navidrome：期限切れキャッシュを除く | 局所対照候補。時間・並行性の難しさと担当間依存を区別する |
| 10 | navidrome：容量・既定TTLの設定 | 局所対照候補。キャッシュ部品内の追加 |
| 11 | ansible：YAMLへの未定義値出力の例外 | 局所対照候補。指定ファイルのrepresenterが中心 |
| 12 | ansible：YAMLの信頼・由来とvault値の整合 | 基点コードまで調査。解析・出力・テンプレートと復号の境界が関係する |

「局所」は公開要求からの暫定分類で、簡単に成功することを実測した意味ではない。今回の要求は具体的な関数・引数・型まで指定するものが多い。これらは正式な入力として保持する。削除して依存の後発見を人工的に作らない。

## 3候補の基点コードで確認した範囲

修正前の固定コミットから21ファイル・358,352バイトを読み取り専用で取得し、関係箇所を確認した。Gitのblob値と各ファイルのSHA-256を照合し、URL・版・サイズを[記録](../reports/pro_public_base_sources_v01.json)した。ファイル全体を精読した、実行した、正解修正を再現したという意味ではない。

**番号1のtutanotaは、追加の依存観察用候補に残す。** `EntityClient`、`DefaultEntityRestCache`、`EntityRestClient`の引数転送と、`CryptoFacade.resolveSessionKey`のキャッシュ依存、返信・索引・ルールの呼び出し経路を確認した。複数の入口が同じキー表現・適用タイミングへ依存する。ただし変更方針は公開要求でかなり明示されており、未知の作業依存や集約の利益はまだ観測していない。[転送層](https://github.com/tutao/tutanota/blob/a834bd49d148888778075a3a48d3b92d832c4eed/src/api/worker/rest/DefaultEntityRestCache.ts)、[キー解決](https://github.com/tutao/tutanota/blob/a834bd49d148888778075a3a48d3b92d832c4eed/src/api/worker/crypto/CryptoFacade.ts)。

**番号3のfliptは、主課題候補の優先度を下げ、依存が比較的明示された対照として残す。** 設定の方式一覧から起動・cleanup開始・cleanup内の処理へ進む経路を確認した。複数ファイルにまたがるが、共通フラグの一方向の伝達で整合できる可能性が高く、相互に方針を決め直す必要性の根拠はまだ弱い。これは静的な観察に基づく判断で、性能測定ではない。[起動](https://github.com/flipt-io/flipt/blob/7620fe8bb64c0d875f419137acc5da24ca8e6031/internal/cmd/authn.go)、[定期処理](https://github.com/flipt-io/flipt/blob/7620fe8bb64c0d875f419137acc5da24ca8e6031/internal/cleanup/cleanup.go)。

**番号12のansibleを、最初の追加環境の導入候補にする。** 入力を通常の文字列へ変換するfilterと、注釈を受け取るLoaderの境界、vaultを扱うDumperとテンプレートのmarker受理規則を確認した。Dumper内の変更だけでは、その前段で失敗する経路を直せない可能性がある。解析と出力の往復条件を含み、複数の層の契約を同時に満たす対象として調べる価値がある。既存基盤と同じPython系の実行・検査経験を使える点も、導入順序の理由にする。[filter](https://github.com/ansible/ansible/blob/6198c7377f545207218fe8eb2e3cfa9673ff8f5e/lib/ansible/plugins/filter/core.py)、[Loader](https://github.com/ansible/ansible/blob/6198c7377f545207218fe8eb2e3cfa9673ff8f5e/lib/ansible/_internal/_yaml/_loader.py)、[marker受理規則](https://github.com/ansible/ansible/blob/6198c7377f545207218fe8eb2e3cfa9673ff8f5e/lib/ansible/template/__init__.py)。

この選択は主実験への正式採用ではない。まずV2の正しいイメージ、必要容量、Apple siliconでの実行、基準状態、独立評価の正負対照を確認する。Proの旧docker_image列をV2用と誤用しない。進行中のP3が完了するまでは新しいコンテナやビルドを動かさず、資源条件を維持する。

## 最初の1環境の取得前確認と実行計画

候補12のV2 `Dockerfile`、`task.toml`、`instruction.md`を公式固定版から確認した。HuggingFaceの公開3項目は、そのまま公式instructionにも含まれていた。公式設定はlinux、1 CPU、memory_mb=4096、storage_mb=10240、agent/verifierは各3,000秒である。これらは設定値であり、実測した必要量ではない。[公開メタデータの記録](../reports/pro_environment_public_metadata.json)。

レジストリのmanifestだけを読み、linux/amd64とdigest `sha256:2ee62346a660d4329f1b4126ecadd02291a0ffca97939c478fbe2b4683dc3e5e`を確認した。22層の圧縮サイズ合計は760,385,698バイトで、展開後容量と作業領域は未測定。タグではなくこのdigestを取得対象にする。[manifestと照合記録](../reports/pro_candidate_image_manifest.json)。

[実行前に固定した計画](../configs/pro_environment_feasibility_v01.json)は、P3の4試行の実行・評価完了後に、イメージ1件の取得、隔離した起動確認、空差分の不合格、参照修正の合格を順に測る。参照修正と評価テストは専用の評価側へ機械的に取得し、本文を研究者・生成側へ表示しない。各対照は新しいコンテナで行い、原ログと失敗を保持する。公式V2検査をローカルのColima/Dockerへ接続するため、Modal/Harborでの公式モデル成績の再現とはしない。

取得前にVM内15GiB・ホスト20GiBの空きを下回らないことを確認し、展開後にも測る。この閾値は設定上の作業領域と余裕を確保するための運用上の上限確認で、圧縮サイズから展開容量を保証する式ではない。無関係なコンテナやモデルを自動削除しない。主課題の正式採用とモデル試行は、この環境確認の後に判断する。

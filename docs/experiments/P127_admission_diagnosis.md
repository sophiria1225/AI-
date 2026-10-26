# P127: 全132保存programのAST受理診断

閉鎖済みP127の全8条件・132 programを固定compilerで静的に再計画した。**受理0件は再現したが、構文制限の緩和だけで成立する小さな改善は確認できない。** 対象APIを呼ぶprogramは各方式2件だけで、両方とも完全な戻り値を永続dictへ保存する。後段の表示が読むfieldは限定されていても、その保存を部分値へ置換してよい証拠はない。本診断から次のモデル実験を採択しない。token削減、品質維持、新規性、形式的な意味保存の証明は主張しない。

[全件の公開診断JSON](../../reports/P127_ast_admission_diagnosis_20261026.json)に全8条件、132 programのordinal・source SHA、拒否件数、field名を残す。[閉鎖結果](P127_findings.md)と[固定計画](P127_whole_task_region_projection.md)は別記録として維持する。

## 全件の結果

同じtask slotの両方式では、保存programのsource bytesと位置情報を除くASTが**66/66対すべて一致**した。対応欠落0。下表の各task行は両方式それぞれの件数である。

| task slot | program数/方式 | unsupported_program_effect | no_supported_top_level_region | 受理 | show_song構文site | read_fields構文site |
|---|---:|---:|---:|---:|---:|---:|
| 01 | 14 | 3 | 11 | 0 | 0 | 0 |
| 02 | 17 | 0 | 17 | 0 | 0 | 0 |
| 03 | 8 | 0 | 8 | 0 | 0 | 0 |
| 04 | 27 | 5 | 22 | 0 | 2 | 0 |
| 全8条件 | 132 | 16 | 116 | 0 | 4 | 0 |

whole-program構文の拒否は16 program。拒否predicate別のprogram数は、非対応method属性12、name直下のmethod call等ではない属性12、単一・非aliasのjson以外のimport8、非対応named call4、unpack/multiple assignment2、保護されたcall機能の直接call以外での利用2、GeneratorExp2、ImportFrom2。同じprogramに複数該当するため加算できない。

全44 top-level `For`における最初の候補拒否条件は、先頭callが対象APIでない20、iterableがnameでない10、先頭文がsimple call assignmentでない8、戻り値全体をdestinationへ保存する4、loop targetがnameでない2。一般的な構文拒否を、対象APIの取得削減機会として数えない。

公開実行summaryの`recorded_execution_error`は静的理由を上書きする場合がある。本診断はそのprogramも除外せず、保存source全件を再計画した。全条件で記録された静的受理・変換・projection lookup・partial hitが0であることと整合する。

## 対象callの消費と可視性

対象callはtask slot 04の保存順ordinal 13と14に各1構文siteあり、両方式で同じsourceだった。ordinalは保存program列の順序であり、model呼出し番号ではない。

| program ordinal | whole-program構文 | 対象loop内 | 同program後段の直接field読取 |
|---|---|---|---|
| 13 | 受理可能 | 戻り値全体をdictへ保存、field抽出0 | `title` 1、`artists` 1；artistの`name`をListCompで抽出 |
| 14 | 非対応構文あり | 同じ完全値保存、field抽出0 | `title` 1、`artists` 1；artistの`name`をGeneratorExpで抽出 |

どちらも対象callはtop-level forの先頭にあり、戻り値をnameへ代入した後、iteration itemをkeyとしてdestinationへ全体保存する。後続の別loopでdestinationからrecordを取り出し、上記fieldを読む。

固定[`_consumer_expr`](../../scripts/automatic_field_projection.py#L133)はimmutable scalar、新しく作るartist-name list、それらを含む新しいdict等を許可するが、戻り値全体は許可しない。[`_candidate`](../../scripts/automatic_field_projection.py#L166)がこのconsumer条件を検査する。ordinal 13は構文上安全でもここで拒否される。ordinal 14にはnon-json import、GeneratorExp、未対応method等の拒否もあるが、それらを許可しても完全値保存が残る。

`title`と`artists`は既存field契約内で、対象callのloop形もtop-level/name iterableなので、非対応fieldやnested loopがこの2 siteの主因ではない。現行[`_project_loop`](../../scripts/region_field_projection.py#L231)は最後のiterationのrootへ通常の完全responseを代入するが、途中の各recordを別dictへ保存した場合、最後の1件だけ完全でも全entriesの完全値可視性を保存できない。

## 手順・source束縛・限界

1. 閉鎖済み[comparison](../../reports/P127_comparison.json)の全8行・132 `program_costs`と、対応する保存program集合が一致することを確認した。保存JSONから選んだ`code`以外の内容は分析しない。各source SHAをcomparisonと照合した。
2. [固定config](../../configs/P127_whole_task_region_projection_v01.json)のsource bindingとcompiler/runtimeのhashを照合した。保存sourceはASTとして解析し、[`plan_region_projection`](../../scripts/region_field_projection.py#L250)を呼んだ。同関数の`compile(AST)`は構文検査であり、生成sourceの実行関数は呼んでいない。
3. [`_safe_source`](../../scripts/region_field_projection.py#L120)の拒否predicateを分類し、全132件で元predicateのbooleanと一致することを確認した。全44 top-level loopの分類も固定[`_candidate`](../../scripts/region_field_projection.py#L201)のbooleanと一致した。この照合は別実装による意味保存証明ではない。
4. 両方式をtask slotとprogram順序で照合し、全66対のsource bytes/AST等値を確認した。対象callでは直接の代入・参照形を追い、後段のfield名だけを集計した。動的実行回数、全alias、将来generationの需要、値のauthority coverageはこの診断から確定しない。

生成source実行、追加model/API/evaluator/tokenizer/Docker呼出しはすべて0。実行時のentry guardやauthority lookupは静的受理0により到達していないため、それらの失敗や値不足を今回の拒否原因と推定しない。公開物にはraw code、値、課題・programのprivate識別子、namespace内容、絶対private pathを含めない。元診断と再現scriptは非公開のまま保持し、それぞれのSHAをJSONへ記録した。

private source binding集合は件数132とSHA `14b02224a0ba985367dd4219e0a2cb7204064b2dec0e85cf4b886f978c750345`のみを公開する。集合はtask slot、policy、program ordinal順に並べ、object keyをsortした空白なしUTF-8 JSONとしてhash化した。公開JSONのsource SHA一覧は、非公開のfile hash・実行plan束縛の一覧を置換するものではない。生sourceが非公開のため、公開資料だけでは再解析を完全再現できない。

## 次実験を支持しない理由

共有済みの[`read_fields` guide](../../scripts/region_projection_runtime.py#L31)には、まさに`title`/`artists`を指定する例と「部分dictは完全API responseではない」という契約がある。joined authority、明示field機能、通常の完全response cache、schema feedback、receipt、rolling historyは両方式で共通だった。今回`read_fields`は全132 sourceで0 call、通常cacheはtask slot 04で各方式72 hitした。その通常cache利用を自動変換の効果へ数えない。

見えている未対応範囲は、取得loopと別消費loopをまたぐ需要推定である。しかし完全recordを永続dictに保存する以上、必要なのは単なる構文追加ではなく、未読fieldを省いてよい寿命・可視性の根拠である。現在の表示が2 fieldを読むことだけでは足りず、明示的な部分値の契約は既存対照がすでに提供する。本診断では、その対照と既知のroot escape問題を越える、安全な最小の機構差を確定できなかった。同条件反復や追加seedを始める根拠にはしない。

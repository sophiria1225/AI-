# P122 CSV追加診断の実行手順記録（事後文書化）

対応集計: [集計](../../reports/closed_csv_review_20261026.json)。

これは2026-10-26に実行済みの読取診断を、会話に残るPython heredocから文書化したもの。独立した実行scriptは当時保存していない。この文書作成時に診断を再実行していない。事前登録済み実験、固定前から存在した解析code、第三者による独立再現として扱わない。追加のモデル、環境API、tokenizer、保存model生成code、評価器の実行は０だった。

## 入力範囲と144ファイルの意味

固定パスは `records/context_pilot/BOC_P122_R{01,02,03}_04_{SINGLE_CHECKPOINT,INLINE_CHECKPOINT}` の６run。すべて閉鎖済みの既知CSVで、P123や他の課題を含めない。

- 各runの `events.json` と `spans.json`、計12ファイル。
- 各runの `call_*/request.json` をlexicographic sort。件数は32,28,10,10,26,24、計130ファイル。成功した生成だけでなく、保存requestのある最終未完了試行も含む。
- R01 inlineの `programs/call_021_01/input_private.json` と `result_private.json`、計２ファイル。
- 計144は**読取ソースファイル数**。144モデル入力ではない。schema可視性確認で同じrequestを再読した分はsource辞書の同じkeyへ上書きされ、固有ファイル数を増やさない。

最終aggregateを作る実行では各ファイルを `Path.read_bytes()` で読み、同じbyte列のSHA-256を計算し、`json.loads`した。absolute path→hashを`source_file_sha256`へ保存。読み終えた後の再hash不変性検査や、以前の診断実行との別hash照合はしていない。既閉鎖記録のread-only集計という範囲である。

## A. 同じactive input内のstdout全文重複

各requestは独立に処理した。`request['messages']`のうち`role == 'tool'`だけを調べる。

1. `message.get('content', '')`を`json.loads`。ValueErrorまたはTypeErrorなら対象外。
2. 得た値が厳密なdictなら`value.get('observation')`を取る。それ以外は対象外。
3. observationが厳密なdictで、次の条件をすべて満たすstdoutだけをlistへ入れる。
   - `observation.get('status') == 'ok'`。
   - `error`, `stdout_truncated`, `unknown_effects`, `declared_complete`のどれもtruthyでない。
   - `type(observation.get('stdout')) is str`。
   - `observation['stdout'].strip()`が非空。
4. そのrequest内だけでPython `Counter`を作る。keyは**元のstdout文字列そのもの**。trim/空白正規化/JSON再整形/大文字小文字変更をしていない。観測span ID、API IDや外側tool本文全体をkeyにしていない。
5. 出現数>1のkeyを重複とする。重複がある境界だけ、group数、余分なcopy数`sum(n-1)`、余分な文字数`sum(len(s)*(n-1))`を保存した。

実装の中心は次と同じ。

```python
vals = []
for m in request.get('messages', []):
    if m.get('role') != 'tool':
        continue
    try:
        v = json.loads(m.get('content', ''))
    except (ValueError, TypeError):
        continue
    o = v.get('observation') if type(v) is dict else None
    if (type(o) is dict and o.get('status') == 'ok'
            and not any(o.get(k) for k in
                        ('error', 'stdout_truncated', 'unknown_effects', 'declared_complete'))
            and type(o.get('stdout')) is str and o['stdout'].strip()):
        vals.append(o['stdout'])
c = Counter(vals)
duplicates = {s: n for s, n in c.items() if n > 1}
```

結果は全130requestで重複境界０。これは「同じ観測を後続requestへ再送する」通常のhistory costを０と言うものではない。部分文字列の一致、異なる整形の同値、異なるstdoutの共通データ、assistant本文、summary、paged/非標準tool表現の重複はこの判定範囲外。対象外観測数を集計していないため、全toolデータについての網羅的な重複不存在証明ではない。

## B. 全引数一致のAPI再出現と６read区間

`events.json`の保存list順に走査した。時系列やschema整合性をこの追加scriptで独立再監査したわけではない。

`canonical(x)`は `json.dumps(x, sort_keys=True, separators=(',', ':'))`。Python標準のその他defaultを使用した。

read集合は、既存`field_read_contract.py`に合わせた次の６名を明示的に列挙した。

```text
spotify__show_song_library
spotify__show_song
spotify__show_album
spotify__show_playlist
spotify__show_playlist_library
spotify__show_album_library
```

手順:

1. `event.get('api_request_sent')`がfalseならそのeventをskip。この追加診断では未送信eventを状態区間の失効理由にしていない。
2. `spans[event['span_id']]['action']`のargumentsがstrならJSON decode。request keyは `(action['name'], canonical(arguments))`。**認証値を含む全引数を保持**。アクセスtokenの削除・同一主体への正規化はしない。
3. 比較するresultは `canonical(span['observation'])`、すなわち保存されたobservation全体。`observation`内部の業務valueだけへ展開しない。
4. `returned`は `(event.get('api_execution') or {}).get('status') == 'returned' and not event.get('effects_unknown')`。bridge nonce、public契約版、business errorの意味、cache可否等を追加検証していない。
5. `not returned`、またはAPI名が上記６read外なら、その場で区間辞書`epoch_seen`をclear。全履歴辞書`seen`はclearしない。
6. returnedかつkeyが`seen`にある場合、`full_argument_repeat`を１増。全observationも以前の値に等しければ`full_argument_and_observation_repeat`も増やす。
7. 同じ条件の中で、API名がread集合内かつkeyが`epoch_seen`にもあれば、`conservative_read_interval_repeat`を増。区間内直前の全observationと等しければ`conservative_read_interval_repeat_equal`を増。現在call、前call、公開API名、等値boolだけを保存。
8. returnedなら`seen[key]=(current_call, observation_string)`へ更新。さらにread名なら`epoch_seen`も更新。したがって比較先はそのkeyの**最後の正常返却**。

要点のpseudocode:

```python
if not event.get('api_request_sent'):
    continue
key = (api_name, canonical(full_arguments))
value = canonical(full_observation)
returned = api_execution_status == 'returned' and not effects_unknown
if not returned or api_name not in read_names:
    epoch_seen.clear()
if returned and key in seen:
    count_full_repeat()
    count_full_equal_if(value == seen[key][1])
    if api_name in read_names and key in epoch_seen:
        count_interval_repeat()
        count_interval_equal_if(value == epoch_seen[key][1])
if returned:
    seen[key] = (call, value)
    if api_name in read_names:
        epoch_seen[key] = (call, value)
```

結果はR02/seed157の各armに区間内一致13件（library１、show_song12）、R01/R03の区間内候補０。R01の別の説明で述べた「認証値を除いたlibrary再取得」は**このaggregateのfull-argument一致とは違う先行診断**であり、混ぜない。

この区間化は実装可能な安全cacheを作った測定ではない。既存６read集合の契約を今回改めて検証しておらず、未送信作用不明eventの失効を含む全runtime安全条件を検査しない。後の返却一致を以前の時点へ供給していないが、それだけで省略が許可されるわけでもない。13/12を回避済みAPI数やtoken節約として扱わない。

## C. call021のschema block照合とactive可視性

R01 inline call021の保存program入力から`api_schemas`を取り、結果の`stdout`と比較した。元programは実行せず、codeのeval/execもしない。

```python
blocks = {
    name: json.dumps(schema, indent=2)
    for name, schema in input_record['api_schemas'].items()
    if json.dumps(schema, indent=2) in result_record['stdout']
}
matched_schema_characters = sum(
    len(block) * stdout.count(block) for block in blocks.values()
)
```

- `json.dumps`のindent2以外はdefault。JSON意味同値ではなく、そのrendered文字列の**完全substring一致**。
- 26個の完全snapshot schemaのrenderが一致し、全stdout18,348文字に対する上式の一致長合計は17,543文字。
- `str.count`は各blockについて非重複出現数を返すが、**異なるblock同士の区間非重複は追加検査していない**。したがって17,543は「一致block長×出現数の合計」であり、厳密に検証済みの区間union長や削除可能文字数とは呼ばない。残り805も意味分類していない。
- Namespaceがすべてfile_systemであることは最初の小集計で確認したが、最終aggregateはschema名を保存せず総数を保存した。
- 値が一致することから、実runtime aliasの由来、当該情報の不要性、削除後の同じ行動を推定しない。

可視性は保存requestのcall021,022,028だけを別に検査。tool messageのcontentをJSON decodeし、dictのobservationにstr stdoutがあれば集めた。この可視性検査ではAのstatus/error等の適格条件を再適用していない。

各schema blockについて`any(block in text for text in visible_tool_stdouts)`を数える。またcall021のstdout全文に`text == target_stdout`となるvisible stdout数を数える。結果はcall021でschema0/full0、call022と028でschema26/full1。

この結果はcall021より前にschemaの意味・引数・別整形がどこにもなかったことを示さない。system、assistant本文、summary、直接tool schema、Python namespace、archive-onlyの情報は同じ可視性カウンタに含めていない。call022–028の全７境界を個別に数えた結果としても扱わない（保存aggregateが明示する３境界のみ）。

## 公開時の表現

安全な表現は「閉鎖済み既知CSV６runの130保存requestについて、定義した正常stdout全文の同一入力内重複は０。特定のschema再印字は26個のsnapshot schemaと完全文字列一致し、一致block長合計17,543文字。API再取得、履歴再送、同一入力内の二重copyを区別した」まで。

この集計は事後の適用機会診断で、新しい方式の有効性、反実仮想成功、一般的な品質維持、全費用削減、新規性を実証しない。未知のモデル使用量は入力文字列やreservationから補完していない。元のP122失敗・不明・停止理由を変更しない。

公開整理時の追加確認: 統合担当が上記144私有ソースのSHA-256を再照合し、全件一致を確認した。診断自体の独立再実行とは区別する。

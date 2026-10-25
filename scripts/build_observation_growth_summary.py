"""Publish all P116 conditions, calls and API repetitions without raw values."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from receipt_reasoning_history import require


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
def csv_new(path, rows):
    require(bool(rows), 'nonempty_all_condition_rows_required')
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader(); writer.writerows(rows)


def build(root):
    source=root/'reports/P116_observation_growth.json'; data=read(source)
    require(data['status'] == 'complete' and not data['errors'] and data['completed_conditions'] == 16,
            'complete_all_sixteen_conditions_required')
    require(len(data['runs']) == 16 and sum(len(r['calls']) for r in data['runs']) == 283
            and sum(len(r['API_repetitions']['rows']) for r in data['runs']) == 820
            and sum(r['unknown_usage_calls'] for r in data['runs']) == 2,
            'all_original_attempts_API_and_unknowns_required')
    folder=root/'materials/20261025_p116_results'
    require(not folder.exists(), 'preserve_all_existing_P116_materials')
    folder.mkdir()
    runs=[]; calls=[]; APIs=[]; names=[]; exposures=[]
    for r in data['runs']:
        identity={k:r[k] for k in ('source_audit','run_id','task_id','reasoning_display_policy')}
        repeat=r['API_repetitions']; exposure=r['tool_exposure']
        runs.append(dict(**identity, **{k:r[k] for k in ('success','stop_reason','model_calls',
            'api_requests','known_total_tokens','unknown_usage_calls','checked_requests',
            'unavailable_requests','known_response_calls_with_no_API')},
            **r['input_character_exposures'],
            tool_first_seen_characters=exposure['first_seen_characters'],
            tool_replayed_characters=exposure['replayed_characters'],
            exact_API_request_repeats=repeat['exact_request_repeats'],
            same_returned_observation_repeats=repeat['same_returned_observation_repeats'],
            same_conservative_read_epoch_repeats=repeat['same_conservative_read_epoch_repeats']))
        for c in r['calls']:
            inp=c['input']
            calls.append(dict(**identity, **{k:c[k] for k in ('call_id','ordinal','usage_status',
                'known_total_tokens','measured_input_tokens','measured_output_tokens',
                'measured_cached_input_tokens','API_requests')}, input_status=inp['status'],
                **{k:v for k,v in (inp.get('components') or {}).items() if k.endswith('_characters')},
                **{'tool_'+k:v for k,v in (inp.get('tool_exposure') or {}).items()}))
        APIs.extend(dict(**identity,**row) for row in repeat['rows'])
        names.extend(dict(**identity,api=name,**values) for name,values in repeat['by_api'].items())
        exposures.extend(dict(**identity,**row) for row in exposure['messages'])
    files={name:rows for name,rows in [('all_conditions.csv',runs),('all_calls.csv',calls),
        ('all_API_requests.csv',APIs),('all_API_names.csv',names),('all_tool_exposures.csv',exposures)]}
    for name,rows in files.items(): csv_new(folder/name,rows)
    summary=dict(phase='P116',status='complete',source_sha256=sha(source),conditions=runs,
        original_known_logical_tokens=3026706,original_unknown_usage_calls=2,
        source_conditions=16,independent_known_tasks=4,original_model_attempts=283,original_API_requests=820,
        all_character_fields_are_not_native_tokens=True,causal_effect_claim=False,
        measured_savings=None,novel_method_claim=False,
        private_reasoning_or_API_argument_values_published=False)
    write_new(folder/'summary.json',summary)
    text='''# P116: 公開観測の再送と同一API要求の全件点検

閉鎖済みP111/P114の全16条件、283要求、820 APIを対象とする. 既知費用3,026,706 tokenと元の未知使用量２件を保持する. 新しい生成、API、Python実行、評価、task DB、未見12課題、tokenizerの呼出しは０.

`all_conditions.csv`は全16条件、`all_calls.csv`は全283要求、`all_API_requests.csv`は全820 API、`all_API_names.csv`はAPI名別内訳、`all_tool_exposures.csv`はモデル入力へ実際に含まれた各観測の表示回数を保持する. 元の未知使用量を文字数や他の推定値で補わない.

入力はUnicode文字数を重複しない本文フィールドで数える. JSON構文、通信識別子、モデルのtemplateを含むnative token数ではない. 同じ観測の再送は、全messageと同一入力内の出現番号で識別する. 内容が同じでも通信IDが違う観測はまとめない. 繰り返し表示が意味的に不要とは判定しない.

API要求は認証を含む全引数の指紋で比較する. 元から確認済みのSpotify６読取操作だけを区別し、それ以外の操作、失敗、未知の作用は保守的な区間を切る. 同一区間の同一要求も通常キャッシュの調査候補に留まり、cacheの有効性、置換の安全性、token削減の証明ではない. 後で返答が一致したことを、その前の時点で利用可能だった根拠にしない. APIが０のモデル呼出しもPython内の計算を行うため無駄とは分類しない.

新しい方式の採用、一般的品質維持、新規性は主張しない. 生の観測、API引数、モデル推論は公開しない. 原稿は保留し、全条件の内訳から次の具体的な介入を判断する.
'''
    with (folder/'README.md').open('x') as stream:stream.write(text)
    paths=list(files)+['summary.json','README.md']
    manifest=dict(source_report_sha256=sha(source),source_code_sha256=sha(Path(__file__)),
        all_conditions=16,all_calls=283,all_API_requests=820,
        files={p:sha(folder/p) for p in paths})
    write_new(folder/'build_manifest.json',manifest)
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args();result=build(args.repo_root.resolve())
    print(json.dumps({k:result[k] for k in ('all_conditions','all_calls','all_API_requests')}))

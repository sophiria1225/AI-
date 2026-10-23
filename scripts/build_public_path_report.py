"""Publish all P77 rows and CSVs from closed metadata; never reread task traces."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path

from public_path_scope import cost

ROOT=Path(__file__).resolve().parents[1]
SOURCE='reports/P77_public_path_scope.json'
DEST='materials/20261023_p77'


def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def read(path):return json.loads((ROOT/path).read_text())
def save(path,value):(ROOT/path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def validate():
    r=read(SOURCE);original=read('reports/P76_comparison.json')
    if (r['status']!='complete' or not r['all_eight_accounted'] or len(r['rows'])!=8
            or r['git_commit']!='f4866ab790e43cee5137edbfbdac14dfaba47b2d'
            or r['plan_sha256']!=sha('configs/P77_public_path_scope_v01.json')
            or r['source_sha256']!=read('configs/P77_public_path_scope_v01.json')['source_sha256']
            or r['measured_savings'] is not None or r['safe_omission_verified']):
        raise ValueError('closed_fixed_P77_required')
    for group in ['source_sha256','implementation_sha256']:
        for path,value in r[group].items():
            if sha(path)!=value:raise ValueError('source_or_inspector_changed')
    calls=[];programs=[];repeats=[]
    for row,old in zip(r['rows'],original['rows'],strict=True):
        if (row['run_id']!=old['run_id'] or row['task_id']!=old['task_id'] or row['arm']!=old['arm']
                or row['original_success']!=old['success'] or row['original_stop_reason']!=old['stop_reason']
                or row['total']!=cost(row['calls'])
                or dict(Counter(p['status'] for p in row['programs']))!=old['program_status_counts']
                or len(row['repeated_requests'])!=old['repeat_identical_request_excess']
                or sum(p['sent_api_requests'] for p in row['programs'])!=old['api_requests']):
            raise ValueError('all_condition_correspondence_disagrees')
        for name,digest in r['private_record_sha256'][row['run_id']].items():
            if digest!=old['source_sha256'][name]:raise ValueError('original_record_hash_changed')
        for category,total in row['partition'].items():
            if total!=cost([c for c in row['calls'] if c['category']==category]):
                raise ValueError('cost_partition_disagrees')
        calls.extend({'run_id':row['run_id'],**v} for v in row['calls'])
        programs.extend({'run_id':row['run_id'],**v} for v in row['programs'])
        repeats.extend({'run_id':row['run_id'],**v} for v in row['repeated_requests'])
    if (cost(calls)!=r['total'] or len(calls)!=43 or len(programs)!=40 or len(repeats)!=42
            or any(r[k] for k in ('model_generations','tokenizer_requests','environment_api_requests',
                'evaluator_calls','task_databases_read','reserved_scenarios_read','saved_code_executions',
                'private_reasoning_text_inspected','runtime_rewriting','novel_method_claim'))):
        raise ValueError('population_or_scope_disagrees')
    return r,calls,programs,repeats


def export_csv(path,rows):
    with (ROOT/path).open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list))
                        else '' if v is None else v for k,v in row.items()})


def build():
    r,calls,programs,repeats=validate();out=ROOT/DEST;out.mkdir(exist_ok=True)
    export_csv(DEST+'/all_calls.csv',calls)
    export_csv(DEST+'/all_programs.csv',programs)
    export_csv(DEST+'/all_repeated_requests.csv',repeats)
    lines=['# P77：全８条件の公開実行経路', '',
        'P76終了後の事後読取。全43生成試行・40公開Pythonプログラムを照合した。',
        '追加の生成・入力計数・環境API・評価・DB内容・保留群・推論本文・保存コード実行は０。', '',
        '| 課題・履歴 | 元成否 | APIあり生成／既知token | APIなし既知生成／token | 不明・未実行生成 | 同一要求／同一返却 |',
        '|---|---|---:|---:|---:|---:|']
    for i,row in enumerate(r['rows']):
        task=('写真','精算','返金','書出し')[i//2];arm='公開のみ' if i%2==0 else '推論保持'
        a=row['partition']['known_with_sent_api'];b=row['partition']['known_without_sent_api'];c=row['partition']['unknown_usage_unexecuted']
        lines.append(f'| {task}・{arm} | {"成功" if row["original_success"] else "未達"} | '
            f'{a["model_calls"]} / {a["known_total_tokens"]:,} | {b["model_calls"]} / {b["known_total_tokens"]:,} | '
            f'{c["model_calls"]} | {len(row["repeated_requests"])} / {sum(v["same_observation"] for v in row["repeated_requests"])} |')
    lines += ['', 'tokenはP76の継続費用の内訳であり、新しい費用・節約可能額ではない。前半込みの仕事費用は[P76全結果](../../docs/P76_findings.md)を参照する。', '',
        '[全43生成CSV](all_calls.csv)／[全40プログラムCSV](all_programs.csv)／[全42同一要求CSV](all_repeated_requests.csv)。',
        'CSVの空欄はnullで、使用量不明を０へ補完していない。構文の関数名・変数名は実行意味や必要性の証明ではない。', '',
        '写真の公開のみ条件には同じ42要求・同じ42返却があり、その間の送信APIはファイル詳細だけだった。通常の推論保持側には同一要求の再送０。一方、保持側にも終了前のディレクトリ確認は残る。反復が全て不要だったことや、安全なcacheの一般契約は示していない。', '',
        '書出しの保持側は、set・sorted・printなどの構文を持つ２プログラムを実行し、次の生成中に時間上限となった。取得０を無用な計算や効率的な成功としない。公開のみ側では60件の曲詳細取得を含むプログラムがOSErrorで終了し、その後の原文参照・ローカル処理も保存する。精算では両側にTypeErrorが１件ずつあり、返金では両側が取引と完了通知を送って成功した。', '',
        '[全結果と解釈](../../docs/P77_findings.md)／[固定計画](../../docs/experiments/P77_public_path_scope.md)／[元集計](../../reports/P77_public_path_scope.json)／[閉じた集計の照合](../../reports/P77_public_path_audit.json)。', '',
        '新しいモデル比較は未配分。次の規則には、通常方式との差と、必要情報・作用・例外を保つ公開の根拠が必要である。']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    audit={'phase':'P77','audit_errors':[],'all_eight_accounted':True,'source_sha256':sha(SOURCE),
           'all_calls':len(calls),'all_programs':len(programs),'all_repeated_requests':len(repeats),
           'same_observation_repeated_requests':sum(v['same_observation'] for v in repeats),
           'total':r['total'],'known_without_sent_api':cost([c for c in calls if c['category']=='known_without_sent_api']),
           'unknown_usage_unexecuted':cost([c for c in calls if c['category']=='unknown_usage_unexecuted']),
           'read_wall_seconds':r['wall_seconds'],'measured_savings':None,'safe_omission_verified':False,
           'all_condition_outcomes_unchanged':True,'builder_sha256':sha('scripts/build_public_path_report.py'),
           'material_sha256':{p:sha(p) for p in (DEST+'/README.md',DEST+'/all_calls.csv',DEST+'/all_programs.csv',DEST+'/all_repeated_requests.csv')}}
    save('reports/P77_public_path_audit.json',audit)
    return audit


if __name__=='__main__':
    result=build();print({k:result[k] for k in ('all_eight_accounted','all_calls','all_programs','all_repeated_requests')})

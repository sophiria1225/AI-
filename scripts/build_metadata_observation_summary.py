"""Retain every P117 condition, request and observation in public tables."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from receipt_reasoning_history import require


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_new(path,value):
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def csv_new(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True)
            if type(v) in (dict,list) else v for k,v in row.items()})


def build(root):
    source=root/'reports/P117_public_metadata_observations.json';d=json.loads(source.read_text())
    require(d['status']=='complete' and not d['errors'] and d['completed_conditions']==16,'all_sixteen_conditions_required')
    require(sum(len(r['calls']) for r in d['runs'])==283
            and sum(len(r['observations']) for r in d['runs'])==263,'all_request_observation_slots_required')
    folder=root/'materials/20261025_p117_results';require(not folder.exists(),'preserve_existing_P117_materials')
    folder.mkdir();runs=[];calls=[];observations=[]
    for r in d['runs']:
        identity={k:r[k] for k in ('source_audit','run_id','task_id','reasoning_display_policy')}
        runs.append(dict(**identity,**{k:r[k] for k in ('success','stop_reason','model_calls',
            'api_requests','known_total_tokens','unknown_usage_calls')},**r['summary']))
        calls.extend(dict(**identity,**c) for c in r['calls'])
        observations.extend(dict(**identity,**e) for e in r['observations'])
    for name,rows in [('all_conditions.csv',runs),('all_calls.csv',calls),('all_observations.csv',observations)]:
        csv_new(folder/name,rows)
    summary=dict(phase='P117',status='complete',source_report_sha256=sha(source),all_conditions=16,
        all_requests=283,all_observations=263,original_unknown_usage_retained=2,
        conditions=runs,all_observation_summary=d['summary'],
        semantic_irrelevance_or_dataflow_provenance_established=False,measured_savings=None,novel_method_claim=False)
    write_new(folder/'summary.json',summary)
    with (folder/'README.md').open('x') as f:f.write('''# P117: 全観測と固定公開API仕様の照合

P116の全16条件・283要求・263観測出現を保持し、stdout全体が固定公開APIの完全な関数仕様と一致するかを確認する. 生の観測、生成コード、推論、課題データは公開しない. 元の成功・未達・未知使用量２件を保持する.

`all_conditions.csv`は全条件、`all_calls.csv`は全要求、`all_observations.csv`は全観測を含む. 不一致、解析不能、ページ表示、保護対象の結果も除かない. schemaの名前・引数・説明を含む全体一致だけを数え、文中の都合のよい部分は抽出しない. 公開仕様との値一致と、実際の変数から出力されたという由来や、モデルの判断に不要という性質は異なる.

再送量は文字数. native token、削減実績、品質維持ではない. 部分省略、モデル生成、API、生成Python実行、評価、tokenizer、task DB、未見12課題の処理は０. 原稿は保留. 既存の文書省略や状態保持の負の結果を覆すものではなく、新規性は未確立.
''')
    paths=['all_conditions.csv','all_calls.csv','all_observations.csv','summary.json','README.md']
    manifest=dict(source_report_sha256=sha(source),source_code_sha256=sha(Path(__file__)),
        files={name:sha(folder/name) for name in paths},all_conditions=16,all_requests=283,all_observations=263)
    write_new(folder/'build_manifest.json',manifest);return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    result=build(p.parse_args().repo_root.resolve())
    print(json.dumps({k:result[k] for k in ('all_conditions','all_requests','all_observations')}))

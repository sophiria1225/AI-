"""Prepare local-only P16 semantic-review packets; no model or evaluator access."""
import argparse
import hashlib
import json
from pathlib import Path
import random


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--rubric',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if read(args.run/'status.json')['status'] in ('running','preflight'):
        raise ValueError('wait for all planned outputs or a terminal failure')
    rubric=read(args.rubric)
    is_contract_review = rubric.get('experiment') == 'P17_01'
    rows=read(args.run/'results.json')
    random.Random(rubric['packet_shuffle_seed']).shuffle(rows)
    args.output.mkdir(parents=True,exist_ok=False)
    mapping=[];counts={'outputs':len(rows),'valid_outputs':0,'items':0,'done_items':0}
    for i,row in enumerate(rows,1):
        packet_id=f'review_{i:03d}'
        mapping.append({'packet_id':packet_id,'case_id':row['case_id'],'variant':row['variant'],'call_id':row['call_id']})
        if is_contract_review:
            mapping[-1]['seed'] = row['seed']
        case=read(args.inputs/(row['case_id']+'.json'))
        packet={'packet_id':packet_id,'schema_valid':row['schema_valid'],
                'task':case['task'],'tools':case['tools'],'spans':case['spans'],'receipts':case['receipts'],
                'selected_span_ids':case['selected_span_ids'],'items':[]}
        if is_contract_review:
            packet['additional_sources'] = {'task': {'kind': 'user_requirement', 'value': case['task']}}
        if row['schema_valid']:
            ledger=read(args.run/row['call_id']/'ledger_private.json')
            packet.update(constraints=ledger['constraints'],unresolved=ledger['unresolved'])
            packet['items']=[{'item_index':j,'item_sha256':digest(item),'item':item} for j,item in enumerate(ledger['items'])]
            counts['valid_outputs']+=1;counts['items']+=len(packet['items'])
            counts['done_items']+=sum(item['status']=='done' for item in ledger['items'])
        (args.output/(packet_id+'.json')).write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
    (args.output/'mapping_private.json').write_text(json.dumps(mapping,indent=2)+'\n')
    (args.output/'rubric.json').write_text(json.dumps(rubric,indent=2)+'\n')
    (args.output/'manifest.json').write_text(json.dumps({'counts':counts,
        'rubric_sha256':hashlib.sha256(args.rubric.read_bytes()).hexdigest(),
        'prepared_rubric_sha256':hashlib.sha256((args.output/'rubric.json').read_bytes()).hexdigest(),
        'results_sha256':hashlib.sha256((args.run/'results.json').read_bytes()).hexdigest(),
        'packets_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.glob('review_*.json')},
        'scope':'View labels masked; prepared event condition may be visible. All packets stay local.'},indent=2)+'\n')
    print(json.dumps(counts))


if __name__=='__main__':
    main()

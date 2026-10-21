"""Describe all four finished P25 traces without hidden truth or model reasoning.

Task-specific analyst checks, not a proposed runtime verifier. Multiple export
writes and non-JSON observations are retained rather than silently discarded.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

from analyze_p18_public_evidence import args_of, body, recorded_operations, sha


def sent_rows(spans,events):
    sent={e['span_id'] for e in events if e['api_request_sent']}
    return [dict(id=sid,name=s['action']['name'],args=args_of(s),data=body(s))
            for sid,s in spans.items() if sid in sent]


def compare_csv(content, metadata, observed_ids):
    out=dict(observed_union_ids=len(observed_ids),known_metadata_ids=len(observed_ids & set(metadata)),
             observed_ids_without_metadata=len(observed_ids-set(metadata)))
    if not isinstance(content,str): return dict(out,status='content_not_text')
    try:
        reader=csv.DictReader(io.StringIO(content),strict=True)
        if reader.fieldnames!=['Title','Artists']:
            return dict(out,status='different_csv_header',header_columns=len(reader.fieldnames or []))
        rows=list(reader)
    except csv.Error: return dict(out,status='csv_parse_error')
    if any(set(r)!={'Title','Artists'} or None in r.values() for r in rows):
        return dict(out,status='malformed_csv_rows',rows=len(rows))
    expected={metadata[i] for i in observed_ids & set(metadata)}
    actual=[(r['Title'],r['Artists']) for r in rows]
    return dict(out,status='compared_to_observed_metadata',rows=len(rows),unique_pairs=len(set(actual)),
        duplicate_rows=len(actual)-len(set(actual)),known_unique_pairs=len(expected),
        matching_pairs=len(expected & set(actual)),missing_known_pairs=len(expected-set(actual)),
        unmatched_pairs=len(set(actual)-expected),
        all_observed_ids_have_metadata=not (observed_ids-set(metadata)))


def export_counts(rows):
    sets={k:set() for k in ('song','album','playlist')};pages={k:[] for k in sets}
    metadata={};writes=[];rereads=[];unclassified=Counter()
    for r in rows:
        name,value=r['name'],r['data']
        if name in {f'spotify__show_{k}_library' for k in sets}:
            kind=name.removeprefix('spotify__show_').removesuffix('_library')
            if not isinstance(value,list): unclassified[name]+=1;continue
            pages[kind].append(len(value))
            for item in value:
                ids=[item.get('song_id')] if kind=='song' else item.get('song_ids',[])
                if not isinstance(ids,list) or any(type(i)is not int or i<=0 for i in ids):
                    unclassified[name]+=1;continue
                sets[kind].update(ids)
                if kind=='song' and 'title' in item and isinstance(item.get('artists'),list):
                    metadata[item['song_id']]=(item['title'],'|'.join(a['name'] for a in item['artists']))
        elif name=='spotify__show_song':
            if (isinstance(value,dict) and type(value.get('song_id'))is int
                    and isinstance(value.get('title'),str) and isinstance(value.get('artists'),list)):
                metadata[value['song_id']]=(value['title'],'|'.join(a['name'] for a in value['artists']))
            else: unclassified[name]+=1
        elif name in ('file_system__create_file','file_system__update_file'):
            content=r['args'].get('content');observed=set.union(*sets.values())
            writes.append(dict(span_id=r['id'],api=name,
                json_message_receipt=isinstance(value,dict) and 'message'in value,
                content_sha256=hashlib.sha256(content.encode()).hexdigest() if isinstance(content,str) else None,
                **compare_csv(content,metadata,observed)))
        elif name=='file_system__show_file':
            if isinstance(value,dict) and isinstance(value.get('content'),str):
                content_hash=hashlib.sha256(value['content'].encode()).hexdigest()
                rereads.append(dict(span_id=r['id'],same_content_as_prior_export_spans=[w['span_id']
                    for w in writes if w['content_sha256']==content_hash]))
            else: unclassified[name]+=1
    return dict(source_unique_id_counts={k:len(v) for k,v in sets.items()},page_counts=pages,
        observed_union_ids=len(set.union(*sets.values())),observed_metadata_ids=len(metadata),
        writes=writes,rereads=rereads,unclassified_observations=dict(unclassified),
        scope='Observed union and exact title/artist strings, not hidden population. Every export attempt '
              'is retained; identical reread content alone is not proof of target-path identity.')


def photos(rows):
    aliases={};metadata=set();moves=[];snapshots=[];unclassified=Counter()
    for r in rows:
        name,value=r['name'],r['data']
        if name=='file_system__show_directory':
            if isinstance(value,list) and all(isinstance(x,str) for x in value):
                snapshots.append((r['id'],set(value)))
            else: unclassified[name]+=1
        elif name=='file_system__show_file':
            if isinstance(value,dict) and isinstance(value.get('path'),str):
                metadata.add(value['path']);aliases[r['args']['file_path']]=value['path']
            else: unclassified[name]+=1
        elif name=='file_system__move_file':
            path=r['args']['source_file_path']
            moves.append(dict(canonical=aliases.get(path,path),receipt=isinstance(value,dict) and 'message'in value))
    moved={m['canonical'] for m in moves if m['receipt']}
    return dict(directory_snapshots=[dict(span_id=s,listed_paths=len(paths),
                    paths_with_metadata=len(paths & metadata),paths_with_move_receipt=len(paths & moved))
                    for s,paths in snapshots],unique_metadata_paths=len(metadata),
        move_requests=len(moves),move_requests_with_json_message=sum(m['receipt'] for m in moves),
        unique_moved_source_paths=len(moved),read_paths_without_move_receipt=len(metadata-moved),
        move_sources_without_metadata=len(moved-metadata),unclassified_observations=dict(unclassified),
        scope='Each listing is kept separately because it may refer to a different directory or time. '
              'Receipts do not by themselves establish destination correctness or a lower API bound.')


def analyze(storage,output):
    batch=storage/'records/context_pilot/P25_batch_v01/status.json'
    if json.loads(batch.read_text())['status']!='complete':
        raise ValueError('all four tasks must finish before diagnosis')
    if output.exists(): raise FileExistsError('preserve previous diagnosis')
    findings=[]
    for n in range(1,5):
        rid=f'P25_{n:02d}_GUIDED';p=storage/'records/context_pilot'/rid
        spans=json.loads((p/'spans.json').read_text());events=json.loads((p/'events.json').read_text())
        rows=sent_rows(spans,events)
        result=dict(run_id=rid,**recorded_operations(spans,events),
            completion_answer_supplied=[r['args'].get('answer') is not None for r in rows
                                       if r['name']=='supervisor__complete_task'],
            source_sha256={f:sha(p/f) for f in ('public_task.json','spans.json','events.json','summary.json')})
        if n==1: result['photo_counts']=photos(rows)
        if n==4: result['song_coverage']=export_counts(rows)
        findings.append(result)
    report=dict(phase='P25',trials=findings,all_four_read=True,script_sha256=sha(Path(__file__)),
        model_calls=0,environment_calls=0,evaluator_contents_read=False,
        scope='Post-hoc analyst checks. No automatic verifier, private task state, or model reasoning.')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'trials':4,'model_calls':0,'environment_calls':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();analyze(a.storage_root,a.output)

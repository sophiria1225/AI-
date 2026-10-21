"""Download only pinned QA/corpus/BM25 assets, retaining partial failures.

No dataset parsing, decryption, model generation or evaluator access here.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import urllib.parse
import urllib.request


def asset_rows(manifest, kind):
    identifier = {'qa':'Tevatron/browsecomp-plus', 'corpus':'Tevatron/browsecomp-plus-corpus',
                  'bm25':'Tevatron/browsecomp-plus-indexes'}[kind]
    dataset = next(d for d in manifest['datasets'] if d['identifier']==identifier)
    selected = []
    for row in dataset['files']:
        name = row['path']
        if not (name.startswith('bm25/') if kind=='bm25' else name.endswith('.parquet')):
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise ValueError('invalid metadata path')
        lfs = row.get('lfs')
        expected = lfs['oid'] if lfs else row['oid']
        method = 'sha256' if lfs else 'git_blob_sha1'
        if len(expected) != (64 if lfs else 40) or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('invalid upstream digest')
        selected.append({'path':name,'size':row['size'],'digest_type':method,'expected_digest':expected,
                         'url':f"https://huggingface.co/datasets/{identifier}/resolve/{dataset['revision']}/"+
                               urllib.parse.quote(name,safe='/')})
    if not selected:
        raise ValueError('no pinned assets found')
    return dataset['revision'], selected


def digests(path, expected_size):
    total = 0; plain = hashlib.sha256()
    blob = hashlib.sha1(f'blob {expected_size}\0'.encode())
    with path.open('rb') as stream:
        while chunk := stream.read(1024*1024):
            total += len(chunk);plain.update(chunk);blob.update(chunk)
    return {'bytes':total,'sha256':plain.hexdigest(),'git_blob_sha1':blob.hexdigest()}


def verify(path, asset):
    result = digests(path,asset['size'])
    if result['bytes'] != asset['size'] or result[asset['digest_type']] != asset['expected_digest']:
        raise ValueError('asset size/hash mismatch')
    return result


def download(asset, folder):
    path = folder / asset['path'];path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        return {**verify(path,asset),'disposition':'already_verified'}
    partial = path.with_name(path.name+'.part')
    if partial.exists():
        raise FileExistsError('partial attempt retained; explicit recovery is required')
    request = urllib.request.Request(asset['url'],headers={'User-Agent':'AI-harness-pinned-download'})
    with urllib.request.urlopen(request,timeout=60) as response, partial.open('xb') as out:
        if response.status != 200:
            raise ValueError('full asset response required')
        length = response.headers.get('Content-Length')
        if length is not None and int(length) != asset['size']:
            raise ValueError('unexpected content length')
        received = 0
        while chunk := response.read(min(1024*1024,asset['size']-received+1)):
            received += len(chunk)
            if received > asset['size']:
                raise ValueError('asset exceeds pinned size')
            out.write(chunk)
    result = verify(partial,asset)
    partial.replace(path)
    return {**result,'disposition':'downloaded_and_verified'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--kind',choices=['qa','corpus','bm25'],required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--completed-batch',type=Path,required=True)
    args=parser.parse_args()
    if json.loads((args.completed_batch/'status.json').read_text())['status'] != 'complete':
        raise ValueError('do not overlap large downloads with the running timed cohort')
    if args.report.exists():
        raise FileExistsError('keep earlier download attempt report')
    revision, assets = asset_rows(json.loads(args.manifest.read_text()),args.kind)
    args.destination.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(args.destination).free < sum(a['size'] for a in assets)+5*1024**3:
        raise ValueError('insufficient space with 5GiB working margin')
    result={'status':'running','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'kind':args.kind,'revision':revision,'files':[],
            'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            'model_calls':0,'data_rows_parsed':0,'evaluator_accessed':False}
    def save():
        args.report.parent.mkdir(parents=True,exist_ok=True)
        tmp=args.report.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(args.report)
    save()
    try:
        for asset in assets:
            result['active_path']=asset['path'];save()
            row=download(asset,args.destination)
            result['files'].append({**asset,**row});save()
            print(json.dumps({'path':asset['path'],'bytes':row['bytes'],'disposition':row['disposition']}),flush=True)
        result.update(status='complete',active_path=None)
    except Exception as error:
        result.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        result['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()

"""Two-stage column projection: IDs first, then selected questions without labels."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path

from download_browsecomp_assets import verify
from select_browsecomp_development import choose


def public_canary(source, expected_hash):
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('upstream decryption source changed')
    values = [node.value.value for node in ast.parse(source.read_text()).body
              if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant)
              and isinstance(node.value.value,str)
              and any(isinstance(n,ast.Name) and n.id=='DEFAULT_CANARY' for n in node.targets)]
    if len(values)!=1:raise ValueError('expected one literal public benchmark canary')
    return values[0]


def decrypt_question(value, canary):
    # Same public SHA-256/XOR obfuscation as the pinned upstream decrypt_dataset.py.
    # The upstream file is parsed, never imported or executed.
    data=base64.b64decode(value,validate=True);key=hashlib.sha256(canary.encode()).digest()
    return bytes(byte^key[i%len(key)] for i,byte in enumerate(data)).decode('utf-8')


def selected_questions(rows, selected, canary):
    wanted=set(selected)
    if not wanted or len(wanted)!=len(selected):raise ValueError('duplicate or empty selection')
    result={}
    for row in rows:
        if set(row)!={'query_id','query'}:raise ValueError('executor projection contains unexpected fields')
        key=row['query_id']
        if key not in wanted:continue
        if key in result:raise ValueError('duplicate selected query')
        text=decrypt_question(row['query'],canary)
        if not text.strip():raise ValueError('empty question')
        result[key]={'query_id':key,'query':text}
    if set(result)!=wanted:raise ValueError('selected query missing')
    return [result[key] for key in selected]


def column_rows(folder, report, columns):
    import pyarrow.parquet as pq
    if report['status']!='complete' or report['kind']!='qa':
        raise ValueError('requires a complete pinned QA download')
    for asset in report['files']:
        path=folder/asset['path'];verify(path,asset)
        parquet=pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=32,columns=columns):
            yield from batch.to_pylist()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['ids','questions'],required=True)
    parser.add_argument('--source-folder',type=Path,required=True)
    parser.add_argument('--download-report',type=Path,required=True)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--selection',type=Path)
    parser.add_argument('--ids',type=Path,help='Original ID-only JSONL, required before question projection')
    parser.add_argument('--decryption-source',type=Path)
    parser.add_argument('--preflight-report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    policy=json.loads(args.policy.read_text());download=json.loads(args.download_report.read_text())
    if download['revision']!=policy['revision']:raise ValueError('wrong QA revision')
    if args.output.exists() or args.report.exists():raise FileExistsError('keep previous projection')
    if args.stage=='ids':
        rows=list(column_rows(args.source_folder,download,['query_id']))
        if len(rows)!=policy['expected_unique_ids'] or len({r['query_id'] for r in rows})!=len(rows):
            raise ValueError('ID count differs from precommitted policy')
    else:
        if not all((args.selection,args.ids,args.decryption_source,args.preflight_report)):
            raise ValueError('selection and pinned decryption source are required')
        selection=json.loads(args.selection.read_text())
        if (selection['source_revision']!=policy['revision'] or
                selection['policy_sha256']!=hashlib.sha256(args.policy.read_bytes()).hexdigest() or
                len(selection['selected_ids'])!=policy['development_count']):
            raise ValueError('selection differs from the fixed policy')
        if selection['id_source_sha256']!=hashlib.sha256(args.ids.read_bytes()).hexdigest():
            raise ValueError('ID-only source changed after selection')
        fixed=choose([json.loads(line) for line in args.ids.read_text().splitlines() if line.strip()],
                     policy,download['revision'])
        if fixed['selected_ids']!=selection['selected_ids']:
            raise ValueError('selected IDs were replaced after applying the policy')
        source=next(s for s in json.loads(args.preflight_report.read_text())['sources']
                    if s['local_name']=='scripts_build_index__decrypt_dataset.py')
        canary=public_canary(args.decryption_source,source['sha256'])
        rows=selected_questions(column_rows(args.source_folder,download,['query_id','query']),
                                selection['selected_ids'],canary)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as out:
        args.output.chmod(0o600)
        for row in rows:out.write(json.dumps(row,ensure_ascii=False)+'\n')
    result={'stage':args.stage,'rows_written':len(rows),'output_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
            'download_report_sha256':hashlib.sha256(args.download_report.read_bytes()).hexdigest(),
            'policy_sha256':hashlib.sha256(args.policy.read_bytes()).hexdigest(),
            'selection_sha256':hashlib.sha256(args.selection.read_bytes()).hexdigest() if args.selection else None,
            'source_revision':download['revision'],'model_calls':0,'answer_or_label_columns_read':False,
            'decrypted_queries':len(rows) if args.stage=='questions' else 0,
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

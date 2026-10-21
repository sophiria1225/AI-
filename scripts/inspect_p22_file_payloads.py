"""Inspect saved public response shapes only; do not infer PDF decoding need."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('preserve the previous report')
    path=args.storage_root/'records/context_pilot/P22_03_ROLES/spans.json'
    rows=[]
    for sid,span in json.loads(path.read_text()).items():
        action=span.get('action') or {}
        if action.get('name')!='file_system__show_file':
            continue
        try:
            data=json.loads(span.get('observation',{}).get('observation',''))
        except (ValueError,TypeError):
            rows.append(dict(span_id=sid,shape='non_json_response'))
            continue
        if not isinstance(data,dict) or not isinstance(data.get('content'),str):
            rows.append(dict(span_id=sid,shape='no_string_content'))
            continue
        text=data['content']
        rows.append(dict(span_id=sid,shape='string_content',characters=len(text),
            suffix=PurePosixPath(data.get('path','')).suffix,pdf_magic=text.startswith('%PDF'),
            has_stream='stream' in text,has_end_marker='%%EOF' in text,
            contains_binary_label='binary' in text.lower(),
            currency_pattern=bool(re.search(r'\$\s*[0-9]',text))))
    result=dict(run_id='P22_03_ROLES',rows=rows,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        model_calls=0,environment_calls=0,hidden_evaluation_read=False,
        scope='Response occurrences, not unique files or a task solution. A filename is not evidence of decoded binary content.')
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(responses=len(rows),string_responses=sum(r['shape']=='string_content' for r in rows),
        with_currency_pattern=sum(r.get('currency_pattern',False) for r in rows),
        with_binary_label=sum(r.get('contains_binary_label',False) for r in rows),
        with_pdf_magic=sum(r.get('pdf_magic',False) for r in rows))))


if __name__=='__main__':
    main()

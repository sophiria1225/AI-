"""Export all two P107 slots, all calls and program costs; no reexecution."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root):
    source=root/'reports/P107_comparison.json'
    audit=json.loads(source.read_text())
    if len(audit['rows'])!=2:raise ValueError('retain_both_planned_slots')
    target=root/'materials/20261025_p107_results';target.mkdir(parents=True,exist_ok=False)
    tables={'all_2_conditions.csv':audit['rows'],
        'all_model_calls.csv':[dict(policy=r['read_view_policy'],**c) for r in audit['rows'] for c in r.get('request_checks',[])],
        'all_programs.csv':[dict(policy=r['read_view_policy'],**c) for r in audit['rows'] for c in r.get('program_costs',[])]}
    for name,rows in tables.items():
        fields=list(dict.fromkeys(k for row in rows for k in row if k not in ('request_checks','program_costs')))
        with (target/name).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
            for row in rows:
                writer.writerow({k:json.dumps(v,sort_keys=True,ensure_ascii=False) if isinstance(v,(dict,list)) else v
                                 for k,v in row.items()})
    summary={k:v for k,v in audit.items() if k!='rows'}
    with (target/'summary.json').open('x') as stream:json.dump(summary,stream,ensure_ascii=False,indent=2);stream.write('\n')
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),builder_sha256=sha(Path(__file__)),
        audit_sha256=sha(source),public_artifact_sha256={p.name:sha(p) for p in target.iterdir() if p.is_file()},
        model_generations=0,environment_API_requests=0,programs_executed=0,evaluations=0,manuscript_changed=False)
    with (target/'build_manifest.json').open('x') as stream:json.dump(manifest,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(conditions=2,model_call_rows=len(tables['all_model_calls.csv']),
        program_rows=len(tables['all_programs.csv']),audit_errors=len(audit['audit_errors']))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True)
    build(p.parse_args().repo_root.resolve())

"""Preserve the first layout attempt and allow URL digit breaks in a fresh edition."""
from datetime import datetime, timezone
import json

from build_observed_control_draft import replace_once
from run_handoff_factors import ROOT, read, sha

PARENT='papers/202610_letter/execution_evidence_controls_v01'
FOLDER='papers/202610_letter/execution_evidence_controls_v02'


def build():
    parent=ROOT/PARENT;target=ROOT/FOLDER
    if target.exists():raise FileExistsError('preserve_formatted_control_edition')
    old=read(parent/'build_manifest.json');sources=dict(old['source_sha256'])
    for name,expected in old['generated_sha256'].items():sources[PARENT+'/'+name]=expected
    for name in ('build_manifest.json','layout_failed.json','draft_layout_failed.pdf','README.md'):
        sources[PARENT+'/'+name]=sha(parent/name)
    sources['scripts/format_closed_control_evidence_draft.py']=sha(ROOT/'scripts/format_closed_control_evidence_draft.py')
    for name,expected in sources.items():
        if sha(ROOT/name)!=expected:raise ValueError('bound_source_changed:'+name)
    generated={n:(parent/n).read_text() for n in old['generated_sha256']}
    text=generated['draft.tex'].replace(PARENT+'/',FOLDER+'/')
    text=replace_once(text,r'\usepackage{url}',r'''\usepackage{url}
\expandafter\def\expandafter\UrlBreaks\expandafter{\UrlBreaks\do\0\do\1\do\2\do\3\do\4\do\5\do\6\do\7\do\8\do\9}''')
    generated['draft.tex']=text
    target.mkdir()
    for name,value in generated.items():(target/name).write_text(value)
    manifest={**old,'generated_at':datetime.now(timezone.utc).isoformat(),'source_sha256':sources,
        'generated_sha256':{n:sha(target/n) for n in generated},'parent_draft':PARENT,
        'presentation_change_only':True,'layout_change':'Allow digit line breaks inside bibliography URLs.',
        'all_numerical_and_conclusion_files_byte_unchanged':[n for n in generated if n!='draft.tex'],
        'visual_reviewed':False,'submission_ready':False}
    (target/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(dict(folder=FOLDER,numerical_sections_changed=False,source_bindings=len(sources)))


if __name__=='__main__':build()

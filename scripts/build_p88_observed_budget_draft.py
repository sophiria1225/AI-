"""Refine the closed P88 draft's generic missing-data wording, preserving it."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from build_whole_task_reasoning_budget_report import validated
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

BASE = 'papers/202610_letter/reasoning_budget_control'
TARGET = 'papers/202610_letter/reasoning_budget_control_observed'


def replace_once(text, old, new):
    if text.count(old)!=1:raise ValueError('expected_original_wording_changed')
    return text.replace(old,new)


def build(root):
    _,report,_,_,_=validated(root)
    if (len(report['rows'])!=8 or any(r['record_status']!='evaluated' for r in report['rows'])
            or sum(r['unknown_usage_calls'] for r in report['rows'])!=1
            or report['development_gate_met'] is not False):
        raise ValueError('this_refinement_requires_observed_P88_closure')
    base=root/BASE;target=root/TARGET
    if target.exists():raise FileExistsError('preserve_editorial_derivation')
    manifest=read(base/'build_manifest.json')
    for name,expected in manifest['generated_sha256'].items():
        if sha(base/name)!=expected:raise ValueError('original_draft_changed')
    sources=deepcopy(manifest['source_sha256'])
    sources.update({BASE+'/'+name:sha(base/name) for name in
                    [*manifest['generated_sha256'],'build_manifest.json','layout.json','draft.pdf']})
    sources['scripts/build_p88_observed_budget_draft.py']=sha(Path(__file__))
    output={name:(base/name).read_text() for name in manifest['generated_sha256']}
    output['draft.tex']=replace_once(output['draft.tex'],
        '使用量の欠測または未評価が残り, 全仕事費用差は確定できなかった.',
        '全条件を評価したが１生成の使用量が不明で, 全仕事費用差は確定できなかった.')
    output['draft.tex']=replace_once(output['draft.tex'],
        'Missing usage or evaluations prevented identifying the complete cohort cost difference.',
        'All conditions were evaluated, but missing usage for one generation prevented identifying the complete cost difference.')
    output['draft.tex']=output['draft.tex'].replace(BASE+'/',TARGET+'/')
    output['whole_task.tex']=replace_once(output['whole_task.tex'],
        '欠測または未評価があるため，固定した全件比較の費用差は未確定とする．',
        '成功した３課題では，各対の論理token差は０であった．全８条件を評価したが，Uの書出し１生成の使用量が不明であり，固定した全件比較の費用差は未確定とする．')
    output['whole_task.tex']=replace_once(output['whole_task.tex'],
        '未達の費用も残し，成功部分のみの減少を全体の改善としない．',
        '表２は費用欠測時に全群の寄与集計を保留する固定規則による．未達の費用も残し，成功部分のみの減少を全体の改善としない．')
    output['conclusion.tex']=replace_once(output['conclusion.tex'],
        '使用量の欠測または未評価・未実行を含む全８枠を保持した．',
        '全８条件を評価し，使用量不明の１生成も含めて原記録を保持した．')
    ja=output['draft.tex'].split('\\textbf{あらまし案}\\quad\n',1)[1].split('\n\n',1)[0]
    en=output['draft.tex'].split('\\textbf{Summary draft}\\quad ',1)[1].split('\n',1)[0]
    if len(ja)>120 or len(en.split())>50 or any(c in ja for c in ('。','・')):
        raise ValueError('refined_abstract_limits')
    target.mkdir(parents=True,exist_ok=False)
    for name,content in output.items():(target/name).write_text(content)
    for key in ('pdf_sha256','renderer_sha256','pages','body_pages'):manifest.pop(key,None)
    manifest.update(generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=sources,
        generated_sha256={name:sha(target/name) for name in output},visual_reviewed=False,
        editorial_source=BASE,editorial_reason='All eight conditions were evaluated; only one generation has unknown usage. Original generic wording retained in source draft.',
        experiment_or_audit_repeated=False,additional_generations=0,additional_api_requests=0,additional_evaluations=0)
    write_json(target/'build_manifest.json',manifest)
    print(dict(folder=TARGET,ja_characters=len(ja),en_words=len(en.split()),original_preserved=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,default=ROOT)
    build(parser.parse_args().repo_root.resolve())

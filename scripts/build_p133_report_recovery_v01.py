"""P133 data-only reporting recovery; original execution and failed report attempt stay fixed.

Reuse the frozen pure row/accounting functions. Extend path validation only for
seven exact, hash-bound public dependencies already in the original plan.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from build_checkpoint_payback_summary import (
    AUDIT, SESSION, BUILDER as ORIGINAL_BUILDER, AUDITOR, INSPECTOR, HELPER,
    FIELDS, MODES, SEEDS, README as ORIGINAL_README, SESSION_MEASURES,
    public_row, aggregate, comparison_groups, number, valid_hash, require,
    publish_directory, sha, PLAN, ACTIVATION, PREFLIGHT, cell_id, run_order, summarize,
)

ROOT = Path(__file__).resolve().parents[1]
BUILDER = 'scripts/build_p133_report_recovery_v01.py'
INPUTS = 'reports/P133_reporting_recovery_inputs_v01.json'
TARGET = 'materials/20261027_p133_results_recovery_v01'
ORIGINAL_HEAD = '66d9eb71a1e6b8ee10b377be3bf52dca82d06cca'
ORIGINAL_PLAN_SHA = '357c59a73ed9637e9171d6729f8f4210533fef90d598ec667fa1d7154d09d986'
EXTRA_PUBLIC_SOURCES = {
    'materials/20261024_p97_results/visual_review.json': 'e59a0cb665fd1765f8eddd2bc430bf5bd5ec56621c835760a8f1bf7e1f3d26ca',
    'materials/20261024_p98_results/summary.json': 'f063e19ef5795ea883eba02eb7bcdd56d8719088fc532a932cd1cd2ca9612f3e',
    'materials/20261025_p112_preparation/README.md': '6c150ef4107099fc3600e8cd4b16440045b94bfa4a55d378ee810e5e100edfb7',
    'materials/20261025_p115_preparation/README.md': 'a066d5164db78b7fe796d9e4caf15c46a57431cd509a863251e8ab697ff18901',
    'materials/20261025_p122_results/build_manifest.json': 'd3b132935f4b072a6dda26c2f4585478725265e94a7f1a8dc9aeb2629f3305b2',
    'materials/20261025_p122_results/summary.json': '5109c2a33711f3c78a04a8a31d740f09dcbc8adc4273fdf951cd4067701e8a64',
    'papers/202610_letter/templates/tool_choice_letter.tex': '3d6587f865f4030b9ab39173fe65886468f7b9a83d1603d93871d01cf700aa19',
}


def public_path(root, name):
    require(type(name) is str and not Path(name).is_absolute()
            and '..' not in Path(name).parts, 'repository_relative_source_required')
    require(name.split('/')[0] in ('scripts', 'tests', 'configs', 'docs', 'reports')
            or name in EXTRA_PUBLIC_SOURCES, 'exact_public_recovery_source_required')
    p = root / name
    require(p.resolve().is_relative_to(root), 'public_source_escapes_repository')
    if name in EXTRA_PUBLIC_SOURCES:
        require(sha(p) == EXTRA_PUBLIC_SOURCES[name], 'additional_frozen_source_changed')
    return p


def build(root):
    root = Path(root).resolve()
    require(root == ROOT.resolve(), 'executing_recovery_repository_must_match')
    target = root / TARGET
    require(not target.exists() and not target.is_symlink(), 'preserve_recovery_directory')
    source_hashes = {}

    def load(name):
        p = public_path(root, name); source_hashes[name] = sha(p)
        value = json.loads(p.read_text())
        require(type(value) is dict, 'public_record_object_required')
        return value

    require(sha(public_path(root, PLAN)) == ORIGINAL_PLAN_SHA, 'original_plan_bytes_required')
    plan, inputs = load(PLAN), load(INPUTS)
    require(inputs.get('phase') == 'P133_reporting_recovery_inputs'
        and inputs.get('original_head') == ORIGINAL_HEAD
        and inputs.get('original_plan_sha256') == ORIGINAL_PLAN_SHA
        and inputs.get('original_source_count') == 1459
        and inputs.get('completed_conditions') == 4
        and inputs.get('owned_processes_absent') is True
        and inputs.get('original_attempts_preserved') is True
        and inputs.get('original_audit_exit_code') == 0
        and inputs.get('original_session_exit_code') == 0
        and inputs.get('original_report_exit_code') == 1, 'original_closed_failure_lineage_required')
    require(all(type(inputs.get(k)) is int and inputs[k] == 0 for k in
        ('additional_model_calls','additional_API_requests','additional_evaluations','additional_tokenizer_calls')),
        'data_only_recovery_required')
    for name, expected in inputs['source_sha256'].items():
        require(valid_hash(expected) and sha(public_path(root, name)) == expected, 'copied_original_artifact_changed')
        source_hashes[name] = expected
    stages = {kind: load(f'reports/P133_{kind}_once_end.json') for kind in ('audit','session','report')}
    require(all(stages[k]['stage'] == k and type(stages[k]['exit_code']) is int
                and stages[k]['exit_code'] == expected for k,expected in [('audit',0),('session',0),('report',1)]),
            'original_stage_outcomes_preserved')
    require(sha(root/'reports/P133_report_once_end.json') == inputs['original_failure_sha256'], 'original_failure_binding')
    report, session, activation = load(AUDIT), load(SESSION), load(ACTIVATION)
    for name in (PREFLIGHT, ORIGINAL_BUILDER, AUDITOR, INSPECTOR, HELPER, BUILDER):
        source_hashes[name] = sha(public_path(root, name))
    require(report.get('phase') == session.get('phase') == plan.get('experiment') == 'P133'
        and report.get('batch_status') == 'complete' and report.get('owned_processes_absent') is True
        and session.get('owned_processes_absent') is True and session.get('status') == 'stopped', 'closed_P133_required')
    require(session.get('audit_source_sha256') == source_hashes[AUDIT]
        and report.get('plan_sha256') == source_hashes[PLAN]
        and report.get('activation_sha256') == source_hashes[ACTIVATION]
        and report.get('auditor_sha256') == source_hashes[AUDITOR]
        and session.get('inspector_sha256') == source_hashes[INSPECTOR]
        and activation.get('preflight_sha256') == source_hashes[PREFLIGHT]
        and session.get('pipeline_source_sha256') == report.get('pipeline_status_sha256')
        and session.get('source_sha256') == report.get('server_final_sha256'), 'original_report_session_binding')
    frozen = activation.get('source_hashes')
    require(type(frozen) is dict and all(n in frozen for n in (ORIGINAL_BUILDER,AUDITOR,INSPECTOR,HELPER)), 'original_frozen_sources_required')
    require(len(plan['source_sha256']) == 1459 and all(plan['source_sha256'].get(n) == h for n,h in EXTRA_PUBLIC_SOURCES.items()), 'original_seven_additional_bindings_required')
    for mapping in (frozen, plan['source_sha256']):
        for name, expected in mapping.items():
            require(valid_hash(expected) and sha(public_path(root,name)) == expected, 'original_frozen_source_changed')
    tasks = plan['known_tasks']
    require(len(tasks) == 1 and plan['payback_modes'] == list(MODES) and plan['model_seeds'] == list(SEEDS), 'fixed_original_scope_required')
    expected = [(cell_id(rep,n,mode),tasks[n-1]['task_id'],mode,rep,SEEDS[rep-1]) for rep,n,mode in run_order()]
    raw = report['rows']
    require(type(raw) is list and [(r['run_id'],r['task_id'],r['payback_mode'],r['replication'],r['model_seed']) for r in raw] == expected, 'all_four_ordered_rows_required')
    errors = report['audit_errors']; require(type(errors) is list, 'audit_errors_preserved')
    criteria = summarize(raw,errors)
    require(all(report.get(k) == v for k,v in criteria.items()), 'original_criteria_recomputed')
    rows = [public_row(r) for r in raw]
    server = {}
    for key in SESSION_MEASURES:
        value = session.get(key); require(value is None or number(value), 'finite_server_measurement_required'); server[key] = value
    summary = dict(phase='P133', all_conditions=aggregate(rows), by_policy={m:aggregate([r for r in rows if r['payback_mode']==m]) for m in MODES},
        primary_baseline=MODES[0],treatment=MODES[1],comparison_costs=comparison_groups(rows,criteria),
        by_replication={str(rep):dict(model_seed=SEEDS[rep-1],all_conditions=aggregate([r for r in rows if r['replication']==rep]),
            by_policy={m:aggregate([r for r in rows if r['replication']==rep and r['payback_mode']==m]) for m in MODES},
            comparison_costs=comparison_groups(rows,criteria,rep)) for rep in (1,2)},
        independent_tasks=1,repetitions=2,model_seeds=list(SEEDS),audited_criteria=criteria,audit_error_count=len(errors),
        conditions=rows,server_measures=server,unknown_usage_is_not_zero=True,
        cost_scope='All model roles, failed work, control, recovery and summary costs remain in the whole-job ledger.',
        time_scope='Control and summary time overlap work; work and evaluation overlap server time. Do not add them.',
        forecast_is_guarantee=False,novel_method_claim=False,general_quality_preservation_claim=False,timing_superiority_claim=False,
        manuscript_changed=False,private_task_values_or_program_text_published=False,
        reporting_recovery=dict(version=1,original_experiment_reexecuted=False,original_reporting_failure_preserved=True,
            original_head=ORIGINAL_HEAD,original_plan_sha256=ORIGINAL_PLAN_SHA,original_failure_sha256=inputs['original_failure_sha256'],
            correction='Seven pre-existing exact public source paths are validated by original hashes; accounting and criteria functions remain frozen.'))
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.p133-recovery-',dir=target.parent))
    try:
        with (staging/'conditions.csv').open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
        (staging/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        (staging/'README.md').write_text(ORIGINAL_README+'\n## Reporting recovery v01\n\n原実験・監査・server集計は再実行せず、旧report失敗を保持する。旧path検査が拒否した、元planにhash固定済みのmaterials6件とpapers1件のみを追加検証対象にした別集計である。元run/prep/source/計画/失敗markerは変更しない。\n')
        manifest=dict(phase='P133',reporting_attempt='recovery_v01',source_sha256=source_hashes,
            activation_bound_source_count=len(frozen),activation_source_mapping_sha256=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest(),
            original_head=ORIGINAL_HEAD,original_plan_sha256=ORIGINAL_PLAN_SHA,original_failure_sha256=inputs['original_failure_sha256'],
            original_builder_sha256=source_hashes[ORIGINAL_BUILDER],actual_recovery_builder_sha256=source_hashes[BUILDER],
            additional_exact_public_source_sha256=EXTRA_PUBLIC_SOURCES,
            artifact_sha256={p.name:sha(p)for p in sorted(staging.iterdir())},new_model_calls=0,new_API_requests=0,new_tokenizer_calls=0,new_evaluations=0,
            original_auditor_reexecuted=False,original_experiment_reexecuted=False,atomic_exclusive_directory_publication=True)
        (staging/'build_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
        require(all(sha(public_path(root,n))==h for n,h in {**frozen,**source_hashes}.items()), 'source_changed_during_recovery')
        publish_directory(staging,target)
    finally:
        if staging.exists():shutil.rmtree(staging)
    return dict(phase='P133',reporting_attempt='recovery_v01',planned_conditions=4,development_gate_met=criteria['development_gate_met'],output=TARGET)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,default=ROOT)
    print(json.dumps(build(p.parse_args().repo_root),ensure_ascii=False))

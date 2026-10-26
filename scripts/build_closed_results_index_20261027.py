"""Data-only index of already published closed cohorts; never opens raw records.

This is a navigation/aggregation artifact, not a new experiment or audit of the
underlying agent. All inputs are explicitly named public repository files.
"""
import argparse
import csv
from io import StringIO
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = 'materials/20261027_closed_results_index'
TASKS = {'34d9492_1': 'Photo', '3c13f5a_1': 'Expenses',
         '60d0b5b_1': 'Refund', '6104387_1': 'CSV'}
SPECS = {
    'P123': ('checkpoint_policy', ('single_checkpoint', 'rolling_separate', 'rolling_inline'),
             '20261025_p123_results', 'docs/P123_findings.md',
             'P123_closed_independent_review_20261026.json', 'P123_whole_task_rolling_checkpoint_v01.json',
             'checkpoint_installations', 'checkpoint採用回数'),
    'P125': ('projection_policy', ('eager_cached', 'automatic_projection_cached'),
             '20261026_p125_results', 'docs/P125_findings.md',
             'P125_closed_independent_review_20261026_v02.json', 'P125_whole_task_projection_v01.json',
             'projection_hits', '自動projection partial hit'),
    'P127': ('projection_policy', ('explicit_joined_fields', 'automatic_region_joined_fields'),
             '20261026_p127_results', 'docs/experiments/P127_findings.md',
             'P127_closed_independent_audit_20261026.json', 'P127_whole_task_region_projection_v01.json',
             'projection_hits', '自動region partial hit'),
    'P128': ('receipt_mode', ('full', 'disclose'), '20261026_p128_results',
             'docs/experiments/P128_findings.md', 'P128_closed_independent_audit_20261026.json',
             'P128_whole_task_receipt_disclosure_v01.json', 'receipt_disclosures',
             '有料入力に含まれた固有disclosed turn数'),
    'P129': ('grounding_mode', ('off', 'feedback', 'repair'), '20261026_p129_results',
             'docs/experiments/P129_findings.md', 'P129_closed_independent_audit_20261026.json',
             'P129_whole_task_output_grounding_v01.json', 'grounding_repairs', '保存根拠まで確認した修復数'),
    'P132': ('inventory_mode', ('off', 'checkpoint_inventory'), '20261027_p132_results',
             'docs/experiments/P132_findings.md', 'P132_closed_independent_audit_20261027.json',
             'P132_whole_task_checkpoint_inventory_resumption_v01.json',
             'inventory_notice_actor_calls', 'inventory実actor提示回数'),
    'P133': ('payback_mode', ('rolling_separate', 'empirical_payback'),
             '20261027_p133_results_recovery_v01', 'docs/experiments/P133_findings.md',
             'P133_closed_independent_audit_20261027_recovery_v01.json',
             'P133_whole_task_checkpoint_payback_v01.json', 'payback_rejections', '予測に基づく実focus拒否回数'),
}
METRICS = ('checkpoint_installations', 'projection_hits', 'receipt_disclosures',
           'receipt_disclosed_turns', 'grounding_feedback_blocks', 'grounding_repair_attempts',
           'grounding_sent_repairs', 'grounding_repairs', 'inventory_notice_actor_calls',
           'inventory_captures', 'payback_rejections', 'payback_shadow_rejections',
           'ordinary_complete_cache_hits', 'explicit_field_requests', 'explicit_field_partial_hits')
PAIR_SPECS = {
    'P123': [('ordinary_anchor', 'single_checkpoint', 'rolling_separate'),
             ('inline_vs_single', 'single_checkpoint', 'rolling_inline'),
             ('inline_vs_strong_ordinary', 'rolling_separate', 'rolling_inline')],
    'P125': [('primary', 'eager_cached', 'automatic_projection_cached')],
    'P127': [('primary', 'explicit_joined_fields', 'automatic_region_joined_fields')],
    'P128': [('primary', 'full', 'disclose')],
    'P129': [('primary', 'feedback', 'repair'), ('auxiliary', 'off', 'repair')],
    'P132': [('primary', 'off', 'checkpoint_inventory')],
    'P133': [('primary', 'rolling_separate', 'empirical_payback')],
}


def require(test, message):
    if not test:
        raise ValueError(message)


def integer(value):
    require(type(value) is int and value >= 0, 'nonnegative exact integer required')
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def totals(rows):
    """Known subtotals remain available; an unknown call makes exact totals null."""
    known_input = sum(integer(r['known_input_tokens']) for r in rows)
    known_output = sum(integer(r['known_output_tokens']) for r in rows)
    unknown = sum(integer(r['unknown_usage_calls']) for r in rows)
    return dict(planned_conditions=len(rows), evaluated_conditions=sum(r['evaluated'] for r in rows),
                successful_conditions=sum(r['success'] is True for r in rows),
                known_input_tokens=known_input, known_output_tokens=known_output,
                known_token_subtotal=known_input + known_output, unknown_usage_calls=unknown,
                exact_total_tokens=known_input + known_output if rows and unknown == 0 else None,
                model_calls=sum(r['model_calls'] for r in rows),
                environment_api_requests=sum(r['environment_api_requests'] for r in rows))


def compare(rows, baseline, treatment):
    b = {(r['model_seed'], r['task']): r for r in rows if r['arm'] == baseline}
    a = {(r['model_seed'], r['task']): r for r in rows if r['arm'] == treatment}
    require(b and b.keys() == a.keys(), 'paired task/seed coverage')
    bt, at = totals(list(b.values())), totals(list(a.values()))
    common = [k for k in b if b[k]['success'] is True and a[k]['success'] is True]
    bc, ac = totals([b[k] for k in common]), totals([a[k] for k in common])
    exact = bt['exact_total_tokens'] is not None and at['exact_total_tokens'] is not None
    common_exact = bool(common) and bc['exact_total_tokens'] is not None and ac['exact_total_tokens'] is not None
    delta = at['exact_total_tokens'] - bt['exact_total_tokens'] if exact else None
    return dict(baseline=baseline, treatment=treatment, paired_conditions=len(b),
                success_losses=sum(b[k]['success'] is True and a[k]['success'] is False for k in b),
                success_gains=sum(b[k]['success'] is False and a[k]['success'] is True for k in b),
                baseline_exact_total_tokens=bt['exact_total_tokens'], treatment_exact_total_tokens=at['exact_total_tokens'],
                exact_total_delta_tokens=delta,
                exact_total_delta_percent=100 * delta / bt['exact_total_tokens'] if exact and bt['exact_total_tokens'] else None,
                common_success_pairs=len(common),
                common_baseline_exact_tokens=bc['exact_total_tokens'], common_treatment_exact_tokens=ac['exact_total_tokens'],
                descriptive_common_success_delta_tokens=ac['exact_total_tokens']-bc['exact_total_tokens'] if common_exact else None,
                descriptive_common_success_delta_percent=100*(ac['exact_total_tokens']-bc['exact_total_tokens'])/bc['exact_total_tokens'] if common_exact and bc['exact_total_tokens'] else None)


def build(root):
    root = Path(root).resolve()
    dependencies = {}

    def load(relative, *, text_only=False):
        p = root / relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts
                and p.resolve().is_relative_to(root), 'public relative dependency')
        raw = p.read_bytes(); dependencies[relative] = sha(raw)
        return raw.decode() if text_only else json.loads(raw)

    conditions, arms, arm_seeds, comparisons, phases = [], [], [], [], {}
    for phase, spec in SPECS.items():
        key, modes, directory, findings, audit_name, plan_name, metric, label = spec
        report_path = 'reports/' + phase + '_comparison.json'
        report = load(report_path); audit_path = 'reports/' + audit_name
        audit = load(audit_path); material = load('materials/' + directory + '/summary.json')
        plan = load('configs/' + plan_name); load(findings, text_only=True)
        require(audit['status'] == 'pass' and not report['audit_errors'], phase + ' closed audit')
        require(report['development_gate_met'] is audit['development_gate_met'], phase + ' fixed gate agreement')
        seeds = plan.get('model_seeds', [plan.get('model_seed')])
        require(all(type(s) is int for s in seeds), phase + ' seed identity')
        task_ids = [x['task_id'] for x in plan['known_tasks']]
        expected = {(mode, seed, TASKS[tid]) for mode in modes for seed in seeds for tid in task_ids}
        current = []
        for r in report['rows']:
            seed = r.get('model_seed', seeds[0]); mode = r[key]
            require(r['record_status'] == 'evaluated' and type(r['success']) is bool, phase + ' evaluated retained row')
            row = dict(phase=phase, arm=mode, model_seed=seed, task=TASKS[r['task_id']],
                       run_id=r['run_id'], evaluated=True, success=r['success'],
                       known_input_tokens=integer(r['input_tokens']), known_output_tokens=integer(r['output_tokens']),
                       known_token_subtotal=integer(r['known_total_tokens']), unknown_usage_calls=integer(r['unknown_usage_calls']),
                       model_calls=integer(r['model_calls']), environment_api_requests=integer(r['api_requests']),
                       stop_reason=r['stop_reason'], fixed_phase_gate=report['development_gate_met'])
            require(row['known_input_tokens']+row['known_output_tokens']==row['known_token_subtotal'], phase+' row total')
            for field, target in [('input_tokens','known_input_tokens'), ('output_tokens','known_output_tokens')]:
                require(sum(integer(v[field]) for v in r['usage_by_role'].values())==row[target], phase+' all role costs')
            require(sum(integer(v['calls'])for v in r['usage_by_role'].values())==row['model_calls']
                    and sum(integer(v['unknown_usage'])for v in r['usage_by_role'].values())==row['unknown_usage_calls'],
                    phase+' all role call/unknown counts')
            row['exact_total_tokens'] = row['known_token_subtotal'] if row['unknown_usage_calls'] == 0 else None
            runtime = r.get('projection_runtime', {})
            for name in METRICS:
                row[name] = integer(r[name]) if name in r else integer(runtime[name]) if name in runtime else None
            require(row[metric] is not None, phase+' primary mechanism evidence')
            current.append(row)
        require(len(current)==len(expected)==report['planned_rows']==plan['max_cells']
                and {(r['arm'],r['model_seed'],r['task'])for r in current}==expected, phase+' all planned identities')
        current.sort(key=lambda r:(r['model_seed'], modes.index(r['arm']), r['task']))
        conditions.extend(current)
        for mode in modes:
            selected = [r for r in current if r['arm']==mode]
            result = totals(selected)
            published = material['by_policy'][mode]; independent = audit['by_policy'][mode]
            for field in ('planned_conditions','evaluated_conditions','successful_conditions'):
                require(result[field]==published[field], phase+' material count '+field)
            require(result['known_token_subtotal']==published.get('known_token_subtotal',published.get('recorded_known_tokens'))
                    and result['unknown_usage_calls']==published['recorded_unknown_usage_calls']
                    and result['exact_total_tokens']==published.get('exact_total_tokens',published.get('exact_all_condition_tokens')), phase+' material cost')
            require(result['known_token_subtotal']==independent.get('known_token_subtotal',independent.get('known_tokens'))
                    and result['unknown_usage_calls']==independent.get('recorded_unknown_usage_calls',independent.get('unknown_usage_calls'))
                    and result['successful_conditions']==independent.get('successful_conditions',independent.get('successes')),phase+' independent count/cost')
            for field,target in [('input_tokens','known_input_tokens'),('output_tokens','known_output_tokens'),
                                 ('model_calls','model_calls'),('api_requests','environment_api_requests')]:
                if field in published.get('measures',{}):
                    require(result[target]==published['measures'][field]['known_subtotal'],phase+' material '+field)
                if field in independent.get('measures',{}):
                    require(result[target]==independent['measures'][field]['known_subtotal'],phase+' independent '+field)
                elif field in independent:
                    require(result[target]==independent[field],phase+' independent '+field)
            arms.append(dict(phase=phase,arm=mode,model_seeds=';'.join(map(str,seeds)),independent_tasks=len(task_ids),
                             **result, mechanism_metric=metric, mechanism_count=sum(r[metric]for r in selected),
                             fixed_phase_gate=report['development_gate_met']))
            for seed in seeds:
                subset=[r for r in selected if r['model_seed']==seed]
                arm_seeds.append(dict(phase=phase,arm=mode,model_seed=seed,**totals(subset),
                                      mechanism_metric=metric,mechanism_count=sum(r[metric]for r in subset)))
        for label_key, baseline, treatment in PAIR_SPECS[phase]:
            for selected_seed in [None]+(seeds if len(seeds)>1 else []):
                subset=current if selected_seed is None else [r for r in current if r['model_seed']==selected_seed]
                c=dict(phase=phase,comparison=label_key,scope='fixed_cohort' if selected_seed is None else 'seed',
                       model_seed=selected_seed,**compare(subset,baseline,treatment),fixed_phase_gate=report['development_gate_met'])
                # Keep conservative preregistered fields separate from descriptive subset arithmetic.
                fixed = None
                if phase=='P123' and label_key!='ordinary_anchor':
                    match=next(x for x in report['comparisons']if x['baseline']==baseline)
                    c['fixed_comparison_gate']=match['comparison_gate_met']
                elif phase=='P128' and selected_seed is not None:
                    match=next(x for x in report['per_seed']if x['model_seed']==selected_seed)
                    fixed=match['paired_successful_token_difference'];c['fixed_comparison_gate']=match['development_gate_met']
                elif phase=='P129':
                    if selected_seed is None:fixed=report['comparisons'][baseline]['paired_successful_token_difference']
                elif phase!='P123' and selected_seed is None:
                    fixed=report.get('paired_successful_token_difference')
                c['fixed_gate_common_success_delta_tokens']=fixed
                comparisons.append(c)
        phases[phase]=dict(planned_conditions=len(current),evaluated_conditions=len(current),independent_tasks=len(task_ids),
            model_seeds=seeds,world_seed=plan['world_seed'],fixed_development_gate=report['development_gate_met'],
            mechanism_metric=metric,mechanism_label=label,findings=findings,comparison_report=report_path,
            independent_audit=audit_path,plan='configs/'+plan_name,
            api_budget_by_task_slot=plan.get('api_budget_by_task_slot'),
            original_csv_api_budget=80 if phase in ('P123','P125','P133') else 120,
            fixed_criteria_preserved=True,novelty_established=False)

    require(len(conditions)==56, 'seven closed cohorts, 56 planned rows; not independent samples')
    recovery=load('reports/P133_reporting_recovery_v01_public_completion.json')
    require(recovery['status']=='complete' and recovery['original_attempts_preserved'] is True
            and recovery['original_collector_started'] is False,'separate P133 recovery')
    for stage,expected in [('audit',0),('session',0),('report',1)]:
        rel='reports/P133_'+stage+'_once_end.json'
        require(load(rel)['exit_code']==expected,'original P133 stage outcome')
        field='original_failure_sha256' if stage=='report' else 'original_'+stage+'_end_sha256'
        require(dependencies[rel]==recovery[field],'P133 original stage byte binding')
    load(recovery['recovery_manifest_path'])
    require(dependencies[recovery['recovery_manifest_path']]==recovery['recovery_manifest_sha256']
            and dependencies['reports/P133_comparison.json']==recovery['audit_sha256'],'P133 recovery artifacts')
    require(all(recovery[k]==0 for k in ('additional_model_calls','additional_API_requests',
            'additional_evaluations','additional_tokenizer_calls')),'data-only reporting recovery')
    phases['P133']['reporting_recovery']=dict(original_execution_head=recovery['original_head'],
        reporting_recovery_head=recovery['source_head'],original_stage_exits=[0,0,1],
        original_collector_started=False,original_failure_sha256=recovery['original_failure_sha256'],
        independent_audit='reports/P133_closed_independent_audit_20261027_recovery_v01.json',
        additional_model_API_evaluator_tokenizer_calls=0)
    p124=load('reports/P124_projection_replay.json');a124=load('reports/P124_projection_replay_independent_audit.json')
    p126=load('reports/P126_region_projection_replay.json');a126=load('reports/P126_closed_independent_audit_20261026.json')
    load('docs/P124_findings.md',text_only=True);load('docs/experiments/P126_findings.md',text_only=True)
    require(a124['audit_status']=='pass' and a126['status']=='pass','closed replay audits')
    regular126=[r for r in p126['programs']if r['comparison_scope']=='normal_prefix_boundary']
    regular_ok=sum(r['actual_execution_status']=='ok'for r in regular126)
    regular_errors=sum(r['actual_execution_status']=='execution_error'for r in regular126)
    require(len(regular126)==a126['matched_regular_boundary_programs']==regular_ok+regular_errors,
            'P126 regular boundary successes and known errors retained')
    replays=[dict(phase='P124',kind='saved_response_prefix_replay',attempted_programs=p124['attempted_generated_programs'],
        matched_regular_boundary_programs=a124['normal_boundaries_match_original'],paired_regular_boundaries=a124['normal_boundaries_match_between_arms'],
        frontier_programs=0,automatic_partial_hits=a124['cross_api_partial_hits_verified_from_only_prior_dispatched_library_returns'],
        traces=1,baseline_saved_backend_per_trace=p124['arms']['eager_cached']['saved_backend_responses'],
        treatment_saved_backend_per_trace=p124['arms']['automatic_projection_cached']['saved_backend_responses'],
        additional_model_calls=p124['model_calls'],environment_api_requests=p124['environment_API_requests'],
        evaluator_calls=p124['evaluator_calls'],whole_job_token_effect=None,task_success_effect=None),
        dict(phase='P126',kind='saved_response_frontier_replay',attempted_programs=p126['attempted_programs'],
        matched_regular_boundary_programs=a126['matched_regular_boundary_programs'],paired_regular_boundaries=a126['paired_regular_boundaries'],
        regular_boundary_ok_programs=regular_ok,regular_boundary_known_error_programs=regular_errors,
        frontier_programs=a126['frontier_programs'],automatic_partial_hits=a126['observed_partial_hits'],traces=2,
        baseline_saved_backend_per_trace=a126['saved_backend_per_trace_explicit'],
        treatment_saved_backend_per_trace=a126['saved_backend_per_trace_automatic'],
        additional_model_calls=p126['additional_model_calls'],environment_api_requests=p126['additional_API_requests'],
        evaluator_calls=p126['additional_evaluations'],whole_job_token_effect=None,task_success_effect=None)]
    require(all(r[k]==0 for r in replays for k in('additional_model_calls','environment_api_requests','evaluator_calls')),'replay is not live API/model comparison')
    f130=load('reports/P130_startup_failure_20261027.json');f131=load('reports/P131_preflight_failure_20261027.json')
    start=load('reports/P135_execution_start_20261027.json')
    load('docs/experiments/P131_execution_status_20261027.md',text_only=True)
    load('docs/experiments/P135_execution_start_20261027.md',text_only=True)
    require(f130['model_generation_dispatched'] is False and f130['task_API_or_evaluator_dispatched'] is False,'P130 not started')
    require(f131['actor_generation_dispatched'] is False and f131['task_API_or_evaluator_dispatched'] is False,'P131 not started')
    require(start['P134_unstarted_queue_failure_validated'] is True and start['all_six_conditions_complete_claim'] is False,'P134 unstarted / P135 start only')
    operations=[]
    for phase,reason in [('P130','server port検査でmodel subprocess前に停止'),
                         ('P131','旧supervisor識別が新basenameを拒否し計数・生成前に停止'),
                         ('P134','P133 report障害で前件queueが停止、model/server/preflight/task未開始')]:
        plan_path=next((root/'configs').glob(phase+'_*v01.json')).relative_to(root).as_posix()
        plan=load(plan_path)
        operations.append(dict(phase=phase,status='not_started_operational_failure',planned_conditions=plan['max_cells'],
            evaluated_conditions=0,successful_conditions=None,known_token_subtotal=None,unknown_usage_calls=None,
            exact_total_tokens=None,model_calls=0,environment_api_requests=0,evaluator_calls=0,reason=reason))
    operations.append(dict(phase='P135',status='start_record_only_no_closed_results_in_index',planned_conditions=start['planned_slots'],
        evaluated_conditions=None,successful_conditions=None,known_token_subtotal=None,unknown_usage_calls=None,
        exact_total_tokens=None,model_calls=None,environment_api_requests=None,evaluator_calls=None,
        reason='08:15:47 JST開始、08:18:19 JST処理確認。この一覧に閉鎖結果未収録、途中成果未読'))
    load('docs/research_history_review_20261026.md',text_only=True)
    summary=dict(scope='Selected closed cohorts since P123 handoff; not the complete research history',
        closed_model_cohorts=7,closed_model_conditions=56,conditions_are_not_56_independent_samples=True,
        no_cross_phase_or_seed_statistical_pooling=True,phases=phases,arms=arms,arm_seeds=arm_seeds,
        comparisons=comparisons,saved_response_replays=replays,operational_attempts=operations,
        unknown_usage_is_not_zero=True,empty_common_success_is_not_zero_cost=True,
        costs_include_agent_focus_failure_recovery_and_logical_cached_input=True,
        input_byte_counts_not_converted_to_tokens=True,audit_pass_is_not_scientific_gate=True,
        P135_interim_results_read=False,new_model_API_evaluator_tokenizer_calls=0,
        manuscript_written=False,novelty_established=False)
    return summary,conditions,dependencies


def csv_text(rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    stream=StringIO();writer=csv.DictWriter(stream,fieldnames=keys,lineterminator='\n')
    writer.writeheader();writer.writerows(rows);return stream.getvalue()


def display(value):
    return '—' if value is None else f'{value:,}' if type(value)is int else str(value)


def markdown(summary):
    lines=['# 引継ぎ後の閉鎖実験結果一覧','',
        '対象はP123以降の指定7モデル比較・全56条件。これは全研究成果の網羅でも56独立標本でもない。',
        '以前のP111等を含む経緯は[研究史](../../docs/research_history_review_20261026.md)、主張と比較条件は[入口](../../docs/closed_results_index_20261027.md)を参照。',
        '', '## 方式別の固定cohort集計','',
        '複数seedの行は元の固定cohortの記述的合計。seed別値は[arm_seeds.csv](arm_seeds.csv)、全56行は[conditions.csv](conditions.csv)。',
        'knownは既知小計。unknownが1件でも全費用は不明。cached inputを差し引かず、actor/focus・失敗・修復費用を含む。', '',
        '| Phase | Arm | seed | 予定/評価/成功 | known input | known output | known total | unknown呼出し | exact total | 実機構回数 | 固定gate |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in summary['arms']:
        lines.append('| '+ ' | '.join([r['phase'],r['arm'],r['model_seeds'],
            f"{r['planned_conditions']}/{r['evaluated_conditions']}/{r['successful_conditions']}",
            *[display(r[k])for k in('known_input_tokens','known_output_tokens','known_token_subtotal','unknown_usage_calls','exact_total_tokens','mechanism_count')],
            str(r['fixed_phase_gate']).lower()])+' |')
    lines+=['','実機構回数の定義: '+ '／'.join(p+': '+v['mechanism_label']for p,v in summary['phases'].items())+'。',
        'P123の採用回数、P128の固有turn数、P132のactor提示回数は相互に同じ単位ではない。通常cache/明示fieldの回数はconditions.csvに別列で保存。',
        '', '## 同一phase内の比較','',
        '差はtreatment−baseline。共通成功は記述的部分集合で、品質損失・unknownを含む全体gateを上書きしない。','',
        '| Phase / 比較 | baseline → treatment | 共通成功対 | 全体exact差 | 共通成功B/A | 共通成功の記述的差 | 元gate用の共通成功差 | 成功損失/改善 |',
        '|---|---|---:|---:|---|---:|---:|---|']
    for c in summary['comparisons']:
        if c['scope']!='fixed_cohort':continue
        lines.append('| '+' | '.join([c['phase']+' / '+c['comparison'],c['baseline']+' → '+c['treatment'],
            display(c['common_success_pairs']),display(c['exact_total_delta_tokens']),
            display(c['common_baseline_exact_tokens'])+' / '+display(c['common_treatment_exact_tokens']),
            display(c['descriptive_common_success_delta_tokens']),display(c['fixed_gate_common_success_delta_tokens']),
            f"{c['success_losses']}/{c['success_gains']}"])+' |')
    lines+=['','P123普通rolling対単発は記述的anchorで専用gate欄はない。P123 inlineの正式gateは両通常対照を上回ることを要求しfalse。',
        'P128/P129の元gate用の共通成功差nullと、費用が既知の共通成功部分集合の計算値は区別する。P132共通成功0の費用差は0でなくnull。',
        'seed別の全比較・P128各seedの固定gateも[comparisons.csv](comparisons.csv)と[summary.json](summary.json)へ保持。',
        '', '## 保存応答再生と未開始・未閉鎖','',
        '| Phase | 種類 | 範囲 | 観測 | 全仕事token/課題品質効果 |',
        '|---|---|---|---|---|',
        '| P124 | 保存prefix再生 | 1旧記録×2arm×10program=20 | 境界20・方式間10一致、保存backend68→57、partial22 | 未測定。実環境API/model/eval0 |',
        '| P126 | 保存frontier再生 | 2旧記録×2arm×12program=48 | 通常prefix境界44（正常終了40＋既知エラー4）・方式間22一致、frontier4、各記録保存backend80→67、partial計26 | 未測定。実環境API/model/eval0 |']
    for r in summary['operational_attempts']:
        interpretation=('この一覧に閉鎖結果未収録、費用/成否は未記載' if r['phase']=='P135' else
                        '課題実験未開始、運用失敗を保持。課題成否/費用効果は未測定')
        lines.append(f"| {r['phase']} | {r['status']} | 予定{r['planned_conditions']}・評価{display(r['evaluated_conditions'])} | {r['reason']} | {interpretation} |")
    lines+=['','保存backend件数は固定応答再生の計数で、実API削減・最終成功・全仕事token改善ではない。P126は未知suffixを実行せず、frontierで真の最終full-root同値を主張しない。',
        'P133元reportのexit1と別data-only回収を保持し、同phaseを再実行したと数えない。P130/P131/P134の未開始失敗も一覧から除かない。',
        '', '## 再生成と根拠','',
        '`python scripts/build_closed_results_index_20261027.py --check` は公開JSONだけを再集計して保存資料へ照合する。',
        '`--output-dir NEW_DIRECTORY` は既存資料を上書きせず別ディレクトリへ生成する。',
        '[source_manifest.json](source_manifest.json)は入力資料・generator・出力のSHA256を保存する。',
        'この固定対象では全56条件が評価済み。予定行の欠落・未評価・根拠不一致があれば補完せず生成を停止する。元監査や生成code、model/API/tokenizer/evaluatorは再実行しない。','']
    return '\n'.join(lines)


def artifacts(root):
    summary,conditions,dependencies=build(root)
    outputs={'summary.json':json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n',
             'conditions.csv':csv_text(conditions),'arms.csv':csv_text(summary['arms']),
             'arm_seeds.csv':csv_text(summary['arm_seeds']),'comparisons.csv':csv_text(summary['comparisons']),
             'replays.csv':csv_text(summary['saved_response_replays']),
             'operational_attempts.csv':csv_text(summary['operational_attempts']), 'README.md':markdown(summary)}
    manifest=dict(input_source_sha256=dependencies,generator_path='scripts/'+Path(__file__).name,
                  generator_sha256=sha(Path(__file__).read_bytes()),
                  artifact_sha256={k:sha(v.encode())for k,v in outputs.items()},
                  reads_only_named_public_files=True,previous_ledgers_modified=False,
                  new_model_API_evaluator_tokenizer_calls=0,P135_interim_results_read=False)
    outputs['source_manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    return outputs


def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true');group.add_argument('--output-dir',type=Path)
    args=parser.parse_args();outputs=artifacts(ROOT)
    dest=ROOT/MATERIALS if args.check else args.output_dir
    if args.check:
        for rel,content in outputs.items():require((dest/rel).read_bytes()==content.encode(), 'generated artifact differs: '+rel)
    else:
        dest.mkdir(parents=True,exist_ok=False)
        for rel,content in outputs.items():(dest/rel).write_text(content)
    print(json.dumps(dict(status='pass',artifacts=len(outputs),closed_conditions=56,actual_model_API_calls=0)))


if __name__=='__main__':
    main()

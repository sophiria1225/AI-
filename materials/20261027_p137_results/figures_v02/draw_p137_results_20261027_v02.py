"""Closed-only P137 figures and hash-bound public, data-only redraw.

The closed loader reads the collector and independent review before results.
The redraw path needs only this source, public figure_data and its manifest;
it does not repeat or certify the experiment or scientific audit.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

HEAD = 'a6c088f8f382521010ff264ffe22f52d2146314e'
PLAN = 'configs/P137_remaining_late_obligations_v01.json'
PLAN_SHA = '9b8b020c83bf1d996b4d977a628831c46da4d7a0e469a3cf2b8f0e18916720f1'
PLAN_SOURCE_COUNT = 1547
REGISTRY_LEDGERS = 196
REGISTRY_BINDINGS = 2433
REVIEW_SHA = '7b58a7b2dbb5dd6a629445ac79cf59432798eead443e8f3a0b078a41ae71f47e'
WRAPPER_SHA = '01b790eb78e380ab60228535c6c8ef23e3d09b4f2705870a3f299a5ec01e8419'
COLLECTOR_SHA = '3cfdfba93cb0d5bb9fda4446ab095ecd45b074f92790b8e0f81c8ebc670d647e'
MATERIAL = 'materials/20261027_p137_results'
MODES = ('raw_anchor', 'ids_only', 'entity_fields')
SEEDS = (57, 157)
ORDER = ((1, 'entity_fields'), (2, 'entity_fields'), (2, 'ids_only'), (2, 'raw_anchor'))
OBLIGATION_COUNTS = ('obligation_checkpoint_captures', 'obligation_notice_actor_calls',
    'obligation_entity_rows_exposed', 'obligation_field_rows_exposed', 'obligation_queries', 'obligation_query_rejections')
COUNT_FIELDS = ('known_total_tokens', 'unknown_usage_calls', 'api_requests', 'model_calls',
    'checkpoint_installations', *OBLIGATION_COUNTS)
FLAGS = ('obligation_contract_failed', 'obligation_accounting_complete')
ROW_FIELDS = ('run_id', 'replication', 'model_seed', 'obligation_mode', 'record_status', 'success',
    *COUNT_FIELDS, *FLAGS, 'obligation_runtime_wall_seconds', 'obligation_final_enumeration',
    'usage_by_role', 'exact_total_tokens')
EVIDENCE_FIELDS = ('collector_end', 'collector_start', 'closure', 'pipeline_start', 'independent_review')
CLAIMS = dict(scientific_adoption_evaluated=False, prior_results_pooled=False,
    original_P136_gate_replaced=False, balanced_repetitions=False, novelty_established=False, general_quality_preservation_claim=False,
    timing_superiority_claim=False, entity_rows_are_unique_entities=False,
    query_interface_exposed=False, public_snapshot_handle_exposed=False,
    initial_guide_added=False, independent_run_trajectories_assumed_identical=False,
    first_divergence_attributed_to_entity_content_alone=False,
    observed_field_completion_is_official_task_success=False,
    additional_model_API_evaluation_tokenizer_calls=0, saved_program_execution=0)
DATA_FIELDS = {'phase', 'synthetic', 'rows', 'criteria', 'audit_error_count',
    'fixed_head', 'fixed_plan_sha256', 'fixed_independent_review_source_sha256',
    'source_binding_count', 'launch_registry_ledgers', 'launch_registry_bindings',
    'server_wall_seconds', 'source_sha256', 'evidence_sha256', *CLAIMS}


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def valid_hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def public_path(value):
    return (type(value) is str and not Path(value).is_absolute() and '\\' not in value
        and '..' not in Path(value).parts and value.split('/')[0] in
        ('scripts', 'tests', 'configs', 'docs', 'reports', 'materials', 'README.md',
         'RESUME.md', 'AGENTS.md', '.github', '.gitignore', 'requirements.txt', 'pyproject.toml',
         'Makefile', 'tracking', 'src', 'examples', 'prompts', 'assets'))


def safe(root, relative):
    # The frozen source manifest can include any repository-relative source;
    # no source content, credential or private absolute path enters figure_data.
    require(type(relative) is str and relative and not Path(relative).is_absolute()
        and '..' not in Path(relative).parts and '\\' not in relative,
        'relative public source required')
    return root / relative


def require_bindings():
    require(type(HEAD) is str and re.fullmatch('[0-9a-f]{40}', HEAD) is not None
        and all(valid_hash(x) for x in (PLAN_SHA, REVIEW_SHA, WRAPPER_SHA, COLLECTOR_SHA))
        and type(PLAN_SOURCE_COUNT) is int and PLAN_SOURCE_COUNT > 0,
        'P137 frozen bindings are not installed')


def comparison(rows, baseline):
    before, after = [next(r for r in rows if r['replication'] == 2 and r['obligation_mode'] == mode)
        for mode in (baseline, 'entity_fields')]
    ready = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (before, after))
    known = ready and all(integer(r.get('known_total_tokens')) and integer(r.get('unknown_usage_calls'))
        and r['unknown_usage_calls'] == 0 for r in (before, after))
    transition = ('not_both_evaluated' if not ready else 'common_success' if before['success'] and after['success']
        else 'quality_loss' if before['success'] else 'quality_gain' if after['success'] else 'both_failed')
    delta = after['known_total_tokens'] - before['known_total_tokens'] if known else None
    common = transition == 'common_success'
    pair = dict(replication=2, model_seed=157, baseline_success=before['success'],
        candidate_success=after['success'], both_evaluated=ready, both_usage_known=known,
        both_successful=common if ready else None, success_lost=(transition == 'quality_loss') if ready else None,
        quality_transition=transition, candidate_minus_baseline_tokens=delta)
    return dict(baseline=baseline, candidate='entity_fields', scope='same_cohort_seed157_only',
        paired_results=[pair], comparable_model_seeds=[157], both_pairs_evaluated=ready,
        both_pairs_usage_known=known, paired_success_losses=int(transition == 'quality_loss') if ready else None,
        paired_successful_task_seed_pairs=int(common) if ready else None,
        candidate_minus_baseline_whole_task_tokens=delta,
        paired_successful_token_difference=delta if known and common else None,
        costs_by_quality_transition={name: dict(pairs=int(transition == name),
            candidate_minus_baseline_tokens=(delta if transition == name else 0) if known else None)
            for name in ('common_success','quality_gain','quality_loss','both_failed','not_both_evaluated')})


def criteria(rows, audit_errors):
    require(integer(audit_errors), 'audit error count is an exact nonnegative integer')
    require(len(rows) == 4 and [(r['replication'], r['obligation_mode']) for r in rows] == list(ORDER),
        'all four fixed remaining slots required')
    evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in rows)
    known = evaluated and all(integer(r.get('known_total_tokens')) and integer(r.get('unknown_usage_calls'))
        and r['unknown_usage_calls'] == 0 for r in rows)
    primary, anchor = comparison(rows, 'ids_only'), comparison(rows, 'raw_anchor')
    field_row = next(r for r in rows if r['replication'] == 2 and r['obligation_mode'] == 'entity_fields')
    exposure = field_row.get('obligation_field_rows_exposed')
    common = primary['paired_results'][0]['both_successful'] is True
    activity = exposure if common and integer(exposure) else None
    intact = all(r.get('obligation_contract_failed') is False and r.get('obligation_accounting_complete') is True for r in rows)
    pair_ready = primary['both_pairs_evaluated'] and anchor['both_pairs_evaluated']
    lossless = (primary['paired_success_losses'] == 0 and anchor['paired_success_losses'] == 0) if pair_ready else None
    return dict(all_four_complete_with_known_usage=known, all_four_evaluated=evaluated,
        primary_comparison=primary, raw_anchor_comparison=anchor,
        no_paired_success_loss_against_either_control=lossless,
        field_rows_exposed_on_primary_common_success=activity, mechanism_contracts_intact=intact,
        seed57_unpaired_result={key: rows[0].get(key) for key in
            ('run_id','record_status','success','known_total_tokens','unknown_usage_calls','obligation_field_rows_exposed')},
        planned_rows=4, independent_tasks=1, repetitions=2, balanced_repetitions=False, model_seeds=list(SEEDS),
        development_gate_met=False, scientific_adoption_evaluated=False,
        original_P136_gate_replaced=False, prior_results_pooled=False,
        novel_method_claim=False, general_quality_preservation_claim=False,
        audit_errors_present=bool(audit_errors),
        interpretation='Four originally unrun slots only; no P136 row is replaced. Seed157 has one within-cohort '
            'three-arm descriptive comparison. Seed57 entity-fields is unpaired. All failures, unknown usage, '
            'summary/disclosure costs remain. No original six-slot adoption gate is evaluated or passed.')


def validate_data(data):
    require(type(data) is dict and set(data) == DATA_FIELDS, 'fixed public figure data schema')
    require(data['phase'] == 'P137' and type(data['synthetic']) is bool, 'P137 figure identity')
    for key, expected in dict(fixed_head=HEAD, fixed_plan_sha256=PLAN_SHA,
        fixed_independent_review_source_sha256=REVIEW_SHA, source_binding_count=PLAN_SOURCE_COUNT,
        launch_registry_ledgers=REGISTRY_LEDGERS, launch_registry_bindings=REGISTRY_BINDINGS, **CLAIMS).items():
        require(digest(data[key]) == digest(expected), 'fixed claim or source identity: ' + key)
    require(number(data['server_wall_seconds']) or data['server_wall_seconds'] is None, 'session time measured or unknown')
    require(type(data['source_sha256']) is dict and type(data['evidence_sha256']) is dict, 'hash maps')
    for name, value in data['source_sha256'].items():
        safe(Path('.'), name)
        require(valid_hash(value), 'public source SHA')
    require(set(data['evidence_sha256']) <= set(EVIDENCE_FIELDS)
        and all(valid_hash(v) for v in data['evidence_sha256'].values()), 'public evidence hash labels only')
    if not data['synthetic']:
        require_bindings()
        require(data['source_sha256'].get(PLAN) == PLAN_SHA and set(data['evidence_sha256']) == set(EVIDENCE_FIELDS),
            'actual figures need bound public sources and closed evidence hashes')
    rows = data['rows']
    require(type(rows) is list and all(type(r) is dict and set(r) == set(ROW_FIELDS) for r in rows), 'public row fields only')
    require([(r['replication'], r['obligation_mode']) for r in rows] == list(ORDER), 'fixed four ordered rows')
    for row in rows:
        require(type(row['replication']) is int and type(row['model_seed']) is int
            and row['model_seed'] == SEEDS[row['replication'] - 1], 'fixed seed identity')
        require(row['run_id'] == f"BOC_P137_R{row['replication']:02d}_01_{row['obligation_mode'].upper()}", 'fixed P137 run identity')
        status = row['record_status']
        require(status in ('evaluated', 'unevaluated', 'not_run', 'incomplete_worker', 'audit_error'), 'record status')
        require(type(row['success']) is bool if status == 'evaluated' else row['success'] is None, 'official outcome')
        if status in ('evaluated', 'unevaluated'):
            require(all(integer(row[k]) for k in COUNT_FIELDS), 'nonnegative measured counts')
            require(row['model_calls'] <= 80 and row['api_requests'] <= 80
                and row['unknown_usage_calls'] <= row['model_calls'], 'finite model and API bounds')
            require(type(row['obligation_contract_failed']) is bool and type(row['obligation_accounting_complete']) is bool, 'typed accounting flags')
            require(number(row['obligation_runtime_wall_seconds']), 'finite measured host time')
            require(row['obligation_final_enumeration'] in ('open', 'closed', 'unknown'), 'enumeration status')
            require(row['obligation_checkpoint_captures'] == row['checkpoint_installations'] <= 3
                and row['obligation_notice_actor_calls'] <= row['obligation_checkpoint_captures']
                and row['obligation_entity_rows_exposed'] <= 16 * row['obligation_notice_actor_calls']
                and row['obligation_query_rejections'] <= row['obligation_queries'], 'capture notice row query conservation')
            require(row['obligation_field_rows_exposed'] <= row['obligation_entity_rows_exposed']
                and (row['obligation_field_rows_exposed'] == row['obligation_entity_rows_exposed']
                     if row['obligation_mode'] == 'entity_fields' else row['obligation_field_rows_exposed'] == 0), 'field-only rows are distinct from ID rows')
            require(row['obligation_queries'] == row['obligation_query_rejections'] == 0, 'no query capability in any mode')
            require(row['obligation_mode'] != 'raw_anchor' or row['obligation_notice_actor_calls'] == row['obligation_entity_rows_exposed'] == row['obligation_queries'] == 0, 'raw anchor has no added interface')
            roles = row['usage_by_role']
            require(type(roles) is dict and set(roles) == {'agent', 'focus'}, 'paid role totals required')
            for role in roles.values():
                require(type(role) is dict and set(role) == {'calls', 'unknown_usage', 'input_tokens', 'output_tokens'}
                    and all(integer(x) for x in role.values()) and role['unknown_usage'] <= role['calls'], 'typed role values')
            require(sum(v['input_tokens'] + v['output_tokens'] for v in roles.values()) == row['known_total_tokens'], 'whole job includes all paid known actor and focus tokens')
            require(sum(v['calls'] for v in roles.values()) == row['model_calls']
                and sum(v['unknown_usage'] for v in roles.values()) == row['unknown_usage_calls'], 'model and unknown role counts')
        else:
            require(all(row[k] is None for k in (*COUNT_FIELDS, *FLAGS, 'usage_by_role',
                'obligation_runtime_wall_seconds', 'obligation_final_enumeration')), 'missing measurements remain null')
        require(row['exact_total_tokens'] == (row['known_total_tokens'] if integer(row['unknown_usage_calls'])
            and row['unknown_usage_calls'] == 0 else None), 'known subtotal is not exact unknown total')
    require(digest(criteria(rows, data['audit_error_count'])) == digest(data['criteria']), 'criteria independently recalculated from all four rows')
    return data


def base_data(rows, *, synthetic, audit_errors, sources, evidence, server_wall):
    return dict(phase='P137', synthetic=synthetic, rows=rows, criteria=criteria(rows, audit_errors),
        audit_error_count=audit_errors, fixed_head=HEAD, fixed_plan_sha256=PLAN_SHA,
        fixed_independent_review_source_sha256=REVIEW_SHA, source_binding_count=PLAN_SOURCE_COUNT,
        launch_registry_ledgers=REGISTRY_LEDGERS, launch_registry_bindings=REGISTRY_BINDINGS, server_wall_seconds=server_wall,
        source_sha256=sources, evidence_sha256=evidence, **CLAIMS)


def load_closed(args):
    require_bindings()
    # Gate order is deliberate: no result or raw record is read before these.
    collector = read(args.collector_end)
    require(collector.get('status') == 'complete' and type(collector.get('planned_conditions')) is int
        and collector['planned_conditions'] == 4, 'collector complete for all four required before results')
    review = read(args.independent_review)
    require(review.get('status') == 'pass' and review.get('collector_complete_seen_before_trial_read') is True
        and review.get('review_script_sha256') == REVIEW_SHA
        and review.get('collector_end_sha256') == sha(args.collector_end), 'fixed closed independent review required')
    closure, cs, start = (read(getattr(args, k)) for k in ('closure', 'collector_start', 'pipeline_start'))
    require(start['source_head'] == cs['source_head'] == review['fixed_head'] == HEAD, 'fixed source head')
    require(start['plan_sha256'] == review['plan_sha256'] == PLAN_SHA, 'fixed plan SHA')
    require(start['wrapper_sha256'] == WRAPPER_SHA and cs['wrapper_sha256'] == COLLECTOR_SHA, 'fixed operational sources')
    require(cs['closure_sha256'] == sha(args.closure), 'collector closure lineage')
    require(review.get('start_registry_ledgers') == collector.get('prior_ledgers_unchanged') == REGISTRY_LEDGERS
        and review.get('start_registry_bindings') == collector.get('prior_bindings_unchanged') == REGISTRY_BINDINGS, 'original reserved snapshot only')
    require([s['stage'] for s in closure['stages']] == ['audit', 'session', 'report']
        and all(type(s['exit_code']) is int and (s['stage'] == 'audit' or s['exit_code'] == 0) for s in closure['stages']), 'all postprocessing closed')
    require(all(type(collector[k]) is int and collector[k] == 0 for k in
        ('additional_model_calls', 'additional_API_requests', 'additional_evaluations')), 'collector is data only')
    root = args.repo_root.resolve()
    require(sha(root / PLAN) == PLAN_SHA, 'fixed plan bytes')
    sources = {PLAN: PLAN_SHA}
    def bind(relative, expected):
        require(valid_hash(expected) and sha(safe(root, relative)) == expected, 'public source hash mismatch: ' + relative)
        sources[relative] = expected
    plan = read(root / PLAN)
    require(len(plan['source_sha256']) == PLAN_SOURCE_COUNT, 'all frozen source bindings')
    for relative, expected in plan['source_sha256'].items():
        bind(relative, expected)
    for relative, expected in collector['copied_source_sha256'].items():
        bind(relative, expected)
    for relative, key in [('reports/P137_comparison.json', 'audit_sha256'),
        ('reports/P137_server_session.json', 'session_sha256'), (MATERIAL + '/build_manifest.json', 'report_manifest_sha256')]:
        bind(relative, closure[key])
    manifest = read(root / MATERIAL / 'build_manifest.json')
    for relative, expected in manifest['source_sha256'].items():
        bind(relative, expected)
    for relative, expected in manifest['artifact_sha256'].items():
        bind(MATERIAL + '/' + relative, expected)
    audit = read(root / 'reports/P137_comparison.json')
    session = read(root / 'reports/P137_server_session.json')
    public = read(root / MATERIAL / 'summary.json')
    require(audit['phase'] == session['phase'] == public['phase'] == 'P137'
        and audit['owned_processes_absent'] is True and session['owned_processes_absent'] is True
        and session['status'] == 'stopped', 'closed public audit and owned server')
    require(len(audit['audit_errors']) == closure['audit_errors'] == collector['audit_errors'], 'all audit errors preserved')
    expected_ids = [(f'BOC_P137_R{rep:02d}_01_{mode.upper()}', rep, SEEDS[rep - 1], mode) for rep, mode in ORDER]
    require([(r['run_id'], r['replication'], r['model_seed'], r['obligation_mode']) for r in audit['rows']] == expected_ids, 'fixed all four identities')
    require([(r['run_id'], r['replication'], r['model_seed'], r['obligation_mode']) for r in public['conditions']] == expected_ids, 'public all four identities')
    rows = []
    for raw, exported in zip(audit['rows'], public['conditions'], strict=True):
        row = {key: deepcopy(raw.get(key)) for key in ROW_FIELDS}
        row['exact_total_tokens'] = row['known_total_tokens'] if integer(row['unknown_usage_calls']) and row['unknown_usage_calls'] == 0 else None
        for key in ROW_FIELDS:
            if key != 'usage_by_role':
                require(digest(row[key]) == digest(exported.get(key)), 'public field binding: ' + key)
        rows.append(row)
    recalculated = criteria(rows, len(audit['audit_errors']))
    for key, value in recalculated.items():
        require(all(digest(value) == digest(mapping[key]) for mapping in
            (audit, public['audited_criteria'], review['independent_criteria'])), 'scientific criterion binding: ' + key)
    data = base_data(rows, synthetic=False, audit_errors=len(audit['audit_errors']), sources=sources,
        evidence={key: sha(getattr(args, key)) for key in EVIDENCE_FIELDS}, server_wall=session.get('wall_seconds'))
    return validate_data(data)


def label(row):
    return f"Seed {row['model_seed']}" + (' (unpaired)' if row['replication'] == 1 else '') + '\n' + {'raw_anchor': 'Raw P123 anchor', 'ids_only': 'IDs only', 'entity_fields': 'IDs + fields'}[row['obligation_mode']]


def outcome(row):
    result = 'SUCCESS' if row['success'] is True else 'FAILURE' if row['success'] is False else row['record_status'].replace('_', ' ').upper()
    return result + (' / CONTRACT FAILURE' if row['obligation_contract_failed'] is True else '')


def value_label(row):
    if row['known_total_tokens'] is None:
        return outcome(row) + '\nUsage unmeasured'
    extra = f"; unknown {row['unknown_usage_calls']}" if row['unknown_usage_calls'] else ''
    return f"{row['known_total_tokens']:,} " + ('known subtotal' if extra else 'exact') + '\n' + outcome(row) + extra


def format_delta(value):
    return 'unmeasured' if value is None else f'{value:+,}'


def comparison_table(data):
    result = []
    for title, key in [('PRIMARY: fields − IDs', 'primary_comparison'), ('ANCHOR: fields − raw', 'raw_anchor_comparison')]:
        value = data['criteria'][key]
        common = value['paired_successful_task_seed_pairs']
        groups = value['costs_by_quality_transition']
        result.append([title, format_delta(value['candidate_minus_baseline_whole_task_tokens']),
            str(common) + '/1' if common is not None else 'unmeasured',
            format_delta(value['paired_successful_token_difference']),
            '/'.join(str(groups[k]['pairs']) for k in ('quality_gain', 'quality_loss', 'both_failed', 'not_both_evaluated'))])
    return result


def render(data, output, *, redraw_lineage=None):
    validate_data(data)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none'})
    rows = sorted(data['rows'], key=lambda row: (row['replication'], MODES.index(row['obligation_mode'])))
    count = len(rows)
    tokens = [r['known_total_tokens'] if r['known_total_tokens'] is not None else 0 for r in rows]
    ceiling = max([1, *tokens])
    prefix = 'SYNTHETIC EXAMPLE — ' if data['synthetic'] else ''
    colors = {'raw_anchor': '#718396', 'ids_only': '#3575A5', 'entity_fields': '#D77B31'}
    fig = plt.figure(figsize=(15, 9))
    ax = fig.add_axes([.07, .39, .9, .43])
    bars = ax.bar(range(count), tokens, width=.64, color=[colors[r['obligation_mode']] for r in rows])
    for index, (bar, row) in enumerate(zip(bars, rows)):
        if row['known_total_tokens'] is None:
            bar.set_facecolor('none')
            ax.scatter(index, ceiling * .015, marker='x', color='#555555')
        elif row['unknown_usage_calls']:
            bar.set_hatch('///'); bar.set_edgecolor('#333333')
        ax.text(index, tokens[index] + ceiling * .025, value_label(row), ha='center', va='bottom', fontsize=9)
    ax.set_ylim(0, ceiling * 1.35)
    ax.set_xticks(range(count), [label(row) for row in rows])
    ax.axvline(.5, color='#666666', linestyle=':', linewidth=1)
    ax.set_ylabel('Logical input + output tokens')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:,.0f}'))
    ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    fig.suptitle(prefix + 'P137 — Whole-job cost and official outcome', fontsize=16, y=.96)
    fig.text(.07, .885, 'All 4 new slots: seed57 fields is unpaired; seed157 has 3 modes. No P136 outcomes or costs are pooled.', fontsize=11)
    table_ax = fig.add_axes([.045, .205, .93, .105]); table_ax.axis('off')
    table = table_ax.table(cellText=comparison_table(data), colLabels=['Comparison', 'Seed157 pair: Δ tokens',
        'Common successes', 'Common-success Δ', 'Gain/loss/both failed/not evaluated'],
        colWidths=[.24, .18, .16, .17, .25], loc='center', cellLoc='center')
    table.auto_set_font_size(False); table.set_fontsize(9); table.scale(1, 1.7)
    footer = (f"Adoption gate (not evaluated): {data['criteria']['development_gate_met']}. Negative differences mean fewer tokens, not automatically better quality.\n"
        'Hatching = known subtotal plus unmeasured usage; × = usage unmeasured. No condition is omitted. Cached input is not subtracted.\n'
        'Both comparison rows use seed157 only. Common-success costs exclude gains, losses and both-failed pairs.\n'
        "Comparison-table 'unmeasured' also includes conservative descriptive null aggregates with some known components.\n"
        'Seed157 is one descriptive pair; seed57 is unpaired. Unbalanced policy totals are not an effect comparison.')
    fig.text(.07, .055, footer, fontsize=10, linespacing=1.5)
    for ext in ('png', 'svg', 'pdf'):
        fig.savefig(output / ('whole_job_cost.' + ext), dpi=180)
    plt.close(fig)

    fig = plt.figure(figsize=(15, 11))
    ax = fig.add_axes([.07, .51, .9, .32])
    actor = [0 if r['usage_by_role'] is None else sum(r['usage_by_role']['agent'][k] for k in ('input_tokens', 'output_tokens')) for r in rows]
    focus = [0 if r['usage_by_role'] is None else sum(r['usage_by_role']['focus'][k] for k in ('input_tokens', 'output_tokens')) for r in rows]
    actor_bars = ax.bar(range(count), actor, color='#527B9D', width=.64, label='Actor: known paid tokens')
    focus_bars = ax.bar(range(count), focus, bottom=actor, color='#D7A05B', width=.64, label='Focus: known paid tokens')
    for index, row in enumerate(rows):
        if row['usage_by_role'] is None:
            ax.scatter(index, ceiling * .015, marker='x', color='#555555'); note = 'Usage unmeasured'
        else:
            for name, bar in (('agent', actor_bars[index]), ('focus', focus_bars[index])):
                if row['usage_by_role'][name]['unknown_usage']:
                    bar.set_hatch('///'); bar.set_edgecolor('#333333')
            note = f"Actor calls {row['usage_by_role']['agent']['calls']} | focus {row['usage_by_role']['focus']['calls']}"
            if row['unknown_usage_calls']:
                note += f"\nUnknown usage calls {row['unknown_usage_calls']}"
        ax.text(index, tokens[index] + ceiling * .025, note, ha='center', va='bottom', fontsize=9)
    ax.set_ylim(0, ceiling * 1.3)
    ax.set_xticks(range(count), [label(row) for row in rows])
    ax.axvline(.5, color='#666666', linestyle=':', linewidth=1)
    ax.set_ylabel('Known logical input + output tokens')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:,.0f}'))
    ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True); ax.legend(loc='upper right', fontsize=9)
    fig.suptitle(prefix + 'P137 — Paid work and observed intervention', fontsize=16, y=.96)
    fig.text(.07, .885, 'All modes pay host observation/capture costs. Notice dispatch, cumulative ID rows and rows with missing fields are separate.', fontsize=11)
    metrics = [('Checkpoint captures', 'obligation_checkpoint_captures'),
        ('Actor calls with automatic notice', 'obligation_notice_actor_calls'),
        ('Cumulative automatic ID rows', 'obligation_entity_rows_exposed'),
        ('Rows with missing-field associations', 'obligation_field_rows_exposed'),
        ('Queries / rejections (absent interface)', None), ('Host observation/capture time (s)', 'obligation_runtime_wall_seconds'),
        ('Final enumeration status', 'obligation_final_enumeration')]
    cells = []
    for title, field in metrics:
        values = []
        for row in rows:
            if field is None:
                value = None if row['obligation_queries'] is None else f"{row['obligation_queries']} / {row['obligation_query_rejections']}"
            else:
                value = row[field]
            values.append('unmeasured' if value is None else f'{value:.3f}' if field == 'obligation_runtime_wall_seconds' else str(value))
        cells.append([title, *values])
    tax = fig.add_axes([.04, .21, .94, .24]); tax.axis('off')
    table = tax.table(cellText=cells, colLabels=['Observed measure', *[label(row) for row in rows]],
        colWidths=[.36, *([.64 / count] * count)], loc='center', cellLoc='center')
    table.auto_set_font_size(False); table.set_fontsize(8.5); table.scale(1, 1.8)
    foot = ('ID and field-row exposure is cumulative across paid actor requests, not unique entities or completed obligations.\n'
        'A capture without subsequent dispatch is not exposure. All modes use the original raw initial guide and tools; queries are absent.\n'
        'No public handle is displayed. Equal initial inputs do not guarantee equal trajectories across independent runs.\n'
        'Host seconds overlap work/session time and are not added again. Bytes are never converted to tokens. Enumeration is not official success.')
    fig.text(.07, .045, foot, fontsize=9.7, linespacing=1.5)
    for ext in ('png', 'svg', 'pdf'):
        fig.savefig(output / ('paid_work_and_obligations.' + ext), dpi=180)
    plt.close(fig)
    (output / 'figure_data.json').write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    (output / 'README.md').write_text('# P137 figures\n\n'
        + ('Synthetic preview; these are not experiment results.\n\n' if data['synthetic'] else 'All 4 planned new slots retained after closed independent review, including missing or unrun slots.\n\n')
        + 'Whole-job costs include all known actor/focus input and output; unknown and missing costs remain unmeasured. '
        'Cumulative ID/field-row exposure is not a unique-entity count. Enumeration does not replace official evaluation. '
        'All initial capabilities are the original raw interface; no query or public handle is added. Independent trajectories are not assumed identical. Seed57 fields is unpaired; seed157 is one within-cohort descriptive comparison. Unequal by-policy sums are not compared as effects. The adoption gate is always false and P136 results are neither replaced nor pooled. '
        "Comparison-table 'unmeasured' means a fixed descriptive aggregate is null; it does not assert that every component cost was physically unmeasured.\n\n"
        + 'Layout revision v02: only the paid-work legend moved from upper left to upper right, avoiding the seed57 call annotation. '
        'The original v01 files and scientific data are preserved; this is a data-only layout improvement, not a new experiment or audit.\n\n'
        + 'Public redraw: use this exact v02 renderer with `--redraw --figure-data figure_data.json '
        '--original-manifest output_manifest.json --manifest-sha256 <published SHA256> --output-dir <new directory>`. '
        'Only these public files are read; the original audit is not re-certified. Original files are never overwritten. '
        'PNG/PDF/SVG bytes can differ with font, plotting-library, date metadata and renderer settings; scientific data stay hash-bound.\n')
    artifacts = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    manifest = dict(phase='P137', synthetic=data['synthetic'], renderer_source_sha256=sha(__file__),
        fixed_head=HEAD, fixed_plan_sha256=PLAN_SHA, fixed_independent_review_source_sha256=REVIEW_SHA,
        source_binding_count=PLAN_SOURCE_COUNT, launch_registry_ledgers=REGISTRY_LEDGERS, launch_registry_bindings=REGISTRY_BINDINGS,
        figure_data_sha256=artifacts['figure_data.json'], artifact_sha256=artifacts,
        source_sha256=data['source_sha256'], evidence_sha256=data['evidence_sha256'],
        generated_at=datetime.now(timezone.utc).isoformat(), original_results_changed=False,
        additional_model_API_evaluation_tokenizer_calls=0, saved_program_execution=0,
        redraw_is_not_renewed_scientific_audit=True, redraw_lineage=redraw_lineage,
        layout_revision=2, layout_change='paid_work_legend_upper_left_to_upper_right_only',
        original_v01_renderer_source_sha256='fd2d3e63500fb0f1d927663028230b3760518b00efca9184e05515179b5e3e81',
        original_v01_manifest_sha256='ed9c426056212d55354219218d52d1fb6bf980a9ed4e74103019634029d3cda1',
        original_v01_figure_data_sha256='550d3dac9c41ad097807f09cefc717c7d3156dd9edae28bd5c67568c1ee4c05c',
        byte_identical_graphics_not_guaranteed_across_fonts_versions_dates=True)
    (output / 'output_manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    return manifest


def synthetic(*, missing=True):
    rows = []
    for rep, mode in ORDER:
        known = {'raw_anchor': 180000, 'ids_only': 170000, 'entity_fields': 140000}[mode]
        unknown = int(rep == 2 and mode == 'ids_only')
        roles = {'agent': dict(calls=10, unknown_usage=unknown, input_tokens=known - 30000, output_tokens=10000),
            'focus': dict(calls=2, unknown_usage=0, input_tokens=19000, output_tokens=1000)}
        row = dict(run_id=f'BOC_P137_R{rep:02d}_01_{mode.upper()}', replication=rep, model_seed=SEEDS[rep - 1], obligation_mode=mode,
            record_status='evaluated', success=(rep == 1), known_total_tokens=known,
            unknown_usage_calls=unknown, exact_total_tokens=known if not unknown else None,
            api_requests=60, model_calls=12, checkpoint_installations=2, obligation_checkpoint_captures=2,
            obligation_notice_actor_calls=0 if mode == 'raw_anchor' else 2,
            obligation_entity_rows_exposed=24 if mode != 'raw_anchor' else 0,
            obligation_field_rows_exposed=24 if mode == 'entity_fields' else 0,
            obligation_queries=0, obligation_query_rejections=0,
            obligation_contract_failed=False, obligation_accounting_complete=True,
            obligation_runtime_wall_seconds=.035, obligation_final_enumeration='closed', usage_by_role=roles)
        if missing and rep == 2 and mode == 'raw_anchor':
            row.update(record_status='not_run', success=None, exact_total_tokens=None)
            for key in (*COUNT_FIELDS, *FLAGS, 'obligation_runtime_wall_seconds', 'obligation_final_enumeration', 'usage_by_role'):
                row[key] = None
        rows.append(row)
    return base_data(rows, synthetic=True, audit_errors=0, sources={}, evidence={}, server_wall=1800)


def load_redraw(args):
    require(args.figure_data is not None and args.original_manifest is not None
        and valid_hash(args.manifest_sha256), 'public data and trusted publication manifest SHA required')
    require(sha(args.original_manifest) == args.manifest_sha256, 'publication manifest digest required')
    manifest = read(args.original_manifest)
    # v02 accepts its own publication manifest, or only this fixed v01 lineage.
    original_layout_v01 = (
        args.manifest_sha256 == 'ed9c426056212d55354219218d52d1fb6bf980a9ed4e74103019634029d3cda1'
        and manifest['renderer_source_sha256'] == 'fd2d3e63500fb0f1d927663028230b3760518b00efca9184e05515179b5e3e81'
        and sha(args.figure_data) == '550d3dac9c41ad097807f09cefc717c7d3156dd9edae28bd5c67568c1ee4c05c')
    require(manifest['phase'] == 'P137' and
        (manifest['renderer_source_sha256'] == sha(__file__) or original_layout_v01),
        'exact v02 renderer or fixed v01 layout lineage required')
    require(manifest['figure_data_sha256'] == sha(args.figure_data)
        == manifest['artifact_sha256']['figure_data.json'], 'exact published figure data required')
    data = validate_data(read(args.figure_data))
    for key in ('synthetic', 'fixed_head', 'fixed_plan_sha256', 'fixed_independent_review_source_sha256',
        'source_binding_count', 'launch_registry_ledgers', 'launch_registry_bindings', 'source_sha256', 'evidence_sha256'):
        require(digest(manifest[key]) == digest(data[key]), 'public manifest data binding: ' + key)
    require(manifest.get('original_results_changed') is False
        and manifest.get('redraw_is_not_renewed_scientific_audit') is True, 'redraw limitations retained')
    return data


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--synthetic-preview', action='store_true')
    action.add_argument('--closed-once', action='store_true')
    action.add_argument('--redraw', action='store_true')
    parser.add_argument('--repo-root', type=Path)
    for name in ('collector-end', 'collector-start', 'closure', 'pipeline-start', 'independent-review',
        'output-dir', 'figure-data', 'original-manifest'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args()
    require(args.output_dir is not None, 'exclusive output directory required')
    # Do not inspect even completed evidence when this requested destination exists.
    require(not args.output_dir.exists() and not args.output_dir.is_symlink(), 'preserve existing output')
    lineage = None
    if args.synthetic_preview:
        data = synthetic()
    elif args.redraw:
        data = load_redraw(args)
        lineage = dict(original_manifest_sha256=args.manifest_sha256, figure_data_sha256=sha(args.figure_data))
    else:
        require(all(getattr(args, name) is not None for name in ('repo_root', *EVIDENCE_FIELDS)), 'closed evidence arguments required')
        data = load_closed(args)
    result = render(data, args.output_dir, redraw_lineage=lineage)
    print(json.dumps(dict(phase='P137', synthetic=data['synthetic'], artifacts=len(result['artifact_sha256']),
        figure_data_sha256=result['figure_data_sha256'], original_results_changed=False)))


if __name__ == '__main__':
    main()

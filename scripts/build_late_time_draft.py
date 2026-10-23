"""Prepare a P82 manuscript only from the closed full cohort, never live cells."""
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import build_late_clock_report_v02 as reporting
from build_budget_visibility_report import TASKS, cost, outcome, totals
from late_clock_comparison import POLICIES
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/late_time_control'


def validate_evidence(plan, report, session, stability, profile):
    """Require the actual pair identities, not just a count of 36 records."""
    rows = report['rows']
    expected = {frozenset((a['run_id'], b['run_id'])) for a, b in combinations(rows, 2)
        if a['task_id'] == b['task_id'] and (a['repetition'] == b['repetition']
            or a['time_visibility'] == b['time_visibility'])}
    actual = [frozenset(p['run_ids']) for p in stability['pairs']]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('all_thirty_six_distinct_planned_pairs_required')
    by_id = {r['run_id']: r for r in rows}
    for pair in stability['pairs']:
        a, b = [by_id[rid] for rid in pair['run_ids']]
        relation = 'same_policy_repetition' if a['time_visibility'] == b['time_visibility'] else 'within_repetition'
        if (pair['task_id'] != a['task_id'] or pair['relation'] != relation
                or pair['policies'] != [a['time_visibility'], b['time_visibility']]
                or pair['repetitions'] != [a['repetition'], b['repetition']]):
            raise ValueError('comparison_identity_metadata_disagrees')
    if set(stability['traces']) != {r['run_id'] for r in rows}:
        raise ValueError('all_twenty_four_trace_identities_required')
    for row in rows:
        t = stability['traces'][row['run_id']]
        if len(t['calls']) != row.get('model_calls', 0):
            raise ValueError('trace_attempt_count_disagrees')
        if row['time_visibility'] == 'late_half':
            positions = [i for i, c in enumerate(t['calls'], 1) if c.get('effective_time_visibility') == 'measured']
            if t.get('first_measured_notice_call') != (positions[0] if positions else None):
                raise ValueError('late_clock_transition_disagrees')
    if len(profile['calls']) != sum(r.get('model_calls', 0) for r in rows):
        raise ValueError('profile_attempt_count_disagrees')
    if (any(report[k] for k in ('additional_model_calls', 'additional_api_calls',
                                'additional_evaluator_calls', 'reserved_scenarios_read'))
            or profile['P80_P81_calls_included'] or stability['private_reasoning_inspected_semantically']):
        raise ValueError('new_P82_cohort_only_required')


def conclusion(report):
    passed = sum(c['development_gate_met'] for r in report['repetitions'] for c in r['comparisons'])
    if passed == 4:
        return ('固定した４比較すべてで開発上の採用基準を満たした．'
                'この判断は既知４課題・２反復での相対比較であり，一般的な品質維持や新手法の成立を意味しない．')
    return (f'採用基準を満たした比較は{passed}/4であり，両対照を両反復で上回るという固定基準は未達だった．'
            '条件を選び直した改善や，新手法の成立として扱わない．')


def numerical_sections(plan, report, session, stability, profile):
    validate_evidence(plan, report, session, stability, profile)
    rows = report['rows']
    result = [r'\begin{table}[tb]', r'\centering\footnotesize\setlength{\tabcolsep}{2pt}',
        r'\caption{全24条件の成否と論理入出力token．不明生成を０へ置換せず，未評価・未実行も残す．}',
        r'\begin{tabular}{lrrr}', r'課題・反復 & M & H & L \\ \hline']
    for n, task in enumerate(plan['known_tasks']):
        for rep in (1, 2):
            cells = [next(r for r in rows if r['task_id'] == task['task_id']
                and r['repetition'] == rep and r['time_visibility'] == p) for p in POLICIES]
            values = [r'\shortstack[r]{' + outcome(r) + f' {r["known_total_tokens"]:,}' +
                r'\\＋不明' + str(r['unknown_usage_calls']) + '}' if r.get('unknown_usage_calls')
                else outcome(r) + ' ' + cost(r) for r in cells]
            result.append(f'{TASKS[n]}{rep} & ' + ' & '.join(values) + r' \\')
    result += [r'\hline\end{tabular}', r'\end{table}', conclusion(report)]
    for rep in (1, 2):
        selected = [r for r in rows if r['repetition'] == rep]
        summary = [totals(selected, p) for p in POLICIES]
        result.append(f'反復{rep}のM/H/Lは，成功／評価数が順に' +
            '，'.join(f'{r["successes"]}/{r["evaluated"]}' for r in summary) +
            '，論理費用は' + '，'.join(cost(r) for r in summary) + ' tokenだった．')
    result += [r'\begin{table}[tb]', r'\centering\footnotesize\setlength{\tabcolsep}{3pt}',
        r'\caption{全４比較の費用差（L−対照）．両側成功・両側未達の寄与を分ける．不明使用量があれば確定差を求めない．}',
        r'\begin{tabular}{llrrr}', r'反復 & 対照 & 全課題 & 両側成功 & 両側未達 \\ \hline']
    signed = lambda v: '未確定' if v is None else f'{v:+,}'
    for rep in report['repetitions']:
        for c in rep['comparisons']:
            result.append(f'{rep["repetition"]} & ' + ('M' if c['baseline'] == 'measured' else 'H') + ' & ' +
                ' & '.join(signed(c[k]) for k in ('late_half_minus_'+c['baseline']+'_whole_task_tokens',
                    'paired_successful_token_difference', 'both_failed_token_difference')) + r' \\')
    result += [r'\hline\end{tabular}', r'\end{table}',
        '双方が未達の課題を安く終えた差は，完成に必要な費用の削減とは異なる．'
        '一方だけが成功した課題の差は全課題へ含むが，両側成功・両側未達の欄には含めない．']
    aggregate = [totals(rows, p) for p in POLICIES]
    known = sum(a['known_total_tokens'] for a in aggregate)
    unknown = sum(a['unknown_usage_calls'] for a in aggregate)
    result.append(f'全予定24条件のうち，費用記録があるのは{sum(a["measured"] for a in aggregate)}条件，'
        f'評価済みは{sum(a["evaluated"] for a in aggregate)}条件だった．'
        f'新規生成は{len(profile["calls"])}回，既知論理入出力{known:,} token，不明使用量{unknown}生成，'
        f'実API送信は{sum(a["api_requests"] for a in aggregate)}回だった．'
        f'推論器の全稼働は{session["wall_seconds"]:,.3f}秒，うちロードは{session["load_wall_seconds"]:.3f}秒，'
        f'各仕事の初期化・作業・後片付けの合計は{session["cell_full_wall_seconds"]:,.3f}秒，'
        f'評価合計は{session["evaluation_wall_seconds"]:.3f}秒だった．これらの時間は重複し，加算しない．')
    paths = [r'\begin{table}[tb]', r'\centering\small\setlength{\tabcolsep}{4pt}',
        r'\caption{同条件の反復間12対．一致数／使用量既知の判定可能対数と，判定可能数／全４対を示す．}',
        r'\begin{tabular}{lrrr}', r'条件 & 判定可能 & 全要求一致 & 全公開出力一致 \\ \hline']
    for policy, label in zip(POLICIES, ('M', 'H', 'L'), strict=True):
        pairs = [p for p in stability['pairs'] if p['relation'] == 'same_policy_repetition' and p['policies'][0] == policy]
        known_pairs = [p for p in pairs if p['both_known_complete']]
        counts = [f'{sum(p[k] is True for p in known_pairs)}/{len(known_pairs)}' if known_pairs else '未確定'
                  for k in ('all_requests_equal', 'all_public_outputs_equal')]
        paths.append(f'{label} & {len(known_pairs)}/4 & ' + ' & '.join(counts) + r' \\')
    paths += [r'\hline\end{tabular}', r'\end{table}', r'\begin{table}[tb]',
        r'\centering\small\setlength{\tabcolsep}{4pt}',
        r'\caption{全８件のLで最初に実測残時間を通知した生成番号．未到達は効果がないことの証明ではない．}',
        r'\begin{tabular}{lrr}', r'課題 & 反復1 & 反復2 \\ \hline']
    for n, task in enumerate(plan['known_tasks']):
        values = []
        for rep in (1, 2):
            row = next(r for r in rows if r['task_id'] == task['task_id'] and r['repetition'] == rep and r['time_visibility'] == 'late_half')
            trace = stability['traces'][row['run_id']]
            pos = trace.get('first_measured_notice_call')
            values.append(str(pos) if pos is not None else '未到達' if trace['calls'] else '未実行')
        paths.append(TASKS[n] + ' & ' + ' & '.join(values) + r' \\')
    paths += [r'\hline\end{tabular}', r'\end{table}',
        '反復間12対に加え，反復内の条件間24対を全件保存した．'
        'これら36対は同じ実行を共有し，独立標本ではない．'
        '現在の通知だけを揃えた補助照合は，過去の履歴差を消去せず，モデルtoken列や全仕事費用の因果効果を同定しない．']
    return {'results.tex': '\n'.join(result) + '\n', 'stability.tex': '\n'.join(paths) + '\n'}


def build():
    evidence = reporting.validated()
    plan, report, session, stability, profile = evidence
    for name, expected in plan['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('frozen_P82_dependency_changed:' + name)
    generated = numerical_sections(*evidence)
    folder = ROOT / FOLDER
    # Publish no draft PDF before the actual closed evidence exists.
    for name, content in generated.items():
        target = folder / name
        if target.exists() and target.read_text() != content:
            raise ValueError('preserve_generated_P82_table:' + name)
    for name, content in generated.items():
        (folder / name).write_text(content)
    inputs = [*reporting.FILES, 'scripts/build_late_time_draft.py',
        'scripts/render_late_time_draft.py', 'scripts/build_late_clock_report_v02.py', FOLDER + '/draft.tex',
        'reports/P81_interval_manuscript_provenance_20261024.json']
    sources = {**plan['source_sha256'], **{name: sha(ROOT / name) for name in inputs}}
    manifest = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=sources,
        generated_sha256={name: sha(folder / name) for name in generated},
        all_planned_rows=24, dependent_pairs=36, independent_tasks=4,
        all_repetition_gates_met=report['all_repetition_gates_met'],
        unknown_usage_imputed=False, authors_confirmed=False, submission_ready=False,
        professor_brief_changed=False, primary_manuscript_replaced=False,
        visual_reviewed=False, novel_method_claim=False, general_quality_preservation_claim=False)
    write_json(folder / 'build_manifest.json', manifest)
    print({k: manifest[k] for k in ('all_planned_rows', 'dependent_pairs', 'all_repetition_gates_met')})
    return manifest


if __name__ == '__main__':
    build()

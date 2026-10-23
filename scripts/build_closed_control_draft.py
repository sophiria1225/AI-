"""Join closed P82 and P84 evidence in a separate, bounded manuscript draft."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import build_late_clock_report_v02 as clock_report
import build_fallback_output_report as fallback_report
from build_late_time_draft import conclusion, numerical_sections, validate_evidence
from fallback_output_replay import CASES, equality_summary, schedule
from inspect_late_clock_usage_intervals import check_cells
from late_clock_comparison import summarize
from summarize_late_clock_resources import comparisons, resource_cells
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/closed_control_integration'
RESOURCE = 'materials/20261024_p82_resource_accounting/resource_accounting.json'


def signed_range(values):
    return f'[{values[0]:+,}, {values[1]:+,}]'


def sections(evidence, replay, resources):
    plan, report, session, stability, profile = evidence
    check_cells(report['rows'])
    validate_evidence(*evidence)
    decisions = summarize(report['rows'], [])
    if any(report.get(k) != v for k, v in decisions.items()):
        raise ValueError('original_P82_decisions_required')
    attempted = replay['model_calls_attempted']
    if (len(replay['rows']) != 18 or not 0 <= attempted <= 18
            or any({k: r[k] for k in item} != item
                   for r, item in zip(replay['rows'], schedule(), strict=True))
            or equality_summary(replay['rows'][:attempted]) != replay['equality_summary']):
        raise ValueError('all_eighteen_planned_replay_slots_required')
    usable = (replay['all_eighteen_audited']
              and replay['equality_summary']['stable_complete_public_outputs_and_equivalent_input_controls'] is True)
    effect = replay['equality_summary']['original_fallback_ID_pair_public_outputs_differ'] if usable else None
    if replay['diagnostic_usable'] != usable or replay['local_public_output_difference_identified'] != effect:
        raise ValueError('no_local_effect_claim_beyond_closed_diagnostic')
    # Keep the complete 24-cell table, but avoid four duplicative tables in the letter.
    previous = numerical_sections(*evidence)['results.tex']
    table = previous.split(r'\end{table}', 1)[0] + '\n' + r'\end{table}'
    rows = report['rows']
    all_known = sum(r['known_total_tokens'] for r in rows)
    unknown = sum(r['unknown_usage_calls'] for r in rows)
    text = [table, conclusion(report)]
    for repetition in report['repetitions']:
        values = [('M' if c['baseline'] == 'measured' else 'H') + 'に対し' +
                  ('達成' if c['development_gate_met'] else '未達') for c in repetition['comparisons']]
        text.append(f'反復{repetition["repetition"]}の固定基準は' + '，'.join(values) + 'であった．')
    for rep in (1, 2):
        counts = [sum(r['success'] for r in rows if r['repetition'] == rep and r['time_visibility'] == p)
                  for p in ('measured', 'not_exposed', 'late_half')]
        text.append(f'反復{rep}のM/H/Lの成功数は{counts[0]}/4，{counts[1]}/4，{counts[2]}/4であった．')
    text.append(f'全24条件で{sum(r["model_calls"] for r in rows)}生成，既知{all_known:,}論理token，'
                f'使用量不明{unknown}生成，{sum(r["api_requests"] for r in rows)} API送信を記録した．'
                f'所有推論器の稼働は{session["wall_seconds"]:,.3f}秒，'
                f'うち読込{session["load_wall_seconds"]:.3f}秒，評価{session["evaluation_wall_seconds"]:.3f}秒であった．'
                f'仕事ごとの準備・作業・後片付けの合計は{session["cell_full_wall_seconds"]:,.3f}秒であり，'
                'これらは重なりを持つため加算しない．')
    if resources is None:
        text.append('補助的な資源区間は本稿に含めず，欠測を含む全費用差を既知分だけから推定しない．')
    else:
        if (resources['original_decisions'] != decisions
                or resources['comparisons'] != comparisons(resources['rows'])
                or [r['run_id'] for r in resources['rows']] != [r['run_id'] for r in rows]):
            raise ValueError('complete_matching_resource_comparisons_required')
        for old, resource in zip(rows, resources['rows'], strict=True):
            if any(old[k] != resource[k] for k in ('repetition', 'task_id', 'time_visibility', 'success',
                    'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'wall_seconds')):
                raise ValueError('resource_and_primary_cohort_disagree')
        text.append('以下は全件監査後の保存ログに基づく事後の条件付き区間である．'
                    '入力計数と生成進捗・要求上限の対応を全既知レシートで照合し，不明cache量は可能範囲を残した．')
        for baseline, label in (('measured', 'M'), ('not_exposed', 'H')):
            pair = next(c for c in resources['comparisons'] if c['repetition'] == 'combined'
                        and c['baseline'] == baseline and c['category'] == 'total')
            values = pair['late_half_minus_baseline_intervals']
            text.append(f'２反復合計のL−{label}は，論理tokenが' + signed_range(values['logical_tokens']) +
                        '，cacheを除く入力tokenが' + signed_range(values['uncached_input_tokens']) +
                        '，出力tokenが' + signed_range(values['output_tokens']) +
                        f'であった．作業時間の実測差は{pair["observed_late_half_minus_baseline"]["wall_seconds"]:+,.3f}秒であった．')
        text.append('これらは信頼区間やGPU計算量ではなく，使用量が既知になったことも意味しない．'
                    '失敗同士・成功同士・成否不一致の全区分は補足記録に残し，元の採否は変更しない．')
    paths = []
    for policy, label in (('measured', 'M'), ('not_exposed', 'H'), ('late_half', 'L')):
        pairs = [p for p in stability['pairs'] if p['relation'] == 'same_policy_repetition' and p['policies'][0] == policy]
        known = [p for p in pairs if p['both_known_complete']]
        request_equal = sum(p['all_requests_equal'] is True for p in known)
        output_equal = sum(p['all_public_outputs_equal'] is True for p in known)
        paths.append(f'{label}の反復間は全４対中{len(known)}対が判定可能で，'
                     f'そのうち全要求一致は{request_equal}対，全公開出力一致は{output_equal}対であった．')
    transitions = []
    for number, task in enumerate(plan['known_tasks'], 1):
        positions = []
        for rep in (1, 2):
            row = next(r for r in rows if r['task_id'] == task['task_id']
                       and r['repetition'] == rep and r['time_visibility'] == 'late_half')
            pos = stability['traces'][row['run_id']]['first_measured_notice_call']
            positions.append(str(pos) if pos is not None else '未到達')
        transitions.append(f'課題{number}は' + '/'.join(positions))
    paths.append('Lで最初に実測残時間を通知した生成番号は反復1/2の順で，' + '，'.join(transitions) + 'であった．')
    paths.append('同条件の反復間12対と，反復内の条件間24対を全て記録した．'
                 '36対は実行を共有しており，独立標本数ではない．一致数は判定可能な対に限り，欠測側を一致扱いしない．')
    summary = replay['equality_summary']
    local = [r'\begin{table}[tb]', r'\centering\footnotesize\setlength{\tabcolsep}{3pt}',
             r'\caption{保存入力の全６条件．各３予定生成．公開一致は既知使用量の比較可能対だけの一致数である．}',
             r'\begin{tabular}{lrrrr}', r'入力 & 試行 & 既知 & 完全非空 & 公開一致 \\ \hline']
    for code, case in zip(('A', 'B', 'C', 'D', 'N', 'X'), CASES, strict=True):
        group = summary['within'][case]
        complete = sum(r.get('status') == 'ok' and r.get('complete_generation') is True
                       and r.get('has_public_output') is True for r in replay['rows'] if r['case'] == case)
        local.append(f'{code} & {group["attempted"]}/3 & {group["known"]}/3 & {complete}/3 & '
                     f'{group["equal_public_pairs"]}/{group["compared_pairs"]}' + r' \\')
    local += [r'\hline\end{tabular}', r'\end{table}', fallback_report.outcome(replay).replace('。', '．')]
    for left, right, label in ((CASES[0], CASES[1], 'A/B'), (CASES[2], CASES[3], 'C/D'), (CASES[0], CASES[4], 'A/N')):
        pair = next(p for p in summary['cross'] if p['left'] == left and p['right'] == right)
        local.append(f'{label}の公開出力一致は{pair["equal_public_pairs"]}/{pair["compared_pairs"]}対であった．')
    local.append(f'全18予定枠中{attempted}生成を試行し，既知{replay["known_total_tokens"]:,}論理token，'
                 f'使用量不明{replay["unknown_usage_calls"]}生成を記録した．'
                 f'所有推論器の稼働は{replay["server"]["wall_seconds"]:,.3f}秒であった．'
                 '全15組の比較と返却message全体の不透明hash照合を補足記録に保持し，内部推論の意味内容は読まない．'
                 '一致する出力が正しいことや，継続後の品質が保たれることは判定していない．')
    return {'whole_task.tex': '\n'.join(text) + '\n', 'trajectories.tex': '\n'.join(paths) + '\n',
            'local_replay.tex': '\n'.join(local) + '\n'}


def build(without_resource_intervals=False):
    folder = ROOT / FOLDER
    if (folder / 'build_manifest.json').exists():
        raise FileExistsError('preserve_closed_integration_attempt')
    evidence = clock_report.validated()
    if evidence[1]['batch_status'] != 'complete':
        raise ValueError('wait_for_the_complete_P82_cohort')
    _, _, replay, p84_sources = fallback_report.validated(ROOT)
    resources = None if without_resource_intervals else read(ROOT / RESOURCE)
    inputs = set(clock_report.FILES) | set(p84_sources)
    inputs.update((FOLDER + '/draft.tex', 'scripts/build_closed_control_draft.py',
                   'scripts/render_bound_letter_draft.py', 'scripts/build_late_time_draft.py',
                   'reports/resource_prior_review_provenance_20261024.json'))
    frozen = dict(evidence[0]['source_sha256'])
    frozen.update(read(ROOT / 'reports/resource_prior_review_provenance_20261024.json')['source_sha256'])
    if resources is not None:
        inputs.add(RESOURCE)
        frozen.update(resources['source_sha256'])
        intervals = read(ROOT / 'reports/P82_usage_intervals_20261024.json')
        expected_rows, expected_decisions = resource_cells(evidence[1]['rows'], intervals['rows'])
        if resources['rows'] != expected_rows or resources['original_decisions'] != expected_decisions:
            raise ValueError('resource_ranges_must_match_all_closed_calls')
    for name, expected in frozen.items():
        if sha(ROOT / name) != expected:
            raise ValueError('closed_bound_evidence_changed:' + name)
    generated = sections(evidence, replay, resources)
    if any((folder / name).exists() for name in generated):
        raise FileExistsError('preserve_generated_integration_tables')
    for name, text in generated.items():
        with (folder / name).open('x') as stream: stream.write(text)
    manifest = dict(generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256={**frozen, **{name: sha(ROOT / name) for name in sorted(inputs)}},
        generated_sha256={name: sha(folder / name) for name in generated},
        P82_planned_cells=24, P82_dependent_pairs=36, independent_tasks=4,
        P84_planned_generations=18, P84_case_contrasts=15,
        P82_all_repetition_gates_met=evidence[1]['all_repetition_gates_met'],
        P84_diagnostic_usable=replay['diagnostic_usable'],
        resource_intervals_included=resources is not None,
        unknown_usage_imputed=False, original_adoption_gate_changed=False,
        novel_method_claim=False, general_quality_preservation_claim=False,
        authors_confirmed=False, official_journal_class=False, submission_ready=False,
        professor_brief_changed=False, visual_reviewed=False,
        additional_generations=0, additional_api_requests=0, additional_evaluations=0)
    with (folder / 'build_manifest.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print({key: manifest[key] for key in ('P82_planned_cells', 'P84_planned_generations',
                                        'resource_intervals_included', 'P84_diagnostic_usable')})
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-resource-intervals', action='store_true',
                        help='Explicitly omit optional intervals if they could not be established; never repair missing usage.')
    args = parser.parse_args()
    build(args.without_resource_intervals)

"""Generate manuscript tables only from the closed, audited 24-row cohort."""
from datetime import datetime, timezone
from pathlib import Path

from budget_observation import POLICIES
from build_budget_visibility_report import totals
from build_budget_visibility_repetition_report import FILES, validated
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FOLDER = 'papers/202610_letter/time_visibility_repetitions'


def token_text(row):
    if row.get('known_total_tokens') is None:
        return '未計測'
    value = f'{row["known_total_tokens"]:,}'
    if row['unknown_usage_calls']:
        value += r'$+?_{' + str(row['unknown_usage_calls']) + '}$'
    return value


def cell(row):
    if row['record_status'] != 'evaluated':
        label = '未実行' if row['record_status'] == 'not_run' else '未評価'
    else:
        label = '成' if row['success'] else '否'
    return token_text(row) + ' ' + label


def build():
    plan, report, stability, session = validated()
    folder = ROOT / FOLDER
    generated = ('results.tex', 'stability.tex')
    if any((folder / name).exists() for name in (*generated, 'build_manifest.json')):
        raise FileExistsError('preserve_first_full_repetition_draft')
    local = read(ROOT / 'reports/P79_clock_notice_replay.json')
    if (not local['all_twelve_audited'] or local['audit_errors']
            or local['model_calls_attempted'] != 12 or local['known_total_tokens'] != 99966
            or any(local[k] for k in ('unknown_usage_calls', 'environment_api_requests',
                                      'generated_programs_executed', 'evaluations'))):
        raise ValueError('local_calibration_changed')
    bound_path = 'reports/P80_usage_lower_bounds_20261024.json'
    bound = read(ROOT / bound_path)
    provenance = read(ROOT / 'reports/P80_bound_and_P81_start_provenance_20261024.json')
    if sha(ROOT / bound_path) != provenance['source_sha256'][bound_path]:
        raise ValueError('supplemental_conditional_bound_changed')
    if (bound['complete_terminal_usage_recovered'] is not False
            or bound['original_unknown_usage_preserved'] != 1):
        raise ValueError('do_not_repair_original_terminal_usage')
    rows = [{**r, 'repetition': 1} for r in report['anchor_rows']] + report['rows']
    table = [r'\begin{table}[tb]', r'\centering\scriptsize\setlength{\tabcolsep}{2pt}',
        r'\caption{全24条件の論理tokenと成否．成：成功，否：未達．$+?_{n}$は別に使用量不明が$n$生成あることを示す．M：残時間表示，H：非表示．}',
        r'\begin{tabular}{llrrr}', r'課題 & 条件 & 反復1（P80） & 反復2 & 反復3 \\ \hline']
    matching = [r'\begin{table}[tb]', r'\centering\small\setlength{\tabcolsep}{3pt}',
        r'\caption{全８条件の対比較．既知は両実行の全使用量が既知の対数／３．要求・出力は一致対数／判定対数．時計は最初の要求差が現在の時計欄だけだった観測対数．}',
        r'\begin{tabular}{llrrrr}', r'課題 & 条件 & 既知 & 要求 & 公開出力 & 時計 \\ \hline']
    for task, name in zip(plan['known_tasks'], ('写真', '精算', '返金', '書出し'), strict=True):
        for policy, label in zip(POLICIES, ('M', 'H'), strict=True):
            group = sorted([r for r in rows if r['task_id'] == task['task_id']
                            and r['time_visibility'] == policy], key=lambda r: r['repetition'])
            if len(group) != 3:
                raise ValueError('all_three_repetitions_required')
            table.append(' & '.join([name, label] + [cell(r) for r in group]) + r' \\')
            pairs = [p for p in stability['pairs'] if p['task_id'] == task['task_id']
                     and p['time_visibility'] == policy]
            if len(pairs) != 3:
                raise ValueError('all_dependent_pairs_required')
            complete = sum(p['both_known_complete'] for p in pairs)
            def ratio(key):
                return f'{sum(p[key] is True for p in pairs)}/{complete}' if complete else '未確定'
            matching.append(' & '.join((name, label, f'{complete}/3', ratio('all_requests_equal'),
                ratio('all_public_outputs_equal'),
                str(sum(p['first_request_difference_is_current_wall_only'] is True for p in pairs)))) + r' \\')
    for text in (table, matching):
        text.extend([r'\hline', r'\end{tabular}', r'\end{table}'])
    for rep, gate in zip((1, 2, 3), report['repetitions'], strict=True):
        a, b = [totals([r for r in rows if r['repetition'] == rep], p) for p in POLICIES]
        table.append(f'反復{rep}はMが{a["evaluated"]}評価中{a["successes"]}成功，'
            f'Hが{b["evaluated"]}評価中{b["successes"]}成功で，'
            f'全論理tokenは順に{token_text(a)}，{token_text(b)}だった．')
        delta = gate['not_exposed_minus_measured_whole_task_tokens']
        table.append('全費用差は使用量不明または未実行のため未確定である．' if delta is None else
                     f'H−Mの合計差は{delta:+,} tokenである．')
        table.append('開発上の採用基準は' + ('達成' if gate['development_gate_met'] else '未達') +
            f'で，作業時間合計はM {a["wall_seconds"]:,.1f}秒，H {b["wall_seconds"]:,.1f}秒だった．')
    table.append('元のP80にはHの書出し中断による使用量不明１生成がある．'
        '事後の補助解析では，単一slotで直列に実行した全143送信を推論器ログへ順序対応させ，'
        '既知142生成の入力処理量と出力量を照合した．'
        '元の終端使用量を復元したものではないが，同じ送信の事前入力計数と'
        '生成開始後の単調な出力計数を使えるという前提では，'
        f'Hの論理費用は{bound["logical_token_lower_bounds"]["not_exposed"]:,}以上となり，'
        f'Mの{bound["measured_complete_total"]:,}を少なくとも'
        f'{bound["not_exposed_minus_measured_lower_bound"]:,}上回る．'
        '順序対応は要求IDの暗号学的な結合ではなく，未知費用は元表に残す．')
    table.append(f'追加P81の推論器滞在は{session["wall_seconds"]:,.1f}秒，'
        f'この内の評価時間は{session["evaluation_wall_seconds"]:.2f}秒だった．'
        '時間は重なるため合算しない．Hの初回入力は全課題でMより12 token多い．'
        '全生成，API，cache，準備・作業・後片付けと評価の全件表を公開記録へ保存する．')
    matching.append('要求列または公開出力列の完全一致は，全使用量が既知で比較できた対について示す．'
        '不明生成を含む対の全体一致は未確定とし，判定できた接頭部だけを全体へ広げない．'
        '時計欄以外をそろえた照合は観測された最初の要求差だけに関する結果であり，'
        '出力変化や全仕事費用の原因を単独で決める証拠ではない．')
    for name, lines in zip(generated, (table, matching), strict=True):
        (folder / name).write_text('\n'.join(lines) + '\n')
    sources = (*FILES, 'reports/P79_clock_notice_replay.json', bound_path,
        'reports/P80_bound_and_P81_start_provenance_20261024.json',
        'reports/P73_stop_diagnosis.json', FOLDER + '/draft.tex')
    manifest = {'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {name: sha(ROOT / name) for name in sources},
        'builder_sha256': sha(Path(__file__)),
        'generated_sha256': {name: sha(folder / name) for name in generated},
        'all_planned_rows': 24, 'dependent_pairs': 24, 'independent_tasks': 4,
        'primary_manuscript_replaced': False, 'professor_brief_changed': False,
        'authors_confirmed': False, 'submission_ready': False, 'visual_reviewed': False,
        'novel_method_claim': False, 'general_quality_preservation_claim': False}
    write_json(folder / 'build_manifest.json', manifest)
    print({'rows': 24, 'pairs': 24, 'independent_tasks': 4, 'primary_manuscript_replaced': False})


if __name__ == '__main__':
    build()

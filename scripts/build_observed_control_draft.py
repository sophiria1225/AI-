"""Add observed P82 resources and closed P84 conclusions to a separate draft.

The failed conditional-interval analysis is preserved. Missing usage is never
filled, and a local output match or difference is not treated as task quality.
"""
from datetime import datetime, timezone
import json

import build_closed_control_draft as base
from run_handoff_factors import ROOT, read, sha
from summarize_late_clock_observed_resources import aggregate, comparisons, observed_rows, POLICIES

FOLDER = 'papers/202610_letter/observed_control_results'
OBSERVED = 'materials/20261024_p82_observed_resources/observed_resources.json'
FAILURE = 'reports/P82_interval_failure_20261024.json'


def checked_observed(audit, observed):
    rows = observed_rows(audit['rows'])
    decisions = base.summarize(audit['rows'], [])
    if (observed['rows'] != rows or observed['comparisons'] != comparisons(rows)
            or observed['totals'] != {p: aggregate([r for r in rows if r['time_visibility'] == p]) for p in POLICIES}
            or observed['original_decisions'] != decisions
            or any(observed[k] for k in ('terminal_usage_imputed', 'failed_interval_method_retried',
                                         'conditional_server_log_intervals_reported'))):
        raise ValueError('observed_resources_must_match_all_closed_receipts')
    return observed['comparisons']


def quantity(value):
    if value['missing_usage_imputed']:
        raise ValueError('no_usage_imputation')
    if value['kind'] == 'unidentified':
        if value['value'] is not None:
            raise ValueError('unidentified_difference_has_no_value')
        return '未確定'
    symbols = {'exact': '', 'lower_bound': r'\geq ', 'upper_bound': r'\leq '}
    return '$' + symbols[value['kind']] + f'{value["value"]:+,}' + '$'


def resource_section(audit, observed):
    groups = checked_observed(audit, observed)
    def pick(baseline, category):
        return next(g for g in groups if g['repetition'] == 'combined'
                    and g['baseline'] == baseline and g['category'] == category)
    lines = [
        '保存ログからの狭い条件付き区間は，Hの欠測２生成に正の生成進捗がなく前提不成立となった．'
        '欠測４件は残し，以下は公開レシートと非負性だけを使った事後集計である．',
        r'\begin{table}[tb]', r'\centering\footnotesize\setlength{\tabcolsep}{3pt}',
        r'\caption{２反復全件のLと各対照との差．下限は欠測計数の非負性だけによる．時間は実測差である．}',
        r'\begin{tabular}{lrr}', r'測定 & L−M & L−H \\ \hline']
    totals = [pick(p, 'total') for p in POLICIES[:2]]
    for key, label in (('logical_tokens', '論理token'), ('uncached_input_tokens', 'cache除外入力'),
                       ('output_tokens', '出力token')):
        lines.append(label + ' & ' + ' & '.join(quantity(g['late_half_minus_baseline'][key]) for g in totals) + r' \\')
    lines.append('作業秒 & ' + ' & '.join(f'{g["observed_differences"]["wall_seconds"]:+,.3f}' for g in totals) + r' \\')
    lines += [r'\hline\end{tabular}', r'\end{table}']
    success, failure, discordant = [pick('measured', c) for c in ('both_success', 'both_failure', 'discordant')]
    descriptions = []
    for label, group in (('成功同士', success), ('失敗同士', failure), ('成否不一致', discordant)):
        descriptions.append(f'{label}{group["paired_task_observations"]}組では' +
                            quantity(group['late_half_minus_baseline']['logical_tokens']))
    lines.append('L−Mの論理token差は，' + '，'.join(descriptions) + 'であった．'
                 '各区分は同じ４課題の反復を含み，独立標本ではない．'
                 '成功部分の減少を全仕事へ拡張せず，Mの成功喪失も保持する．')
    lines.append('L−Hは両側に欠測があるため既知部分の差を全費用差へ読み替えない．'
                 '片側境界は信頼区間ではなく，GPU演算量，消費電力，課金，因果的な高速化も測っていない．')
    return '\n'.join(lines) + '\n'


def closing_text(audit, replay):
    if audit['all_repetition_gates_met'] is not False:
        raise ValueError('this_draft_is_for_the_closed_rejected_P82_candidate')
    usable, effect = replay['diagnostic_usable'], replay['local_public_output_difference_identified']
    if (type(usable) is not bool or (usable and type(effect) is not bool)
            or (not usable and effect is not None)):
        raise ValueError('closed_local_diagnostic_state_required')
    if not usable:
        ja_local = '保存文脈の次出力比較は固定した判定条件を満たさなかった.'
        en_local = 'The saved-context comparison did not meet its fixed diagnostic criteria.'
    elif effect:
        ja_local = '１保存文脈で参照ID差に伴う次出力差を確認した.'
        en_local = 'Reference-ID variants produced different next outputs in one saved context.'
    else:
        ja_local = '１保存文脈では参照IDが異なる元入力の次出力も一致した.'
        en_local = 'Original reference-ID variants produced matching next outputs in one saved context.'
    ja = '状態保持型LLMエージェントの通知と参照表現を評価した. 既知４課題24条件で後半通知の全仕事費用改善は示せなかった. ' + ja_local
    en = ('We evaluated notices and references in stateful LLM agents. Late notices did not demonstrate '
          'whole-task cost improvement across 24 conditions on four known tasks. ' + en_local +
          ' These observations do not establish general quality preservation.')
    if len(ja) > 120 or len(en.split()) > 50:
        raise ValueError('closed_abstract_length_limit')
    ending = ('後半通知は固定した全４採用基準を満たさず，全仕事費用の改善として採用しない．' +
              base.fallback_report.outcome(replay).replace('。', '．') +
              '通知・参照の整合を課題成功や費用削減へ読み替えず，未達と使用量の欠測も残す．'
              '今回の既知課題と１保存文脈だけから，一般的な品質維持や新規な制御手法の有効性は結論できない．\n')
    return ja, en, ending


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('single_known_template_boundary_required')
    return text.replace(old, new, 1)


def draft_source(source, ja, en):
    old_ja = source.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    old_en = source.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    source = replace_once(replace_once(source, old_ja, ja), old_en, en)
    source = source.replace(base.FOLDER + '/', FOLDER + '/')
    source = replace_once(source, '% Prepared template: no real numerical sections are generated before closure.',
                          '% Closed P82/P84 results with observed resource accounting; not submission-ready.')
    marker = '\\input{' + FOLDER + '/trajectories.tex}'
    source = replace_once(source, marker, marker + '\n\\input{' + FOLDER + '/observed_resources.tex}')
    source = replace_once(source, '途中切れ，空出力，揺れ，欠測，未実行を除外して判定可能扱いしない．',
                          'ここで完全とは出力上限による終了でないことであり，構文の妥当性や実行可能性ではない．'
                          '途中切れ，空出力，揺れ，欠測，未実行を除外して判定可能扱いしない．')
    source = replace_once(source, '% The verified bibliography is appended from the closed prior-review draft.',
                          '\\section{結論}\n\\input{' + FOLDER + '/conclusion.tex}\n\n'
                          '% The verified bibliography is retained from the closed prior-review draft.')
    return source


def build():
    folder = ROOT / FOLDER
    if folder.exists():
        raise FileExistsError('preserve_observed_control_draft_attempt')
    old_manifest = read(ROOT / base.FOLDER / 'build_manifest.json')
    if old_manifest['resource_intervals_included'] is not False:
        raise ValueError('explicit_omission_of_failed_intervals_required')
    sources = dict(old_manifest['source_sha256'])
    sources.update({base.FOLDER + '/' + n: digest for n, digest in old_manifest['generated_sha256'].items()})
    # Verify the prior binding before merging later ledgers that share paths.
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('bound_base_draft_source_changed:' + name)
    observed, failure = read(ROOT / OBSERVED), read(ROOT / FAILURE)
    sources.update(observed['source_sha256'])
    sources.update(failure['source_sha256'])
    sources.update({n: sha(ROOT / n) for n in (OBSERVED, FAILURE, base.FOLDER + '/build_manifest.json',
                   'scripts/build_observed_control_draft.py', 'scripts/render_bound_letter_draft.py')})
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('bound_observed_control_source_changed:' + name)
    if (failure['original_interval_result_created'] is not False
            or failure['original_method_changed'] is not False
            or failure['prepared_resource_analysis_run'] is not False):
        raise ValueError('preserved_failed_interval_attempt_required')
    evidence = base.clock_report.validated()
    if evidence[1]['batch_status'] != 'complete':
        raise ValueError('closed_P82_required')
    _, _, replay, _ = base.fallback_report.validated(ROOT)
    sections = base.sections(evidence, replay, None)
    for name, text in sections.items():
        if text != (ROOT / base.FOLDER / name).read_text():
            raise ValueError('closed_base_section_mismatch:' + name)
    sections['observed_resources.tex'] = resource_section(evidence[1], observed)
    ja, en, sections['conclusion.tex'] = closing_text(evidence[1], replay)
    source = draft_source((ROOT / base.FOLDER / 'draft.tex').read_text(), ja, en)
    sections['draft.tex'] = source
    folder.mkdir(parents=True, exist_ok=False)
    for name, text in sections.items():
        with (folder / name).open('x') as f: f.write(text)
    manifest = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=sources,
        generated_sha256={n: sha(folder / n) for n in sections}, P82_planned_cells=24,
        P84_planned_generations=18, P84_case_contrasts=15, independent_tasks=4,
        P82_all_repetition_gates_met=False, P84_diagnostic_usable=replay['diagnostic_usable'],
        P84_local_public_output_difference_identified=replay['local_public_output_difference_identified'],
        resource_intervals_included=False, observed_resource_accounting_included=True,
        conditional_interval_failure_preserved=True, unknown_usage_imputed=False,
        original_adoption_gate_changed=False, novel_method_claim=False,
        general_quality_preservation_claim=False, authors_confirmed=False,
        official_journal_class=False, submission_ready=False, professor_brief_changed=False,
        visual_reviewed=False, additional_generations=0, additional_api_requests=0, additional_evaluations=0)
    with (folder / 'build_manifest.json').open('x') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2); f.write('\n')
    print({'folder': FOLDER, 'ja_characters': len(ja), 'en_words': len(en.split()),
           'diagnostic_usable': replay['diagnostic_usable']})
    return manifest


if __name__ == '__main__':
    build()

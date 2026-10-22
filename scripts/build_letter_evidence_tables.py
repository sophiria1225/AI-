"""Render auditable tables for a provisional evidence manuscript, no new runs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'papers/202610_letter'
SOURCES = ['reports/P33_comparison.json', 'reports/P33_cost_profile.json',
           'reports/P33_prefix_checks.json', 'reports/P33_cost_decomposition.json',
           'reports/P47_comparison.json', 'reports/P49_repair_binding.json',
           'reports/P50_baseline_repair_census.json']


def main():
    data = {p: json.loads((ROOT / p).read_text()) for p in SOURCES}
    p33, p47 = data[SOURCES[0]], data[SOURCES[4]]
    if not p33['all_twelve_reviewed'] or p33['audit_errors']:
        raise ValueError('incomplete P33 audit')
    if not p47['all_planned_cells_accounted'] or p47['audit_errors']:
        raise ValueError('incomplete P47 accounting')
    if len(p33['rows']) != 12 or len(p47['rows']) != 12:
        raise ValueError('missing planned cell')
    arms = ['full_keep', 'stdout_mask_keep', 'stdout_mask_index_keep']
    lines = ['% Generated from audited reports; edit the builder, not these tables.']
    lines += [r'\newcommand{\EvidencePThirtyThreeTotals}{%',
        r'\begin{tabular}{lrrr}\hline 指標 & 全表示 & 省略 & 一覧付\\\hline']
    values = [p33['totals'][a] for a in arms]
    rows = [
        ('成功', [f"{v['successes']}/4" for v in values]),
        ('初回入力', [f"{sum(r['views'][a]['input_tokens'] for r in data[SOURCES[2]]['rows']):,}" for a in arms]),
        ('継続総token', [f"{v['known_total_tokens']:,}" for v in values]),
        ('AI呼出し', [str(v['model_calls']) for v in values]),
        ('継続API', [str(v['api_requests']) for v in values]),
        ('実験用復元API', [str(v['setup_api_requests']) for v in values]),
        ('処理入力token', [f"{data[SOURCES[1]]['by_arm'][a]['totals']['processed_input_tokens']:,}" for a in arms]),
        ('出力token', [f"{data[SOURCES[1]]['by_arm'][a]['totals']['output_tokens']:,}" for a in arms]),
        ('継続時間(s)', [f"{v['continuation_wall_seconds']:,.1f}" for v in values]),
    ]
    lines += [name + ' & ' + ' & '.join(vals) + r'\\' for name, vals in rows]
    lines += [r'\hline\end{tabular}}']
    task_names = {'34d9492_1':'写真整理', '3c13f5a_1':'共有・依頼',
                  '60d0b5b_1':'返金', '6104387_1':'曲一覧書出'}
    for macro, report, selected in [('EvidencePThirtyThreeTasks', p33, arms),
            ('EvidencePFortySevenTasks', p47,
             ['full_contract_keep', 'selected_names_keep', 'selected_contract_keep'])]:
        lines += [f'\\newcommand{{\\{macro}}}{{%',
                  r'\begin{tabular}{llrr}\hline 課題 & 条件・成否 & token & AI\\\hline']
        for task, title in task_names.items():
            for index, arm in enumerate(selected):
                row = next(r for r in report['rows'] if r['task_id'] == task and r['arm'] == arm)
                status = row.get('record_status', 'evaluated')
                label = ('F', 'M', 'I')[index] if report is p33 else ('F', 'N', 'S')[index]
                outcome = ('成功' if row['success'] else '未達') if status == 'evaluated' else (
                          '未評価' if status == 'attempted_unevaluated' else '未実行')
                cost = f"{row['known_total_tokens']:,}"
                calls = str(row['model_calls'])
                if status == 'not_run_after_stop':
                    cost = calls = '---'
                elif row['unknown_usage_calls']:
                    cost += r'$+?$'
                lines.append(f'{title if index == 0 else ""} & {label}・{outcome} & {cost} & {calls}' + r'\\')
        lines += [r'\hline\end{tabular}}']
    table_path = OUT / 'evidence_tables.tex'
    table_path.write_text('\n'.join(lines) + '\n')
    source_map = {'kind':'provisional_evidence_manuscript_not_submission_ready',
        'sources':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
        'generated_table_sha256':hashlib.sha256(table_path.read_bytes()).hexdigest(),
        'all_P33_cells':12, 'all_P47_cells':12,
        'new_model_calls':0,'new_api_requests':0,'novelty_established':False,
        'official_class_used':False, 'author_details_supplied':False,
        'limits':['P33 predates normalized first-call cache control.',
            'P47 differs in intervention and budget controls; no cross-phase causal subtraction.',
            'Incomplete P47 cells remain unknown or not run; no zero-cost substitution.',
            'Algebraic cost decomposition is descriptive, not a causal estimator.']}
    map_path = OUT / 'evidence_draft_source_map.json'
    if map_path.exists():
        previous = json.loads(map_path.read_text())
        unchanged = (previous.get('sources') == source_map['sources']
                     and previous.get('generated_table_sha256') == source_map['generated_table_sha256'])
        artifacts = previous.get('artifact_sha256', {})
        rendering_matches = bool(artifacts) and all(
            (ROOT / name).exists() and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
            for name, digest in artifacts.items() if name != 'scripts/build_letter_evidence_tables.py')
        if unchanged and rendering_matches:
            source_map = {**previous, **source_map, 'rendering_up_to_date': True}
            source_map['artifact_sha256']['scripts/build_letter_evidence_tables.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        else:
            source_map['rendering_up_to_date'] = False
    map_path.write_text(json.dumps(source_map,ensure_ascii=False,indent=2)+'\n')
    print('Generated tables from seven audited reports; no model/API calls.')


if __name__ == '__main__':
    main()

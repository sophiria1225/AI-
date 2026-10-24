"""Report all P99 outcomes, costs and submission records after cohort closure."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from build_budget_visibility_report import TASKS, outcome
from build_budget_visibility_repetition_report import table
from whole_task_tool_choice import POLICIES, cell_id, run_order, summarize, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_whole_task_tool_choice_20261024'
LABELS = ('A 任意提出', 'R 必須提出')
FILES = ('configs/P99_whole_task_tool_choice_v01.json', 'reports/P99_comparison.json',
         'reports/P99_initial_checks.json', 'reports/P99_server_session.json',
         'reports/P99_activation_v01.json', 'reports/P99_start_provenance_20261024.json')


def validated(root=ROOT):
    plan, report, pre, session, activation, start = [read(root / name) for name in FILES]
    validate_plan(plan)
    expected = [(cell_id(n, p), plan['known_tasks'][n-1]['task_id'], p) for n, p in run_order()]
    if ([(r['run_id'], r['task_id'], r['tool_choice_policy']) for r in report['rows']] != expected
            or report['audit_errors'] or report['batch_status'] not in ('complete', 'stopped')
            or report['plan_sha256'] != sha(root / FILES[0])
            or report['activation_sha256'] != sha(root / FILES[4])
            or not report['owned_processes_absent']
            or pre['status'] != 'complete' or not pre['all_eight_inputs_checked']
            or pre['input_count_requests'] != 8 or pre['failed_input_count_requests']
            or pre['git_commit'] != start['head']
            or type(start['head']) is not str or len(start['head']) != 40
            or any(c not in '0123456789abcdef' for c in start['head'])
            or start['both_workflows_and_jobs_success'] is not True
            or any(type(start.get(k)) is not int or start[k] <= 0
                   for k in ('push_workflow','push_job','PR_workflow','PR_job'))
            or start['plan_sha256'] != sha(root / FILES[0])
            or start['preflight_sha256'] != sha(root / FILES[2])
            or start['activation_sha256'] != sha(root / FILES[4])
            or activation['preflight_sha256'] != sha(root / FILES[2])
            or activation['source_hashes'] != pre['source_hashes']
            or not activation['all_eight_conditions_frozen_before_generation']
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(root / FILES[1])
            or session['pipeline_source_sha256'] != report['pipeline_status_sha256']):
        raise ValueError('closed_fixed_P99_cohort_and_owned_server_required')
    if [r['task_id'] for r in pre['rows']] != [r['task_id'] for r in plan['known_tasks']]:
        raise ValueError('all_four_initial_tasks_required')
    for row in pre['rows']:
        if set(row['conditions']) != set(POLICIES):
            raise ValueError('both_initial_conditions_required')
        a, b = [row['conditions'][p] for p in POLICIES]
        if (a['model_messages_sha256'] != b['model_messages_sha256']
                or a['base_messages_sha256'] != b['base_messages_sha256']
                or a['visible_state'] != b['visible_state']
                or [a['reasoning_budget_tokens'], b['reasoning_budget_tokens']] != [-1, -1]
                or [a['tool_choice'], b['tool_choice']] != list(POLICIES)
                or any(type(x['input_tokens']) is not int or x['input_tokens'] < 1 for x in (a,b))):
            raise ValueError('matched_initial_history_and_explicit_choices_required')
    for name, expected_hash in pre['source_hashes'].items():
        if sha(root / name) != expected_hash:
            raise ValueError('frozen_P99_source_changed:' + name)
    for key, value in summarize(report['rows'], report['audit_errors']).items():
        if report[key] != value:
            raise ValueError('fixed_P99_gate_disagrees:' + key)
    for row in report['rows']:
        if row['record_status'] == 'evaluated':
            if type(row['success']) is not bool:
                raise ValueError('evaluated_success_must_be_boolean')
        elif row['success'] is not None:
            raise ValueError('unevaluated_result_cannot_be_success_or_failure')
        format_metrics(row)
    return plan, report, pre, session, activation


FORMAT_FIELDS = ('recorded_generations', 'known_responses', 'unknown_responses',
    'known_no_tool_generations', 'known_structured_generations', 'known_length_generations',
    'outer_record_count', 'format_rejections', 'not_executed_records',
    'Python_execution_errors', 'API_requests')


def format_metrics(row):
    if row.get('known_total_tokens') is None:
        if row.get('request_checks'):
            raise ValueError('unmeasured_cell_cannot_supply_selected_generation_records')
        return {k: None for k in FORMAT_FIELDS}
    checks = row.get('request_checks')
    if (type(checks) is not list or len(checks) != row['model_calls']
            or [c['call_id'] for c in checks] != [f'call_{n+1:03d}' for n in range(len(checks))]):
        raise ValueError('every_recorded_generation_required')
    known = [c for c in checks if c['status'] == 'ok']
    unknown = [c for c in checks if c['status'] != 'ok']
    if (len(unknown) != row['unknown_usage_calls']
            or any(c['structured_tool_calls'] is not None or c['output_limit_reached'] is not None
                   for c in unknown)
            or any(type(c['structured_tool_calls']) is not int or c['structured_tool_calls'] < 0
                   or type(c['output_limit_reached']) is not bool for c in known)):
        raise ValueError('known_and_unknown_response_features_must_remain_distinct')
    counts = ('outer_record_count','format_rejections','not_executed_records',
              'Python_execution_errors','API_requests')
    for c in checks:
        if (any(type(c[k]) is not int or c[k] < 0 for k in counts)
                or any(c[k] > c['outer_record_count'] for k in counts[1:-1])
                or (c['status'] != 'ok' and any(c[k] != 0 for k in counts))):
            raise ValueError('invalid_submission_record_counts')
    if sum(c['API_requests'] for c in checks) != row['api_requests']:
        raise ValueError('all_API_requests_must_be_assigned_to_generations')
    return dict(recorded_generations=len(checks), known_responses=len(known),
        unknown_responses=len(unknown),
        known_no_tool_generations=sum(c['structured_tool_calls'] == 0 for c in known),
        known_structured_generations=sum(c['structured_tool_calls'] > 0 for c in known),
        known_length_generations=sum(c['output_limit_reached'] for c in known),
        **{k:sum(c[k] for c in checks) for k in counts})


def format_totals(rows, policy):
    cells = [r for r in rows if r['tool_choice_policy'] == policy]
    measured = [format_metrics(r) for r in cells if r.get('known_total_tokens') is not None]
    return dict(tool_choice_policy=policy, measured_conditions=len(measured),
        unmeasured_conditions=len(cells)-len(measured),
        **{k:sum(r[k] for r in measured) if measured else None for k in FORMAT_FIELDS})


def totals(rows, policy):
    cells = [r for r in rows if r['tool_choice_policy'] == policy]
    measured = [r for r in cells if r.get('known_total_tokens') is not None]
    known = lambda key: sum(r[key] for r in measured) if measured and all(r.get(key) is not None for r in measured) else None
    out = dict(tool_choice_policy=policy, planned=len(cells), measured=len(measured),
        evaluated=sum(r['record_status'] == 'evaluated' for r in cells),
        successes=sum(r['success'] is True for r in cells),
        failures=sum(r['record_status'] == 'evaluated' and r['success'] is False for r in cells),
        unmeasured=len(cells)-len(measured))
    for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'input_tokens',
                'output_tokens', 'cached_input_tokens', 'api_requests', 'invocation_exceptions',
                'setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds'):
        out[key] = known(key)
    out['full_logical_tokens'] = (out['known_total_tokens']
        if len(measured) == len(cells) and out['unknown_usage_calls'] == 0 else None)
    out['known_uncached_input_tokens'] = (out['input_tokens'] - out['cached_input_tokens']
        if out['input_tokens'] is not None and out['cached_input_tokens'] is not None else None)
    return out


def cost(row):
    value = row.get('known_total_tokens')
    if value is None:
        return '未計測'
    text = f'{value:,}'
    if row.get('unknown_usage_calls'):
        text += f"＋不明{row['unknown_usage_calls']}"
    if row.get('unmeasured'):
        text += f"＋未計測{row['unmeasured']}条件"
    return text


def signed(value):
    return '未確定' if value is None else f'{value:+,}'


def number(value, decimals=0):
    return '未計測' if value is None else f'{value:,.{decimals}f}'


def contributions(report):
    groups = {'both_successful': [], 'both_failed': [], 'discordant': [], 'unevaluated': []}
    for pair in report['paired_results']:
        if not pair['both_evaluated']:
            group = 'unevaluated'
        elif pair['both_successful']:
            group = 'both_successful'
        elif not pair['auto_success'] and not pair['required_success']:
            group = 'both_failed'
        else:
            group = 'discordant'
        groups[group].append(pair)
    # Avoid presenting a selected known subset as the contribution of the full cohort.
    complete = report['all_eight_complete_with_known_usage']
    return {key: dict(task_count=len(pairs),
        required_minus_auto_tokens=sum(p['required_minus_auto_tokens'] for p in pairs) if complete else None)
        for key, pairs in groups.items()}


def figure(output, plan, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False})
    folder = output / 'figures'; folder.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 3.5), layout='constrained', facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    for n, item in enumerate(plan['known_tasks']):
        for j, policy in enumerate(POLICIES):
            row = next(r for r in rows if r['task_id'] == item['task_id'] and r['tool_choice_policy'] == policy)
            color = ('#7d8892', '#177b79')[j]; y = 3-n+(-.15 if j == 0 else .15)
            if row.get('known_total_tokens') is None:
                ax.text(.02, y, LABELS[j]+'：未計測', transform=ax.get_yaxis_transform(), va='center', color=color)
                continue
            value = row['known_total_tokens']/1000
            marker = '>' if row['unknown_usage_calls'] else ('o', 'D')[j]
            ax.scatter(value, y, marker=marker, s=75, edgecolor=color,
                facecolor=color if row['success'] is True else '#f6f4ed', lw=1.8)
            ax.annotate(f'{value:.1f}'+('＋不明' if row['unknown_usage_calls'] else '')+' '+outcome(row),
                (value, y), xytext=(7, 0), textcoords='offset points', va='center', color=color, fontsize=9)
    largest = max((r['known_total_tokens']/1000 for r in rows if r.get('known_total_tokens') is not None), default=1)
    ax.set_yticks(range(4), TASKS[::-1]); ax.set_ylim(-.6, 3.6); ax.set_xlim(0, max(1, largest)*1.42)
    ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    ax.set_xlabel('初期からの論理入力＋出力token（千）／右向き三角：既知小計＋不明使用量')
    for j, label in enumerate(LABELS):
        ax.plot([], [], color=('#7d8892', '#177b79')[j], marker=('o', 'D')[j], linestyle='', label=label)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.2), ncol=2, frameon=False)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(folder / ('P99_whole_task_costs.'+ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)


def build(output, root=ROOT):
    plan, report, pre, session, _ = validated(root)
    output.mkdir(parents=True, exist_ok=False); rows = report['rows']
    fields = ('run_id', 'task_id', 'tool_choice_policy', 'record_status', 'success', 'stop_reason',
        'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'input_tokens', 'cached_input_tokens',
        'output_tokens', 'api_requests', 'invocation_exceptions', 'setup_wall_seconds',
        'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
    format_rows = [dict(run_id=r['run_id'], task_id=r['task_id'], tool_choice_policy=r['tool_choice_policy'],
                       **format_metrics(r)) for r in rows]
    calls = [dict(run_id=r['run_id'], task_id=r['task_id'], tool_choice_policy=r['tool_choice_policy'],
                  **c) for r in rows for c in r.get('request_checks', [])]
    call_fields = ('run_id','task_id','tool_choice_policy','call_id','status',
        'structured_tool_calls','output_limit_reached','outer_record_count','format_rejections',
        'not_executed_records','Python_execution_errors','API_requests',
        'terminal_usage_recorded','request_sha256','response_sha256')
    for filename, data, columns in [('all_eight_conditions.csv', rows, fields),
            ('all_eight_submission_counts.csv', format_rows, tuple(format_rows[0])),
            ('all_recorded_generations.csv', calls, call_fields),
            ('all_four_pairs.csv', report['paired_results'], tuple(report['paired_results'][0]))]:
        with (output / filename).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader(); writer.writerows(data)
    figure(output, plan, rows)
    aggregate = [totals(rows, p) for p in POLICIES]; parts = contributions(report)
    formats = [format_totals(rows, p) for p in POLICIES]
    write_json(output / 'whole_cohort_summary.json', {'totals': aggregate, 'contributions': parts,
        'development_gate_met': report['development_gate_met'], 'all_planned_rows': 8,
        'required_minus_auto_whole_task_tokens': report['required_minus_auto_whole_task_tokens'],
        'paired_success_losses': report['paired_success_losses'], 'paired_success_gains': report['paired_success_gains'],
        'submission_counts': formats, 'all_recorded_generations': len(calls),
        'format_metrics_are_not_task_success': True})
    slides = []
    def add(title, body, takeaway, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, notes=notes))
    add('通常の提出設定を、課題全体の成果へつなげる',
        '<p class="body">A：任意提出auto／R：必須提出required。推論専用上限−1、全出力上限は共通。</p>'+
        table(('課題', 'A 初期入力token', 'R 初期入力token'),
            [(task, number(r['conditions']['auto']['input_tokens']), number(r['conditions']['required']['input_tokens']))
                for task, r in zip(TASKS, pre['rows'], strict=True)])+
        '<p class="body">新しい初期状態から各１回。初期要求差はtool_choiceの値だけ。入力長の差も実測する。</p>',
        '既知４課題の通常対照比較。過去の不明・未実行枠を補充したものではない。',
        '全返却推論・持続Python・型付きAPI・文章化前の構造化参照統一・残時間非表示を共通化。世界seed42、モデルseed57＋生成番号。必須指定でも有限出力内の完成、正しいPython、課題達成は保証されない。')
    add('全８条件の成否と、失敗を含む費用',
        table(('課題', '条件', '成否', '全仕事token', '生成', 'API', '作業秒'),
            [(TASKS[n-1], 'A' if p == 'auto' else 'R', outcome(r), cost(r),
              number(r.get('model_calls')), number(r.get('api_requests')), number(r.get('wall_seconds'), 1))
             for n, p in run_order() for r in rows if r['run_id'] == cell_id(n, p)], 'results'),
        '未評価・未実行は失敗数へ入れず、使用量不明は０で補完しない。',
        '各条件の最終状態を独立評価で一度だけ判定。判定基準や評価結果はモデルへ返さない。未知生成は実行・再試行しない。保留12課題は未閲覧。')
    add('同じ課題で、全仕事の費用と成功を比べる',
        '<img class="cost-figure" src="figures/P99_whole_task_costs.svg" alt="全８条件の論理費用と成否">',
        '塗りは成功。三角は不明費用が残る既知小計で、確定した総費用ではない。',
        '論理費用はcacheを含む全入力＋出力。早く未達で終えたことだけでは、品質を保った効率化としない。')
    gate = '達成' if report['development_gate_met'] else '未達'
    add('採否は全４課題と、課題ごとの成功喪失で決める',
        table(('条件', '成功／評価', '既知token合計', '計測済み／予定'),
            [(label, f"{r['successes']}/{r['evaluated']}", cost(r), f"{r['measured']}/{r['planned']}")
                for label, r in zip(LABELS, aggregate, strict=True)])+
        '<p class="lead">全課題 R−A：'+signed(report['required_minus_auto_whole_task_tokens'])+' token</p>'+
        '<p class="body">成功喪失 '+number(report['paired_success_losses'])+'課題、成功獲得 '+number(report['paired_success_gains'])+'課題。<br>'+
        '全８評価と使用量既知、監査一致、成功喪失０、両側成功１以上、全費用減が必要。</p>',
        '開発上の採用基準：'+gate+'。同数成功だけでは品質維持と判定しない。',
        '既知４課題・１反復の開発比較である。採用基準を満たしても一般的品質維持、以前の直接API方式への品質回復、新規性、採録可能性を保証しない。')
    add('成功した課題と、未達の課題の費用を分ける',
        table(('成果の組合せ', '課題数', 'R−A 全論理token'),
            [(label, parts[key]['task_count'], signed(parts[key]['required_minus_auto_tokens']))
             for key, label in [('both_successful', '両側成功'), ('both_failed', '両側未達'),
                               ('discordant', '成否が異なる'), ('unevaluated', '片側以上が未評価')]])+
        '<p class="body">全４対の成否・費用差はCSVにも保存。欠測時は全体の寄与を未確定とする。</p>',
        '成功部分だけの削減と、失敗を含めた全仕事の削減を区別する。',
        '全件の使用量が既知のとき、３つの評価済み区分の差は全課題の差へ足し合わさる。不明使用量があれば、選ばれた既知部分を全体の差として表示しない。')
    add('cache、出力、呼出しを別の費用として残す',
        table(('計測対象', 'A 任意提出', 'R 必須提出'),
            [(label, number(aggregate[0][key]), number(aggregate[1][key])) for key, label in [
                ('input_tokens', '既知の全入力token'), ('cached_input_tokens', '既知入力のcache再利用'),
                ('known_uncached_input_tokens', '既知のcache除外入力'), ('output_tokens', '既知の出力token'),
                ('model_calls', '生成試行'), ('api_requests', 'API要求'), ('unknown_usage_calls', '使用量不明の生成')]]),
        '既知小計は不明生成の使用量を含まない。tokenを金額や計算時間へ換算しない。',
        '制御通知・失敗・回復・再取得は仕事全体の入力と出力に含む。各条件の初回だけcoldを確認し、後続は通常のprefix cacheを使用。')
    add('提出形式と実操作を、最終成果から区別する',
        table(('計測対象', *LABELS),
            [(label, *[number(r[key]) for r in formats]) for key,label in [
                ('known_responses','終端応答が既知の生成'),
                ('unknown_responses','終端応答が不明の生成'),
                ('known_no_tool_generations','既知応答でツール提出なし'),
                ('known_length_generations','既知応答で出力上限に到達'),
                ('format_rejections','実行口の形式拒否記録'),
                ('Python_execution_errors','Pythonの実行例外記録'),
                ('not_executed_records','提出後の未実行記録')]]),
        '形式が改善しても課題達成は未確認。全８条件の成否で判断する。',
        '１生成が複数の外側記録を持つ場合があり、生成数と記録数は同じではない。上限到達と形式拒否も重なり得る。不明応答は提出なし０件へ置き換えず、未計測条件は別に保持する。全生成の数値とhashをCSVへ出す。')
    add('ロードから終了まで、所有推論器の費用も残す',
        table(('計測対象', '実測値'), [
            ('推論器稼働秒', number(session['wall_seconds'], 2)),
            ('モデルロード秒（稼働時間に含む）', number(session['load_wall_seconds'], 2)),
            ('全条件の初期化・作業・後片付け秒', number(session['cell_full_wall_seconds'], 2)),
            ('独立評価秒（稼働時間に含む）', number(session['evaluation_wall_seconds'], 2)),
            ('推論器の最大実測RSS GiB', number(session['sampled_peak_rss_bytes']/2**30, 2)),
            ('最大システムswap GiB', number(session['peak_system_swap_bytes']/2**30, 2))]),
        '所有推論器の停止とPID不在を確認。重なる時間を二重加算しない。',
        '１条件80生成・450000論理token・作業1800秒、全体640生成・3600000予約token・推論器21600秒。ホストで軽量な編集と報告準備も実施し、排他的な速度ベンチマークではない。RSSはGPU使用量全体ではない。')
    sections = []
    for n, slide in enumerate(slides, 1):
        sections.append(f'<section class="slide"><div class="eyebrow">10月24日 全仕事での通常ツール提出 / {n:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div><div class="footer"><span>既知４課題・固定８条件・各１回</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:29px}table{font-size:18px}td{padding:8px 12px}.results td,.results th{font-size:16px;padding:7px 8px}.cost-figure{width:100%;height:350px;object-fit:contain}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P99 全仕事のツール提出</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output / 'slides.json', slides)
    manifest = dict(pages=len(slides), generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256={name: sha(root / name) for name in FILES}, builder_sha256=sha(Path(__file__)),
        all_planned_rows=8, independent_tasks=4, repetitions=1, totals=aggregate, contributions=parts,
        development_gate_met=report['development_gate_met'],
        csv_sha256=sha(output / 'all_eight_conditions.csv'), paired_csv_sha256=sha(output / 'all_four_pairs.csv'),
        submission_csv_sha256=sha(output / 'all_eight_submission_counts.csv'),
        generation_csv_sha256=sha(output / 'all_recorded_generations.csv'),
        all_recorded_generations=len(calls), submission_counts=formats,
        summary_sha256=sha(output / 'whole_cohort_summary.json'), visual_reviewed=False,
        novel_method_claim=False, general_quality_preservation_claim=False, unknown_usage_imputed=False)
    write_json(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_p99_results')
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args(); result = build(args.output, args.repo_root)
    print({k: result[k] for k in ('pages', 'all_planned_rows', 'development_gate_met')})
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)

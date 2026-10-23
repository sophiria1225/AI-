"""Present all fourteen P72 cases, separately from original agent outcomes."""
import argparse
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from public_completion_scope import fixed_cases
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_public_completion_20261023'
LOCKED = {
    'reports/P72_public_completion_scope.json': '327dc950b37534893cf8851a739cf45174b12be57a5d44fa870ec554ad48a240',
    'reports/P72_public_completion_audit.json': 'd7fc2e2060fa0e80f2cced78e095067e9be22dad30691142127dafc9502772b7',
}
HISTORICAL_LOCKED = {
    'reports/P56_completion_scope.json': '3e3b1341840bea7e424a4434cad8fb4afd9c5c63677b593cc3e6bdd880f14ee9',
    'reports/P56_completion_audit.json': '4600af50f2bead2e7099c5dba67e2d4850247628d6f49751960f4de897b70a03',
}
LABELS = ('写真 D', '精算 F', '精算 D', '精算 B', '書出し F', '書出し D', '書出し B')


def validated():
    for path, digest in (LOCKED | HISTORICAL_LOCKED).items():
        if sha(ROOT / path) != digest:
            raise ValueError('closed P72 evidence changed: ' + path)
    report, audit = [read(ROOT / path) for path in LOCKED]
    plan = read(ROOT / 'configs/P72_public_completion_scope_v01.json')
    if (report['status'] != 'complete' or audit['batch_status'] != 'complete'
            or report['plan'] != plan or report['planned_cases'] != fixed_cases(plan)
            or audit['audit_errors'] or not audit['all_cases_evaluated']
            or not audit['all_cases_accounted'] or len(audit['rows']) != 14
            or audit['source_report_sha256'] != sha(ROOT / next(iter(LOCKED)))
            or audit['source_plan_sha256'] != sha(ROOT / 'configs/P72_public_completion_scope_v01.json')
            or not report['original_sources_unchanged'] or not audit['original_sources_unchanged']
            or audit['original_outcomes_relabelled'] or audit['autonomous_finalizer_validated']
            or report['not_recorded_cases'] or report['unknown_request_count_cases']):
        raise ValueError('complete, unchanged and separately audited P72 evidence required')
    for row, case in zip(audit['rows'], fixed_cases(plan), strict=True):
        if (any(row[key] != value for key, value in case.items())
                or row['record_status'] != 'evaluated' or row['database_files'] != 13
                or not row['non_supervisor_files_unchanged']
                or row['observation_matches'] != row['replay_api_requests']):
            raise ValueError('all fixed cases and exact public/state matches required')
    outcomes = [p['outcomes'] for p in audit['comparisons']]
    if (outcomes != [[False, True]] + [[False, False]] * 6
            or [p['source_run'] for p in audit['comparisons']] != plan['source_runs']
            or not audit['rows'][1]['final_world_equals_completed_reference']):
        raise ValueError('review the narrative if the observed pattern changes')
    claims = {
        'known_tasks': 3, 'source_states': 7, 'evaluated_cases': len(audit['rows']),
        'paired_outcomes': outcomes,
        'replay_api_requests': sum(r['replay_api_requests'] for r in audit['rows']),
        'intervention_api_requests': sum(r['intervention_api_requests'] for r in audit['rows']),
        'total_api_requests': report['total_api_requests'], 'evaluator_calls': report['evaluator_calls'],
        'model_generations': report['model_generations'], 'tokenizer_requests': report['tokenizer_requests'],
        'reserved_scenarios_read': report['reserved_scenarios_read'],
        'wall_seconds': report['wall_seconds'],
        'execution_seconds_including_cleanup': sum(r['execution_wall_seconds_including_cleanup'] for r in audit['rows']),
        'evaluation_seconds': sum(r['evaluation_wall_seconds'] for r in audit['rows']),
        'original_usage_unknown_calls_preserved': 2,
        'photo_completed_world_matches_original_B': audit['rows'][1]['final_world_equals_completed_reference'],
        'non_supervisor_files_unchanged': all(r['non_supervisor_files_unchanged'] for r in audit['rows']),
    }
    if ([claims[k] for k in ('replay_api_requests', 'intervention_api_requests', 'total_api_requests',
                            'evaluator_calls', 'model_generations', 'tokenizer_requests', 'reserved_scenarios_read')]
            != [702, 7, 709, 14, 0, 0, 0]):
        raise ValueError('review the measured resource ledger before rendering')
    locked = LOCKED | HISTORICAL_LOCKED
    locked['configs/P72_public_completion_scope_v01.json'] = audit['source_plan_sha256']
    return report, audit, claims, locked


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_joint_component(audit, claims):
    """Keep the earlier four cases and all fourteen new cases in one compact table."""
    old = read(ROOT / 'reports/P56_completion_audit.json')
    if (old['audit_errors'] or not old['all_four_evaluated']
            or [p['outcomes'] for p in old['comparisons']] != [[False, True], [False, False]]):
        raise ValueError('original four-case diagnostic changed')
    labels = ('G 写真 F', 'G 写真 B') + tuple('N ' + label for label in LABELS)
    pairs = old['comparisons'] + audit['comparisons']
    rows = [label + ' & ' + ' & '.join('成功' if v else '未達' for v in pair['outcomes']) + r'\\'
            for label, pair in zip(labels, pairs, strict=True)]
    component = (
        'Gの写真F/Dは各42移動で非supervisor保存ファイルが一致したが，公式成否は未達／成功，通知は０／１件だった．'
        'まずGの写真F/Bを別環境で再現し，元Dと同じ空引数の完了通知なし／１回追加の４条件を固定した．\n'
        '次にNの全12条件のうち，成否によらず完了API未送信の全７状態（既知３課題）を選び，同じ２条件の計14ケースを固定した．'
        'Nの通知は元写真Bで観測した\\texttt{status="success"}だけとした．'
        '全ケースで送信済み公開APIの返却と介入前の全13保存ファイルを元状態と照合し，無介入は元の成否を再現した．\n'
        r'\begin{center}\small 表4\quad 完了通知だけの介入（全18ケース）\par\smallskip' + '\n'
        r'\begin{tabular}{lll}\hline 再現した元状態 & 通知なし & 通知１回\\\hline' + '\n'
        + '\n'.join(rows) + '\n' + r'\hline\end{tabular}\end{center}' + '\n'
        'Gの写真FとNの写真Dだけが未達から成功へ変わり，それぞれ元GのD，元NのBと最終13保存ファイルも一致した．'
        '非supervisor保存ファイルは全ケースで介入前後不変だった．'
        '残り７状態は通知後も未達で，完了宣言を一律に足す根拠にはならない．\n'
        'Gの診断は346 API・４評価・23.927秒（評価8.541秒），'
        f'Nは702再送＋７通知＝709 API・14評価・{claims["wall_seconds"]:.3f}秒（評価{claims["evaluation_seconds"]:.3f}秒）だった．'
        '両診断とも生成０で，元の成否と不明費用は変更しない．'
        'Nの不明２生成は最後の未実行応答に限り，全API作用が既知であることを別に照合した．\n'
        '同じ既知写真の事後診断であり，独立した別課題の追認ではない．'
        'Gの写真では分類に必要な現在年の成功した公開時計応答がなく，'
        '通知による公式判定の変化は公開証拠だけで要求を全て検証できたことを意味しない．\n')
    path = ROOT / 'papers/202610_letter/completion_scope_joint.tex'
    path.write_text(component)
    return path


def build(output):
    report, audit, claims, locked = validated()
    output.mkdir(parents=True, exist_ok=True)
    fields = ('run_id', 'source_run', 'task_id', 'arm', 'record_status', 'official_success',
              'replay_api_requests', 'intervention_api_requests', 'observation_matches',
              'database_files', 'non_supervisor_files_unchanged',
              'execution_wall_seconds_including_cleanup', 'evaluation_wall_seconds')
    with (output / 'all_diagnostic_cases.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(audit['rows'])
    slides = [dict(title='完了通知だけで成否は変わるか<br>全７状態・14ケースの診断', cover=True)]

    def add(title, body, takeaway, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, notes=notes, cover=False))

    add('全ての未完了状態へ、同じ規則を適用する',
        '<p class="lead">P71で完了APIを送っていない全７状態を、公式成否によらず選ぶ。</p>'
        '<table><tr><th>対象</th><th>固定する比較</th><th>先に確認すること</th></tr>'
        '<tr><td>写真 D<br>精算 F・D・B<br>書出し F・D・B</td><td>別環境で記録済み操作を再送<br>無介入／完了通知１回</td>'
        '<td>全公開返却・介入前13保存ファイル一致<br>無介入の成否が元と一致</td></tr></table>'
        '<p class="small">写真だけを選ばず、既知３課題の７状態を全て残す。<br>観測済みの status="success" を固定し、他の通知引数は探索しない。</p>',
        '作業アプリへの追加操作なし。記録されたモデルコードも実行しない。',
        '各120 API・実行120秒・片付け45秒・評価180秒、全体1,800秒。再現不一致・作用不明・片付け失敗・評価不一致で全体停止、再試行なし。')
    rows = []
    for label, pair in zip(LABELS, audit['comparisons'], strict=True):
        rows.append('<tr><td>' + label + '</td>' + ''.join('<td>' + ('成功' if v else '未達') + '</td>' for v in pair['outcomes'])
                    + '<td>変化なし</td></tr>')
    add('写真Dだけが、通知１回で未達から成功へ変わった',
        '<table class="results"><tr><th>再現した元状態</th><th>通知なし</th><th>通知１回</th><th>非supervisor状態</th></tr>'
        + ''.join(rows) + '</table><p class="small">F：全表示、D：詳細省略、B：詳細と一覧を省略。<br>全14ケースを評価。監査不一致・未評価・未実行０。</p>',
        '精算・書出しの６状態は、通知だけでは成功しなかった。',
        '写真Dの通知後は元写真Bと全13保存ファイルも一致した。これは保存状態の限定比較であり、自動完了規則の検証ではない。')
    add('再現・介入・評価の費用も全て残す',
        '<table><tr><th>実測項目</th><th>全14ケース</th></tr>'
        '<tr><td>公開API</td><td>再送702 ＋ 通知７ ＝ 709</td></tr>'
        '<tr><td>独立評価／生成／token計数</td><td>14 ／ ０ ／ ０</td></tr>'
        f'<tr><td>全体時間</td><td>{claims["wall_seconds"]:.3f}秒</td></tr>'
        f'<tr><td>実行・片付け／評価</td><td>{claims["execution_seconds_including_cleanup"]:.3f} ／ {claims["evaluation_seconds"]:.3f}秒</td></tr></table>'
        '<p class="small">元のP71の不明２生成は不明のまま。<br>最後の未実行応答だけが不明で、環境への全API作用は確定していることを照合した。</p>',
        '診断の追加費用を記録し、元の費用へ混ぜたり節約額へ転記したりしない。',
        '全体時間には検査・起動などの残余も含むため、実行・片付けと評価の合計とは一致しない。モデル推論器は起動せず、保留群・隠れた評価項目・DB内容の読取も０。')
    add('今回強まった解釈と、まだない証拠',
        '<table><tr><th>分かったこと</th><th>主張の限界</th></tr>'
        '<tr><td>公開名接続でも成否差の一部は終了手続きによる</td><td>写真整理の品質改善とは区別する</td></tr>'
        '<tr><td>他の６状態では通知だけで未達を解消できない</td><td>一律の完了追加や安全な自動終了を支持しない</td></tr>'
        '<tr><td>全未完了状態を同じ規則で照合した</td><td>既知３課題。独立14課題の確認評価ではない</td></tr>'
        '<tr><td>元の成否・不明費用・費用不採用を保持</td><td>新手法の中核・一般品質維持は未確立</td></tr></table>',
        '最終目標は、必要情報・処理と品質を保ち、仕事全体の費用を減らすこと。',
        '元P55/P56の空引数診断とP71/P72の明示引数診断を分ける。同じ写真課題の再点検を新しい課題の追認と数えない。全18診断は自律実行の成功数へ加えず、別表として原稿へ反映する。')
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 全未完了状態の診断 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P72_findings.md">全結果と限界</a> / '
                '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P72_public_completion_audit.json">全件監査</a></span>'
                f'<span>{i}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:34px}table{font-size:20px}.small{margin-top:15px}td{padding:11px 15px}.results td{padding:3px 15px;font-size:19px}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P72 全７状態の完了診断</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    save(output / 'slides.json', slides)
    joint = write_joint_component(audit, claims)
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': locked, 'claims': claims, 'builder_sha256': sha(Path(__file__)),
        'joint_component_sha256': sha(joint),
        'shared_rendering_sha256': {p: sha(ROOT / 'scripts' / p) for p in ('build_morning_report.py', 'build_budget_report.py')},
        'visual_reviewed': False, 'scope': 'All seven P71 sources without a sent completion API; fourteen separate diagnostic cases.'}
    save(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p72')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    result = build(args.output); print({k: result[k] for k in ('pages', 'claims')})
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)

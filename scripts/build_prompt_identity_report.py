"""Present every saved P73 pair while preserving the original stopped batch."""
import argparse
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from prompt_identity import PAIR_RUNS
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_prompt_identity_20261023'
LOCKED = {
    'reports/P73_prompt_identity.json': 'd5a38803fb709e46f481bd7d5bddb95c89325ca8c08b8ed3f8f642e9247b03f1',
    'reports/P73_prompt_identity_audit.json': 'a4237db92c593e6cdf395650251e4f91a61ddefdbedfa8518192c624d454d2a5',
    'reports/P73_stop_diagnosis.json': '4b8e2099ccf6576964ce64df33b5e298f9070abf59aa2cd9b99dd6787384fa7c',
}
FIELDS = ('prompt', 'tokens', 'session_controls', 'parsed_non_message_parameters')


def validated():
    for path, expected in LOCKED.items():
        if sha(ROOT / path) != expected:
            raise ValueError('closed P73 evidence changed: ' + path)
    original, audit, diagnosis = [read(ROOT / path) for path in LOCKED]
    if (original['status'] != 'stopped' or original['pairs'] or original['calibrations']
            or original['rendering_attempts'] != 69 or original['rendered_input_files'] != 69
            or audit['audit_errors'] or not audit['all_69_inputs_accounted'] or audit['all_33_pairs_validated']
            or diagnosis['status'] != 'complete' or diagnosis['original_batch_status'] != 'stopped'
            or diagnosis['original_comparison_pairs_validated'] != 0
            or diagnosis['posthoc_pairs_inspected'] != 33 or len(diagnosis['pairs']) != 33
            or not diagnosis['all_69_existing_renderings_accounted']
            or diagnosis['original_criteria_changed'] or diagnosis['original_outcomes_relabelled']):
        raise ValueError('preserve the stopped batch and the separately complete read-only diagnosis')
    for path, expected in diagnosis['source_sha256'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('diagnostic source changed: ' + path)
    if sha(ROOT / 'scripts/inspect_prompt_identity_stop.py') != diagnosis['inspector_sha256']:
        raise ValueError('closed inspector changed')
    expected_pairs = [(before, after, f'call_{i:03d}') for before, after, count in PAIR_RUNS for i in range(1, count + 1)]
    rows = diagnosis['pairs']
    if [(r['reference_run'], r['controlled_run'], r['call_id']) for r in rows] != expected_pairs:
        raise ValueError('all fixed pairs in original order required')
    for row in rows:
        if (not all(row['equal'][key] for key in FIELDS)
                or not all(row['historical_input_counts_match'])
                or row['rendered_input_tokens'] != row['historical_input_tokens']
                or not row['bound_id_renamed_requests_equal']):
            raise ValueError('review the narrative if any observed pair differs')
    counts = [13, 12, 8]
    for group, count in zip(diagnosis['groups'], counts, strict=True):
        if (group['pairs'] != count or group['raw_request_equal_pairs'] != 1
                or group['bound_id_renamed_equal_pairs'] != count
                or group['historical_input_counts_matching'] != 2 * count
                or any(group['equal_pairs'][key] != count for key in FIELDS)):
            raise ValueError('group totals changed')
    controls = diagnosis['calibrations']
    if (set(controls) != {'P73_UNCHANGED', 'P73_RENAMED_IDS', 'P73_CHANGED_CONTENT'}
            or not all(controls['P73_UNCHANGED']['equal'].values())
            or not all(controls['P73_RENAMED_IDS']['equal'].values())
            or controls['P73_CHANGED_CONTENT']['equal'] != dict(zip(FIELDS, (False, False, True, True), strict=True))):
        raise ValueError('review every calibration result before rendering')
    zeros = ('additional_vocabulary_loads', 'additional_renderings', 'additional_input_tokenizations',
             'additional_model_calls', 'additional_api_requests', 'additional_evaluator_calls', 'reserved_scenarios_read')
    if any(diagnosis[k] != 0 for k in zeros):
        raise ValueError('additional read-only work must remain separately accounted')
    claims = {
        'original_batch_status': 'stopped', 'original_validated_pairs': 0,
        'posthoc_pairs': len(rows), 'groups': diagnosis['groups'],
        'renderings_and_input_tokenizations': original['rendered_input_files'],
        'historical_input_counts_matching': sum(sum(r['historical_input_counts_match']) for r in rows),
        'preflight_wall_seconds': original['preflight_wall_seconds'],
        'batch_wall_seconds': original['wall_seconds'],
        'sampled_peak_rss_bytes': original['sampled_peak_rss_bytes'],
        'posthoc_read_wall_seconds': diagnosis['wall_seconds'],
        'unchanged_control_equal': True, 'id_control_equal': True, 'content_control_equal': False,
        'new_model_calls': original['model_generations'], 'new_api_requests': original['environment_api_requests'],
        'new_evaluator_calls': original['evaluator_calls'], 'reserved_scenarios_read': original['reserved_scenarios_read'],
        'original_criteria_changed': False, 'original_outcomes_relabelled': False,
        'novel_method_claim': False, 'historical_gpu_or_rng_state_restored': False,
    }
    return original, diagnosis, claims, LOCKED | diagnosis['source_sha256']


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def component():
    path = ROOT / 'papers/202610_letter/prompt_identity_component.tex'
    path.write_text(
        'このID差を別途点検し，固定runtimeで保存66入力と３対照を再構成した．'
        '元batchは原文と正規化後のテンプレートの末尾改行１byte差で停止したため，保存出力を事後に読み取った．'
        '写真13・12対，書出し８対の全33対で文章・全token列・生成制約が一致し，元66入力の実測数とも一致した．'
        '未変更とID変更の対照は一致，本文変更では文章・token列が変化した．'
        '69入力の再構成・計数を含む処理5.543秒，事前照合1.859秒，事後読取0.254秒で，新規生成・API・評価は０だった．'
        '過去のGPU・乱数器状態は復元せず，元の全文不一致判定は変更しない．\n')
    return path


def build(output):
    _, diagnosis, claims, locked = validated()
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'all_input_pairs.csv').open('w', newline='') as stream:
        fields = ('index', 'reference_run', 'controlled_run', 'call_id', 'raw_requests_equal',
                  'bound_id_renamed_requests_equal', *FIELDS, 'reference_input_tokens', 'controlled_input_tokens',
                  'historical_input_counts_match')
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in diagnosis['pairs']:
            writer.writerow({**{k: row[k] for k in fields[:6]}, **row['equal'],
                'reference_input_tokens': row['rendered_input_tokens'][0],
                'controlled_input_tokens': row['rendered_input_tokens'][1],
                'historical_input_counts_match': all(row['historical_input_counts_match'])})
    slides = [dict(title='呼出しIDの差は<br>モデル入力にも残るか', cover=True)]
    def add(title, body, takeaway, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, notes=notes, cover=False))
    add('元の停止と、保存出力の事後診断を分ける',
        '<p class="lead">全69入力の再構成後、テンプレート原文のハッシュ照合で停止。</p>'
        '<table><tr><th>元batch</th><th>停止後の読取診断</th></tr>'
        '<tr><td>原文11,756 byte → 実効原文11,755 byte<br>固定ライブラリが末尾LFを１つ除去<br>元の検証済み対数は０のまま</td>'
        '<td>保存済み69出力を全件点検<br>全33対＋３対照を除外せず比較<br>再構成・再計数・モデル実行を追加しない</td></tr></table>',
        '停止条件を後から変更せず、事後の結果として報告する。',
        '親処理の比較前に停止したため、元監査の全入力所在確認と33対の未検証を保持する。差は末尾LF１byteのみで、一般的な空白除去では丸めない。')
    add('写真の改善例と、書出しの未達を全て含める',
        '<table><tr><th>全対象</th><th>要求JSON一致</th><th>文章・全token列<br>生成制約の一致</th></tr>'
        '<tr><td>写真・文書取得必須</td><td>1 / 13</td><td>13 / 13</td></tr>'
        '<tr><td>写真・公開名</td><td>1 / 12</td><td>12 / 12</td></tr>'
        '<tr><td>書出し・通常／制御</td><td>1 / 8</td><td>8 / 8</td></tr></table>'
        '<p class="small">元66入力は、過去に記録された入力token数とも全件一致。<br>対応IDだけを一対一で変更した要求JSONは全33対で一致。</p>',
        '同じ入力数だけでなく、保存された全token列を比較した。',
        '写真13・12対と書出し８対が固定全対象。制御条件より後の対照入力を補わない。全文不一致の元判定と各条件の費用・成否は保持する。')
    add('対照と追加費用を別々に記録する',
        '<table><tr><th>対照</th><th>文章・token列</th><th>生成制約</th></tr>'
        '<tr><td>未変更の複製 ／ 対応ID変更</td><td>一致 ／ 一致</td><td>一致</td></tr>'
        '<tr><td>system本文へ固定文を追加</td><td>変化（＋７token）</td><td>一致</td></tr></table>'
        f'<p class="small">元batch：69再構成・全入力計数、{claims["batch_wall_seconds"]:.3f}秒<br>'
        f'事前照合 {claims["preflight_wall_seconds"]:.3f}秒 ／ 停止後の読取 {claims["posthoc_read_wall_seconds"]:.3f}秒<br>'
        '観測最大RSS 184,991,744 byte。生成・推論context・環境API・評価０。</p>',
        '語彙処理と69入力の計数は追加作業であり、費用０とはしない。',
        '本文変更は13,546→13,553 token。ID変更での一致を校正の合格条件にせず、変化の有無を結果として残した。保留群・隠れた評価項目・DB内容は読まない。')
    add('入力の限定を絞り、主張の限界を維持する',
        '<table><tr><th>追加された根拠</th><th>引き続き必要な根拠</th></tr>'
        '<tr><td>固定runtimeの再構成入力は全33対一致</td><td>過去のGPU・乱数器状態は復元していない</td></tr>'
        '<tr><td>ID差が文章・token列へ残る兆候なし</td><td>元の全文不一致基準は不成立のまま</td></tr>'
        '<tr><td>写真の局所改善と書出しの未達を保持</td><td>新手法の中核・一般品質維持は未確立</td></tr></table>',
        '必要情報・処理と品質を保ち、仕事全体の費用を減らす目標へ戻る。',
        'P66の30.1％／26.0％減、P68の削減なしを変更しない。新しい生成実験、独立追認、平均因果効果の証明には数えない。通常対照に残る不要処理と判断規則の差を次に点検する。')
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 固定runtimeの入力診断 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P73_findings.md">全結果と限界</a> / '
                '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P73_stop_diagnosis.json">全33対の診断</a></span>'
                f'<span>{i}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:34px}table{font-size:20px}.small{margin-top:15px}td{padding:10px 15px}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P73 再構成入力の事後診断</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    save(output / 'slides.json', slides)
    part = component()
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': locked, 'claims': claims, 'builder_sha256': sha(Path(__file__)),
        'component_sha256': sha(part), 'csv_sha256': sha(output / 'all_input_pairs.csv'),
        'shared_rendering_sha256': {p: sha(ROOT / 'scripts' / p) for p in ('build_morning_report.py', 'build_budget_report.py')},
        'visual_reviewed': False, 'scope': 'Posthoc reading of all 33 pairs and 3 controls; original batch remains stopped.'}
    save(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p73')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    result = build(args.output); print({k: result[k] for k in ('pages', 'claims')})
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)

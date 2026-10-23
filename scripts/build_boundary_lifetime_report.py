"""Audit saved P74 outputs and present every cell without parsing source again."""
import argparse
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from inspect_boundary_lifetime_scope import validate
from run_handoff_factors import ROOT, read, sha

RAW = 'reports/P74_boundary_lifetime_scope.json'
RAW_SHA = '32ba5c9d2125eb1c0b95e166a20df96f698d624fcb014b6144a9a131aad6fbd3'
STEM = 'AI_harness_boundary_lifetime_20261023'
KEYS = ('all_call_api_syntax_sites', 'root_name_binding_sites', 'tracked_single_name_bindings',
        'bindings_with_literal_field_read', 'literal_subscripts_only_windows',
        'explicit_same_suite_releases', 'bindings_inside_control_or_definition',
        'normal_path_release_syntax_candidates', 'existing_helper_target_bindings')
LABELS = [task + ' ' + arm for task in ('写真', '精算', '返金', '書出し') for arm in ('全履歴', '出力省略', '一覧追加')]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def audit():
    if sha(ROOT / RAW) != RAW_SHA:
        raise ValueError('closed P74 source changed')
    raw = read(ROOT / RAW)
    plan_path = 'configs/P74_boundary_lifetime_v01.json'
    plan = read(ROOT / plan_path); source, _ = validate(plan)
    if (raw['status'] != 'complete' or raw['accounted_program_occurrences'] != 181
            or raw['unique_input_files'] != 117 or raw['unprocessed_inputs']
            or len(raw['programs']) != 181 or len(raw['rows']) != 12
            or raw['plan_sha256'] != sha(ROOT / plan_path)
            or raw['protocol_sha256'] != sha(ROOT / 'docs/experiments/P74_boundary_lifetime_scope.md')
            or raw['runtime_rewriting'] or raw['online_equivalence_verified'] or raw['novel_method_claim']
            or raw['measured_savings'] is not None):
        raise ValueError('complete unchanged syntax-only inspection required')
    for path, digest in (raw['source_sha256'] | raw['implementation_sha256']).items():
        if sha(ROOT / path) != digest:
            raise ValueError('fixed source or implementation changed: ' + path)
    expected = [{'run_id':row['run_id'],**item} for row in source['rows'] for item in row['inputs']]
    if raw['planned_inputs'] != expected:
        raise ValueError('all input occurrences must remain accounted')
    unique = {}
    for item, record in zip(expected, raw['programs'], strict=True):
        if (record['status'] != 'analyzed' or any(record[k] != item[k] for k in ('run_id','program','phase','program_index','sha256'))
                or record['analysis']['online_replacement_verified']
                or record['analysis']['exception_exit_equivalence_verified']):
            raise ValueError('original input identity or scope changed')
        if item['path'] in unique and unique[item['path']]['analysis'] != record['analysis']:
            raise ValueError('same saved source has inconsistent analysis')
        unique[item['path']] = record
        bindings = record['analysis']['bindings']; c = record['analysis']['counts']
        if (c['tracked_single_name_bindings'] != len(bindings)
                or c['normal_path_release_syntax_candidates'] != sum(b['normal_path_release_syntax_candidate'] for b in bindings)
                or c['bindings_with_literal_field_read'] != sum(any(b['load_counts'].get(k,0) for k in
                    ('literal_field_subscript','literal_field_get')) for b in bindings)
                or c['explicit_same_suite_releases'] != sum(b['same_suite_release_kind'] is not None for b in bindings)):
            raise ValueError('binding totals do not agree')
    for expected_row, row in zip(source['rows'],raw['rows'],strict=True):
        programs = [r for r in raw['programs'] if r['run_id'] == row['run_id']]
        counts = {k:sum(r['analysis']['counts'][k] for r in programs if r['phase'] != 'control') for k in KEYS}
        if (any(row[k] != expected_row[k] for k in ('run_id','task_id','arm')) or row['counts'] != counts
                or row['program_occurrences'] != len(programs) or row['unsupported_programs'] != 0):
            raise ValueError('all-cell totals disagree')
    totals = {k:sum(row['counts'][k] for row in raw['rows']) for k in KEYS}
    if raw['totals'] != {k:v for k,v in totals.items() if v > 0}:
        raise ValueError('original positive-count summary disagrees')
    if list(totals.values()) != [239,144,144,15,3,3,22,0,2]:
        raise ValueError('review the narrative after a result change')
    distinct = {k:sum(r['analysis']['counts'][k] for r in unique.values() if r['phase'] != 'control') for k in KEYS}
    zero_keys = ('model_generations','environment_api_requests','evaluator_calls','task_databases_read',
                 'reserved_scenarios_read','saved_code_executions')
    if any(raw[k] != 0 for k in zero_keys):
        raise ValueError('unexpected additional execution')
    result = {'phase':'P74_audit','status':'complete','source_report_sha256':RAW_SHA,'audit_errors':[],
        'all_181_occurrences_accounted':True,'unique_input_files':len(unique),'rows':raw['rows'],
        'totals_including_zero':totals,'distinct_file_totals_including_zero':distinct,
        'wall_seconds':raw['wall_seconds'],**{k:raw[k] for k in zero_keys},
        'original_totals_omit_zero_keys':True,'missing_zero_key_derived_from_all_rows':True,
        'online_replacement_verified':False,'novel_method_claim':False,'measured_savings':None,
        'auditor_sha256':sha(Path(__file__))}
    return raw,result


def build(output):
    raw,checked = audit(); output.mkdir(parents=True,exist_ok=True)
    save(ROOT/'reports/P74_boundary_lifetime_audit.json',checked)
    fields=('run_id','task_id','arm','program_occurrences','unsupported_programs','control_programs',*KEYS)
    with (output/'all_lifetime_cells.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=fields);w.writeheader()
        for row in checked['rows']:w.writerow({k:row[k] for k in fields[:6]} | row['counts'])
    slides=[dict(title='現在の項目参照と<br>次の生成へ残る値を分ける',cover=True)]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes,cover=False))
    rows=''.join(f'<tr><td>{label}</td><td>{r["counts"]["root_name_binding_sites"]}</td>'
                 f'<td>{r["counts"]["bindings_with_literal_field_read"]}</td><td>{r["counts"]["explicit_same_suite_releases"]}</td><td>0</td></tr>'
                 for label,r in zip(LABELS,checked['rows'],strict=True))
    add('全12条件：項目参照があっても、根の破棄は別条件',
        '<table class="results"><tr><th>既知課題・条件</th><th>名前へ保存</th><th>項目参照あり</th><th>明示的上書き</th><th>限定候補</th></tr>'+rows+'</table>',
        '144保存箇所のうち項目参照は15箇所。固定した構文候補は０。',
        '全181出現、117固有ファイル。前半の重複96・継続81・制御４を残す。構文箇所数でありAPI回数・不要量・節約量ではない。元集計は０のキーを省くため、全12行から０を明示して監査した。')
    add('なぜ残る値を、そのまま部分辞書へ変えないか',
        '<table><tr><th>観測した構造</th><th>残る制約</th></tr>'
        '<tr><td>literal添字だけの読取は３箇所</td><td>いずれも写真のループ内。対象helper外で、明示的な破棄なし</td></tr>'
        '<tr><td>明示的上書きは３出現</td><td>同じ前半の説明取得１箇所の重複。根全体の使用あり</td></tr>'
        '<tr><td>曲詳細helperの対象は２箇所</td><td>両方ループ内。getや根を使う構文があり、限定候補には入らない</td></tr></table>',
        '根を使う構文があることも、全項目が実際に読まれた証明ではない。',
        '構文解析では将来生成、動的型、別名、例外時の名前空間、取得時点を保証しない。２つの曲詳細箇所やループ一般の最適化不可能性を示す結果ではない。')
    add('今回の方式は拡張せず、復元を含む条件を残す',
        f'<p class="lead">全181出現を {raw["wall_seconds"]:.3f}秒で点検。未対応・未処理０。</p>'
        '<ul><li>新しい生成・環境API・評価・保存コード実行は０。</li>'
        '<li>既存の直接項目helperへ自動変換する実行器は追加しない。</li>'
        '<li>取得を遅らせるなら、次の生成・状態変更・例外時の完全値と取得時点を守る必要がある。</li>'
        '<li>その復元費用まで加えて得になるかは、別の未検証事項。</li></ul>',
        '新提案の中核・一般品質維持は未確立。原稿の既存結果は変更しない。',
        'P73の事後入力診断は原稿へ反映済み。P74は方式を絞る読取点検であり、主表の成功数や独立課題数へ加えない。通常の依存解析との差を示せる機構と反証条件が必要である。')
    sections=[]
    for i,s in enumerate(slides,1):
        if s['cover']:sections.append(f'<section class="slide cover"><h1>{s["title"]}</h1><div class="notes"></div></section>')
        else:sections.append(f'<section class="slide"><div class="eyebrow">10月23日 生成境界と返却値 / {i-1:02d}</div>'
            f'<h2>{s["title"]}</h2>{s["body"]}<div class="takeaway">{s["takeaway"]}</div>'
            '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P74_findings.md">全結果と限界</a></span>'
            f'<span>{i}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:32px}table{font-size:20px}td{padding:10px 15px}.results td,.results th{padding:2px 12px;font-size:17px}li{font-size:24px;margin:14px 0}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P74 生成境界の返却値点検</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    save(output/'slides.json',slides)
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),'builder_sha256':sha(Path(__file__)),
        'source_sha256':{RAW:RAW_SHA,'reports/P74_boundary_lifetime_audit.json':sha(ROOT/'reports/P74_boundary_lifetime_audit.json'),
                         'configs/P74_boundary_lifetime_v01.json':raw['plan_sha256']},
        'claims':{k:checked[k] for k in ('totals_including_zero','distinct_file_totals_including_zero','wall_seconds','online_replacement_verified','novel_method_claim')},
        'csv_sha256':sha(output/'all_lifetime_cells.csv'),'visual_reviewed':False,
        'shared_rendering_sha256':{p:sha(ROOT/'scripts'/p) for p in ('build_morning_report.py','build_budget_report.py')}}
    save(output/'build_manifest.json',manifest);return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261023_p74')
    p.add_argument('--pdf',action='store_true');args=p.parse_args()
    result=build(args.output);print({k:result[k] for k in ('pages','claims')})
    if args.pdf:build_budget_report.STEM=STEM;build_budget_report.export(args.output)

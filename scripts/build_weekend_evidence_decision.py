"""An editorial snapshot of closed evidence, with no experiment or audit rerun."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_weekend_evidence_decision_20261024'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'
SOURCES = (
    'reports/P88_comparison.json', 'reports/P84_fallback_output_replay.json',
    'reports/public_read_views_live_results_20261024.json',
    'reports/P89_public_read_opportunity.json', 'reports/P90_public_read_authority_causes.json',
    'reports/P91_joined_read_opportunity.json', 'reports/P92_recorded_view_compatibility.json',
    'reports/P92_preparation_20261024.json',
    'docs/retained_read_admission_limit_20261024.md',
    'docs/letter_scenario_reservation_20261021.md',
    'docs/deferred_read_resource_prior_boundary_20261024.md',
    'docs/reversible_read_views_20261024.md',
    'docs/automatic_completion_contract_scope_20261024.md')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, data): p.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
def esc(value): return html.escape(str(value))
def table(headers, rows):
    return '<table class="compact decision-table"><thead><tr>'+''.join('<th>'+esc(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def build(root, output):
    if output.exists(): raise FileExistsError('preserve_editorial_snapshot')
    loaded = {name: json.loads((root/name).read_text()) for name in SOURCES if name.endswith('.json')}
    p88=loaded[SOURCES[0]]; p84=loaded[SOURCES[1]]; live=loaded[SOURCES[2]]
    p91=loaded[SOURCES[5]]; p92=loaded[SOURCES[6]]; prep=loaded[SOURCES[7]]
    if (len(p88['rows']) != 8 or p88['audit_errors'] or p88['development_gate_met'] is not False
            or any(r['record_status'] != 'evaluated' for r in p88['rows'])
            or sum(r['unknown_usage_calls'] for r in p88['rows']) != 1
            or p84['audit_errors'] or not p84['all_eighteen_audited']
            or live['all_six_observations_equal'] is not True
            or [r['api_rows_recorded'] for r in live['conditions']] != [11,10]
            or p91['status'] != 'complete' or len(p91['rows']) != 8
            or p92['status'] != 'complete' or len(p92['rows']) != 5
            or p92['inspected_programs'] != 11 or prep['all_tests'] != 1435):
        raise ValueError('closed_expected_evidence_required')
    targets=[t for r in p91['rows'] for t in r['analysis']['targets']]
    if len(targets) != 4: raise ValueError('all_four_targets_required')
    for row in p91['rows']:
        if row['analysis']['counts'].get('before_partial',0) or row['analysis']['counts'].get('before_complete',0):
            raise ValueError('the_no_opportunity_interpretation_changed')
    output.mkdir(parents=True)
    slides=[]
    def add(title, body, takeaway, notes, sources):
        slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes,sources=sources))
    add('研究の現在地と日曜の判断',
        '<p class="lead">新しい読取機構は実装できたが、実課題で品質を保った全費用削減と、新規手法の中核は未確立。</p>'
        '<div class="three"><div class="col"><h3>最終目標</h3><p class="body">必要な情報・処理と最終品質を保ち、取得・共有・生成・実行・検証の総費用を減らす。</p></div>'
        '<div class="col"><h3>今回閉じた範囲</h3><p class="body">P88の全８条件、読取の実サービス確認、P89〜P92の全件点検。</p></div>'
        '<div class="col"><h3>期限</h3><p class="body">10/25に主張と採否を絞る。10/29〜30に原稿整備、10/31投稿を目指す。</p></div></div>',
        '実装数や検査数は、新規性・成果品質・採録可能性の代用にならない。',
        '2026年10月24日の閉じた根拠をまとめた判断資料。投稿可能な完成稿ではない。ユーザーからの停止指示はなく、実装と原稿の整理を継続する。',
        [('研究状態','docs/current_status.md'),('P88全件','docs/P88_findings.md')])
    task_order=[]
    for row in p88['rows']:
        if row['task_id'] not in task_order:task_order.append(row['task_id'])
    task_names=dict(zip(task_order,['写真','精算','返金','CSV'],strict=True))
    eight=[]
    for r in p88['rows']:
        tokens=f'{r["known_total_tokens"]:,}'+('＋不明１' if r['unknown_usage_calls'] else '')
        eight.append([task_names[r['task_id']], 'U 上限なし' if r['reasoning_policy']=='unlimited' else 'H 固定2,048',
                      '成功' if r['success'] else '未達',r['model_calls'],tokens,r['api_requests']])
    add('通常の推論予算：全８条件でも採用基準は未達',
        table(['課題','条件','結果','生成','論理token','実API'],eight)
        +'<p class="small subtle">両方式3/4成功。成功３対の論理token差は各０。CSVは両方未達で、Uの１生成は使用量不明。全仕事費用差は未確定。</p>',
        '形式が完成したことと、課題が成功して全費用が減ることを分ける。',
        '全150生成、既知1,689,160論理tokenと使用量不明１生成、399 API、８評価。監査終了。既知小計の差を完全な費用差にしない。通常の設定を新規手法とは主張しない。',
        [('全件結果','docs/P88_findings.md'),('全出力診断','materials/20261024_p88_output_diagnostic/README.md')])
    add('遅延読取：部品の動作と実課題の機会は別',
        table(['確認','結果','言える範囲'],[
            ['手書きの実サービス操作','API 11対10／制御要求18対18','６段階の値が一致。未使用参照１件の回避'],
            ['P89：全８条件','曲詳細４要求とも事前情報なし','現行の一覧・詳細契約では候補０'],
            ['P90：同じ全４要求','無効化で失った適合情報０','無効化を緩めるだけでは候補が増えない'],
            ['P91：取得元を追加','アルバム・プレイリストでも候補０','この８条件の大きな遅延比較は採用しない']])
        +'<p class="small subtle">同じ完全応答キャッシュを即時・遅延の両側へ与えた。旧値を差分復元する別ホストは部品検査までで、実サービスの作用例外は未有効化。</p>',
        '手書き11対10から、LLM課題の成功率・総費用改善へは一般化しない。',
        '３つの点検は同じP88の記録を使っており、独立した３集団ではない。取得元の成功返答総数は要求直前の利用可能性を意味しない。実サービス確認は新しいモデル生成・課題評価０。',
        [('実サービス','materials/20261024_public_read_views_live_results/README.md'),('P91','materials/20261024_p91_results/README.md'),('旧値復元','docs/reversible_read_views_20261024.md')])
    five=[[r['run_id'].replace('P68_01_EXPORT_NATIVE','P68 NATIVE').replace('P68_02_EXPORT_CONTROLLED','P68 CONTROLLED'),
           '成功' if r['original_official_success'] else '未達',r['show_song_requests'],r['task_fields_preknown_requests'],r['program_count']]
          for r in p92['rows']]
    add('P92：部分情報26機会を26要求の節約とは数えない',
        table(['記録','元結果','曲詳細送信','項目の事前充足','保存Python'],five)
        +'<p class="small subtle">Pythonは１記録・11プログラム。最後のループは返却を辞書へ残し、元は50送信後に停止。全件取得後の表示に進んでいない。</p>'
        +'<p class="formula">生存参照を各１回予約する前提では　S ＋ D ＝ S₀ ＋ n</p>',
        '取得を後回しにしても、予約が残る限り次の読取の余力は増えない。',
        'Sは取得済み、Dは未取得予約、nは新しく受理した参照数。参照消滅・完全キャッシュ・まとめ取得などがない場合の直接の恒等式。896合成条件は別の部品検査。P92は保存構造と構文の点検で、変更コードを再生していない。',
        [('全５記録','materials/20261024_p92_results/README.md'),('受理上限','docs/retained_read_admission_limit_20261024.md')])
    add('新規性・研究意義・採録の見通し',
        table(['評価軸','現時点の判断'],[
            ['新しい方式としての貢献','通常の遅延・キャッシュ・予約・過去復元を超える規則と実課題での追加価値が未確立'],
            ['実証資料としての意義','入力表現、形式完成、最終成功、各費用を区別し、局所改善が全仕事改善へ届く条件を点検できる'],
            ['残る弱点','少数の既知課題・主に単一モデル。調整後の独立確認と、強い通常対照に勝つ結果が不足'],
            ['レター採録の判断','採録されそうと言える根拠はまだ不足。採録確率の数字は付けず、主張範囲と証拠を優先する']]),
        '限定的な評価の原稿は書けるが、良い結果が出たことには置き換えない。',
        '評価実験としての価値と、査読に十分な新規性は別。文献メモでは一般原理との重なりを確認しているが、具体的な差が今後生じる可能性まで否定しない。採録の約束をしない。',
        [('先行する資源付き遅延','docs/deferred_read_resource_prior_boundary_20261024.md'),('自動完了契約の限界','docs/automatic_completion_contract_scope_20261024.md')])
    add('日曜までに絞る作業と投稿の準備',
        '<div class="two"><div><h3>主張の精度を上げる</h3><ul class="body"><li>P84の保存18出力を、文字列の差と公開操作の差に分ける点検を準備する。</li><li>構文一致を意味・品質の一致へ広げない。追加生成・実行はまず配分しない。</li><li>新方式は通常対照後の不要処理と、実行時に使える判断根拠を具体化する。</li></ul></div>'
        '<div><h3>原稿を成立させる</h3><ul class="body"><li>和英題名と教授用あらましを維持。本文の主張は閉じた結果に合わせる。</li><li>著者・所属・順序は確認待ち。公式様式への適合確認も残る。</li><li>未見12課題は保留。主提案未成立のまま探索へ使わない。</li></ul></div></div>',
        '10/25は採否を絞る期限。10/31投稿へ、成果のある範囲を明確にする。',
        'P84の追加点検は新しい読取専用の計画として準備し、元の固定判定を変更しない。著者情報はユーザーへ質問中。教授への送信と実投稿は行っていない。',
        [('P84の元の判定','docs/P84_findings.md'),('未見群の規則','docs/letter_scenario_reservation_20261021.md'),('現行原稿','papers/202610_letter/reasoning_budget_control_observed/README.md')])
    parts=[]
    for i,s in enumerate(slides,1):
        links=' ／ '.join(f'<a href="{LINK+path}">{esc(label)}</a>' for label,path in s['sources'])
        parts.append(f'<section class="slide"><div class="eyebrow">2026.10.24 / {i:02d}</div><h2>{s["title"]}</h2>'+s['body']+
            f'<div class="takeaway">{s["takeaway"]}</div><footer class="footer"><div class="sources">{links}</div><span>{i} / {len(slides)}</span></footer>'+
            f'<div class="notes">{esc(s["notes"])}</div></section>')
    extra='.decision-table{margin-top:18px}.decision-table th,.decision-table td{font-size:18px;padding-top:7px;padding-bottom:7px}.slide:nth-of-type(2) .decision-table th,.slide:nth-of-type(2) .decision-table td{font-size:17px;line-height:1.4;padding-top:4px;padding-bottom:4px}.formula{margin-top:16px;font-size:26px;font-weight:700;color:var(--teal)}.two .body{font-size:21px;line-height:1.55}.three .body{font-size:21px;line-height:1.6}'
    document='<!doctype html><html lang="ja"><meta charset="utf-8"><title>研究の現状と日曜の判断</title><style>'+STYLE+extra+'</style><body>'+''.join(parts)+\
        '<nav id="nav"><button id="prev">前</button><span id="count"></span><button id="next">次</button><button id="all">一覧</button><button id="note">メモ</button><button id="print">PDF</button></nav><div id="speaker"></div><script>'+SCRIPT+'</script></body></html>'
    (output/'index.html').write_text(document)
    put(output/'slides.json',slides)
    (output/'speaker_notes.md').write_text('# 10月24日：研究の現状と日曜の判断\n\n'+'\n\n'.join(f'## {i}. {s["title"]}\n\n{s["notes"]}' for i,s in enumerate(slides,1))+'\n')
    with (output/'P88_all_eight.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['task','condition','outcome','generations','known_logical_tokens_and_missing','api_requests']);w.writerows(eight)
    with (output/'P92_all_five.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['record','original_outcome','song_requests','prior_task_field_coverage','saved_python_programs']);w.writerows(five)
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),pages=len(slides),source_sha256={name:sha(root/name) for name in SOURCES},builder_sha256=sha(Path(__file__)),
        generated_sha256={name:sha(output/name) for name in ['index.html','slides.json','speaker_notes.md','P88_all_eight.csv','P92_all_five.csv']},
        visual_reviewed=False,additional_model_generations=0,additional_environment_api_requests=0,additional_evaluations=0,closed_experiment_or_audit_rerun=False,
        new_method_established=False,submission_ready=False,authors_confirmed=False,P84_action_inspection_status='planned_not_started')
    put(output/'build_manifest.json',manifest)
    (output/'README.md').write_text('# 研究の現状と日曜の判断\n\n[PDF・全６頁]('+STEM+'.pdf)／[HTML](index.html)／[説明メモ](speaker_notes.md)／[根拠と生成記録](build_manifest.json)。\n\nP88の全８条件、手書きの実サービス確認、P89〜P92の点検を、実装・実測・未確立の主張に分けて整理した。新規手法の有効性・一般的な品質維持・採録に足る中核は未確立。追加モデル・API・評価０、閉じた実験や監査の再実行０。著者情報と公式様式への適合は未確認。\n\n既知課題を使った診断であり、未見12課題は保留する。P84の出力差を公開操作・構文の違いに分ける次の点検は準備前で、元の判定や成否を変更していない。\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pdf',action='store_true');args=parser.parse_args()
    result=build(args.repo_root.resolve(),args.output.resolve())
    if args.pdf:
        build_budget_report.STEM=STEM;build_budget_report.export(args.output.resolve())
    print(json.dumps({'pages':result['pages'],'additional_generations':0,'submission_ready':False}))

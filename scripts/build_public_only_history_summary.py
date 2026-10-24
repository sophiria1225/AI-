"""All four new controls and all twelve historical references after closure."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def csvfile(path,fields,rows):
    with path.open('x') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:writer.writerow({key:row.get(key) for key in fields})


def build(root,storage):
    audit=read(root/'reports/P114_comparison.json');session=read(root/'reports/P114_server_session.json')
    if (audit['audit_errors'] or len(audit['rows'])!=4 or not audit['owned_processes_absent']
            or session['status']!='stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256']!=sha(root/'reports/P114_comparison.json')):
        raise ValueError('closed_all_four_audited_conditions_required')
    folder=root/'materials/20261025_p114_results';folder.mkdir()
    conditions=[];calls=[];views=[];private={}
    for row in audit['rows']:
        control=row.get('reasoning_display') or {}
        condition=dict(**row,**{'display_'+k:v for k,v in control.items()},
            full_logical_tokens=row.get('known_total_tokens') if row.get('unknown_usage_calls')==0 else None,
            noncached_input_tokens=(row['input_tokens']-row['cached_input_tokens'])
                if row.get('cached_input_tokens') is not None else None)
        conditions.append(condition)
        if row['record_status'] not in ('evaluated','unevaluated'):continue
        trial=storage/'records/context_pilot'/row['run_id']
        if sha(trial/'usage.json')!=row['usage_sha256']:raise ValueError('bound_usage_changed')
        usage=read(trial/'usage.json');private[row['run_id']]={'usage.json':sha(trial/'usage.json')}
        for call in usage:
            calls.append(dict(run_id=row['run_id'],task_id=row['task_id'],policy=row['reasoning_display_policy'],
                task_success=row['success'],**call,
                total_tokens=call['input_tokens']+call['output_tokens'] if call['status']=='ok' else None))
        if row.get('history_views_sha256'):
            path=trial/'reasoning_history_views.json'
            if sha(path)!=row['history_views_sha256']:raise ValueError('bound_history_views_changed')
            private[row['run_id']]['reasoning_history_views.json']=sha(path)
            dispatched={c['id'] for c in usage}
            for item in read(path):
                value=item['projection']
                views.append(dict(run_id=row['run_id'],next_call_id=item['next_call_id'],
                    policy=row['reasoning_display_policy'],model_attempted=item['next_call_id'] in dispatched,
                    projection_wall_seconds=item['projection_wall_seconds'],
                    removed_turns=json.dumps(value['removed_reasoning_turns']),
                    redisplayed_turns=json.dumps(value['redisplayed_reasoning_turns']),
                    signature_unbound_turns=json.dumps(value['signature_unbound_turns']),
                    **{k:value[k] for k in ('original_reasoning_characters','supplied_reasoning_characters',
                        'removed_reasoning_characters','latest_execution_eligible','public_history_sha256',
                        'original_history_sha256','supplied_history_sha256')}))
    csvfile(folder/'all_conditions.csv',[
        'run_id','task_id','reasoning_display_policy','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','full_logical_tokens','api_requests',
        'input_tokens','output_tokens','cached_input_tokens','noncached_input_tokens',
        'setup_wall_seconds','wall_seconds','cleanup_wall_seconds','full_wall_seconds','invocation_exceptions',
        'display_eligible_executions','display_projections','display_projections_hiding_reasoning',
        'display_projections_redisplaying_reasoning','display_measured_projection_wall_seconds',
        'display_measured_evidence_wall_seconds'],conditions)
    csvfile(folder/'all_model_calls.csv',[
        'run_id','task_id','policy','task_success','id','status','input_tokens','output_tokens','total_tokens',
        'cached_input_tokens','wall_seconds','finish_reason','timeout_scope','error_kind',
        'predicted_input_tokens','output_cap'],calls)
    csvfile(folder/'all_projections.csv',[
        'run_id','next_call_id','policy','model_attempted','projection_wall_seconds',
        'latest_execution_eligible','removed_turns','redisplayed_turns','signature_unbound_turns',
        'original_reasoning_characters','supplied_reasoning_characters','removed_reasoning_characters',
        'public_history_sha256','original_history_sha256','supplied_history_sha256'],views)
    historical=read(root/'reports/P111_comparison.json')
    if historical['audit_errors'] or len(historical['rows'])!=12:
        raise ValueError('all_twelve_historical_rows_required')
    csvfile(folder/'historical_P111_conditions.csv',[
        'run_id','task_id','reasoning_display_policy','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','api_requests',
        'input_tokens','output_tokens','cached_input_tokens','wall_seconds','full_wall_seconds'],historical['rows'])
    summary={k:audit[k] for k in ('phase','batch_status','planned_rows','independent_tasks',
        'repetitions','comparisons','development_gate_met','all_four_complete_with_known_usage',
        'historical_reference_rows','contemporaneous_comparison',
        'novel_method_claim','general_quality_preservation_claim','interpretation')}
    summary.update(model_attempts=len(calls),known_logical_tokens=sum(c['total_tokens'] or 0 for c in calls),
        unknown_usage_attempts=sum(c['status']!='ok' for c in calls),
        sent_API_requests=sum(r.get('api_requests',0) for r in audit['rows']),
        all_conditions_retained=4,original_P110_hypothetical_counts_reused_as_cost=False)
    write(folder/'summary.json',summary)
    write(folder/'server_cost.json',session)
    lines=['# P114: 内部推論を再入力しない通常対照','',
        '既知４課題を初期状態から各１回実行した通常対照の全記録. P111の全12条件は過去参照であり、'
        '同時実行の対照でも未見の確認試験でもない. 全条件と不明使用量、失敗、未実行を保持する.',
        '', '| 出典 | 課題 | 表示 | 成否 | 既知の全論理token | 不明使用量 | 生成 | API |',
        '|---|---|---|---|---:|---:|---:|---:|']
    for phase,r in [('P114',r) for r in audit['rows']]+[('P111 過去参照',r) for r in historical['rows']]:
        success='成功' if r['success'] is True else '未達' if r['success'] is False else r['record_status']
        lines.append('| '+' | '.join(str(v) if v is not None else '不明' for v in (
            phase,r['task_id'],r['reasoning_display_policy'],success,r.get('known_total_tokens'),
            r.get('unknown_usage_calls'),r.get('model_calls'),r.get('api_requests')))+' |')
    lines+=['','通常対照の校正であり新手法の採用判定を行わない. P111の元の採用基準と結果は変更しない.', '',
        '[全条件](all_conditions.csv)／[全生成試行](all_model_calls.csv)／[全表示判断](all_projections.csv)／'
        '[過去P111の全条件](historical_P111_conditions.csv)／[成否別の記述比較](summary.json)／[サーバー全費用](server_cost.json).','',
        '使用量不明の要求を０へ補完しない. known_logical_tokensは既知部分の合計であり、'
        '不明があれば全費用は未確定. control時間はwork内、work/setup/cleanupはfull内、'
        '評価とloadはserver内なので重複加算しない. cached tokenの減少を論理tokenや時間の削減と同一視しない.','',
        'P111参照の費用を今回の追加費用に加算しない. 初回の完全要求と計数は過去の３方式と照合する. '
        '全履歴の原文と生のモデル推論は非公開保存先に置く. '
        '未見12課題と原稿保留を維持する.','',
        '[固定比較](../../docs/experiments/P114_whole_task_public_only_history.md)／[全監査](../../reports/P114_comparison.json).']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    write(folder/'build_manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        builder_sha256=sha(Path(__file__)),source_audit_sha256=sha(root/'reports/P114_comparison.json'),
        historical_P111_audit_sha256=sha(root/'reports/P111_comparison.json'),
        private_source_sha256=private,public_artifact_sha256={p.name:sha(p) for p in sorted(folder.iterdir())},
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))
    print(json.dumps({k:summary[k] for k in ('model_attempts','unknown_usage_attempts','development_gate_met')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True);p.add_argument('--storage-root',type=Path,required=True)
    a=p.parse_args();build(a.repo_root.resolve(),a.storage_root.resolve())

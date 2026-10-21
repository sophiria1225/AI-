"""Generate all fixed export submissions before executing or judging them."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from data_export_probe import inputs, schedule, sha, submission
from local_llama import count_input
from model_provenance import check_live_model
from run_context_comparison import BudgetStop, Inference, write_json
from run_event_view_probe import inference_deadline, lease_remaining
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'sophiria1225/AI-'
ISSUES = {'P20': 95, 'P21': 99}


def store_frozen_file(source, destination, expected):
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('frozen file changed before archival')
    destination.write_bytes(data)


def publish(state, rows, issue_id):
    phase = state['phase']
    if phase not in ISSUES or issue_id != ISSUES[phase]:
        raise ValueError('progress is restricted to the matching research Issue')
    marker = f'<!-- harness-data-export:{phase}_01 -->'
    body = '\n'.join([marker, f'{phase}：同じ取得済み情報からの直接書出と計算コード', '',
        '１開発局面×２方式×３seed。新規方式・CodeAct完全再現・最終タスク成功の評価ではありません。',
        '全６出力の生成が終わってから内容を照合します。', '',
        '| Variant | Seed | Submission valid | Known tokens |', '|---|---:|---|---:|'] +
        [f"| {r['variant']} | {r['seed']} | {r['schema_valid']} | {r['known_tokens']} |" for r in rows] +
        ['', f"Status: {state['status']}; outputs {len(rows)}/6; known tokens "
         f"{state['known_total_tokens']}; unknown usage {state['unknown_usage_calls']}."])
    issue = f'repos/{REPOSITORY}/issues/{issue_id}'
    if state.get('comment_id'):
        endpoint = f'repos/{REPOSITORY}/issues/comments/{state["comment_id"]}'
        old = gh_api(endpoint)
        if old.get('issue_url') != 'https://api.github.com/'+issue or not old.get('body', '').startswith(marker):
            raise ValueError('unexpected progress comment')
        result = gh_api(endpoint, method='PATCH', payload={'body': body})
    else:
        info = gh_api(issue)
        if info['html_url'] != f'https://github.com/{REPOSITORY}/issues/{issue_id}':
            raise ValueError('unexpected repository')
        result = gh_api(issue+'/comments', method='POST', payload={'body': body})
    state.update(comment_id=result['id'], comment_url=result['html_url'])


def main():
    signal.signal(signal.SIGALRM, inference_deadline)
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--freeze-record', type=Path, required=True)
    p.add_argument('--publish', action='store_true')
    a = p.parse_args()
    plan, frozen = json.loads(a.plan.read_text()), json.loads(a.freeze_record.read_text())
    if plan['phase'] not in ISSUES or plan['run_id'] != plan['phase']+'_01':
        raise ValueError('unexpected phase/run identity')
    order = schedule(plan)
    source = a.storage_root/plan['input_root']
    if sha(a.plan) != frozen['plan_sha256'] or sha(source/'input.json') != frozen['input_sha256']:
        raise ValueError('frozen plan or input changed')
    if sha(source/'manifest.json') != frozen['input_manifest_sha256'] or order != frozen['schedule']:
        raise ValueError('frozen manifest or schedule changed')
    for name, digest in frozen['source_hashes'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('frozen source changed: '+name)
    case = json.loads((source/'input.json').read_text())
    config = json.loads((ROOT/plan['model_matches']).read_text())
    config.update(seed=plan['seeds'][0], agent_temperature=plan['temperature'],
                  max_calls=plan['max_calls'], max_total_tokens=plan['max_total_tokens'],
                  max_wall_seconds=plan['max_wall_seconds'], max_output_tokens=plan['max_output_tokens'])
    if 'call_timeout_seconds' in plan:
        config['model']['call_timeout_seconds'] = plan['call_timeout_seconds']
    runtime = json.loads((a.storage_root/'.runtime/model_server.json').read_text())
    command = subprocess.check_output(['ps', '-p', str(runtime['supervisor_pid']), '-o', 'command='], text=True)
    remaining, lease_end = lease_remaining(runtime, command, dt.datetime.now(dt.timezone.utc))
    if runtime['status'] != 'ready' or remaining < plan['max_wall_seconds']+600:
        raise ValueError('model lease must cover whole run plus margin')
    with urllib.request.urlopen(config['model']['base_url']+'/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(config['model_selection'], runtime, props, root=a.storage_root,
                     expected_ctx=config['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    out = a.storage_root/plan['output_root']
    out.mkdir(parents=True, exist_ok=False)
    store_frozen_file(a.plan, out/'plan.json', frozen['plan_sha256'])
    store_frozen_file(source/'input.json', out/'input_private.json', frozen['input_sha256'])
    store_frozen_file(source/'manifest.json', out/'input_manifest.json', frozen['input_manifest_sha256'])
    for name, value in [('freeze_record.json', frozen), ('schedule.json', order)]:
        write_json(out/name, value)
    write_json(out/'provenance.json', {'runtime': runtime, 'props': props, 'config': config,
               'server_lease_end_utc': lease_end,
               'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()})
    for name in frozen['source_hashes']:
        dest = out/'source'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    infer = Inference(config, out)
    rows, state = [], {'phase': plan['phase'], 'status': 'preflight', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}

    def update():
        state.update(known_total_tokens=infer.tokens, model_calls=len(infer.calls),
                     unknown_usage_calls=sum(c['status'] != 'ok' for c in infer.calls),
                     completed_outputs=len(rows), updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(out/'results.json', rows)
        write_json(out/'status.json', state)
        if a.publish:
            try:
                publish(state, rows, plan['publish_issue'])
                state.pop('publish_error', None)
            except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                state['publish_error'] = type(exc).__name__
            write_json(out/'status.json', state)

    update()
    try:
        counts = []
        for item in order:
            messages, tools = inputs(case, item['variant'])
            cfg = dict(config['model'], seed=item['seed'], temperature=plan['temperature'],
                       num_predict=plan['max_output_tokens'])
            count = count_input(cfg, messages, tools)
            if count['input_tokens']+plan['max_output_tokens'] > config['model']['num_ctx']:
                raise ValueError('fixed input exceeds context')
            counts.append({**item, **count})
        write_json(out/'input_counts.json', counts)
        if sum(c['input_tokens']+plan['max_output_tokens'] for c in counts) > plan['max_total_tokens']:
            raise ValueError('full design token bound exceeds budget')
        for item in order:
            state.update(status='running', active=item)
            update()
            messages, tools = inputs(case, item['variant'])
            infer.config['seed'] = item['seed']-sum(c['role'] == 'export' for c in infer.calls)
            message = infer.call('export', messages, tools)
            call = infer.calls[-1]
            try:
                if call['finish_reason'] == 'length':
                    raise ValueError('truncated submission')
                value = submission(message, item['variant'])
                write_json(out/call['id']/'submission_private.json', value)
                valid, error = True, None
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                valid, error = False, type(exc).__name__
            rows.append({**item, 'call_id': call['id'], 'schema_valid': valid, 'error_type': error,
                         'known_tokens': call['input_tokens']+call['output_tokens'],
                         'request_sha256': sha(out/call['id']/'request.json'),
                         'response_sha256': sha(out/call['id']/'response.json')})
            update()
        state.update(status='complete', active=None)
    except BudgetStop as exc:
        state.update(status='budget_stop', stop_reason=str(exc))
    except KeyboardInterrupt:
        state.update(status='interrupted', stop_reason='user_or_process_interrupt')
    except Exception as exc:
        state.update(status='runtime_error', error_type=type(exc).__name__)
        write_json(out/'error_private.json', {'type': type(exc).__name__, 'message': str(exc)})
    finally:
        state['wall_seconds'] = time.monotonic()-infer.started
        update()
    print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""P17: a bounded correction check, preserving the original P16 experiment."""
import argparse
import datetime as dt
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from context_preservation import parse_submission
from ledger_contract import inputs, validate
from local_llama import count_input
from model_provenance import check_live_model
from prepare_event_view_probe import sha
from run_context_comparison import BudgetStop, Inference, write_json
from run_event_view_probe import inference_deadline, lease_remaining
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'sophiria1225/AI-'
MARKER = '<!-- harness-ledger-contract:P17_01 -->'


def schedule(plan):
    if (plan['run_id'] != 'P17_01' or plan['variants'] != ['legacy', 'aligned'] or
            plan['seeds'] != [47, 48] or plan['max_calls'] != 16 or
            plan['case_ids'] != [f'case_{i:02d}_recorded' for i in range(1, 5)]):
        raise ValueError('unexpected fixed P17 design')
    rows = []
    for i, case_id in enumerate(plan['case_ids']):
        for j, seed in enumerate(plan['seeds']):
            offset = (i + j) % 2
            variants = plan['variants'][offset:] + plan['variants'][:offset]
            rows.extend({'case_id': case_id, 'variant': v, 'seed': seed} for v in variants)
    return rows


def publish(state, rows, issue_id):
    if issue_id != 71:
        raise ValueError('P17 progress is restricted to the approved research Issue')
    lines = [MARKER, 'P17: 台帳インターフェース修正の校正', '',
             '基準実装の不整合を直す比較。新規方式の性能評価・最終タスク成功ではありません。', '',
             '| Input | Variant | Seed | Schema valid | Known tokens |', '|---|---|---:|---:|---:|']
    lines += [f"| {r['case_id']} | {r['variant']} | {r['seed']} | {r['schema_valid']} | {r['known_tokens']} |"
              for r in rows]
    lines += ['', f"Status: {state['status']}; outputs {len(rows)}/16; "
                  f"known tokens {state['known_total_tokens']}; unknown usage {state['unknown_usage_calls']}.",
              '全出力終了後に内容を確認します。形式適合は意味の正しさを保証しません。']
    body = '\n'.join(lines) + '\n'
    issue = f'repos/{REPOSITORY}/issues/{issue_id}'
    if state.get('comment_id'):
        endpoint = f'repos/{REPOSITORY}/issues/comments/{state["comment_id"]}'
        old = gh_api(endpoint)
        if old.get('issue_url') != 'https://api.github.com/' + issue or not old.get('body', '').startswith(MARKER):
            raise ValueError('unexpected progress comment')
        result = gh_api(endpoint, method='PATCH', payload={'body': body})
    else:
        info = gh_api(issue)
        if info['html_url'] != f'https://github.com/{REPOSITORY}/issues/{issue_id}':
            raise ValueError('unexpected research Issue')
        result = gh_api(issue + '/comments', method='POST', payload={'body': body})
    state.update(comment_id=result['id'], comment_url=result['html_url'])


def main():
    signal.signal(signal.SIGALRM, inference_deadline)
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--freeze-record', type=Path, required=True)
    p.add_argument('--publish', action='store_true')
    args = p.parse_args()
    plan = json.loads(args.plan.read_text())
    frozen = json.loads(args.freeze_record.read_text())
    order = schedule(plan)
    input_root = args.storage_root / plan['input_root']
    manifest = json.loads((input_root / 'manifest.json').read_text())
    if sha(args.plan) != frozen['plan_sha256'] or sha(input_root / 'manifest.json') != frozen['input_manifest_sha256']:
        raise ValueError('fixed plan or input manifest changed')
    for name, digest in frozen['source_hashes'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('frozen source changed: ' + name)
    cases = {}
    for case_id in plan['case_ids']:
        entry, = [c for c in manifest['cases'] if c['case_id'] == case_id]
        path = input_root / (case_id + '.json')
        if sha(path) != entry['case_sha256'] or entry['condition'] != 'recorded':
            raise ValueError('fixed recorded input changed')
        cases[case_id] = json.loads(path.read_text())
    prerequisite = json.loads((args.storage_root / 'records/event_view_probe/P16_01/status.json').read_text())
    if prerequisite['status'] != 'complete':
        raise ValueError('P16 must finish before P17')
    config = json.loads((ROOT / plan['memory_model_matches']).read_text())
    config.update(seed=plan['seeds'][0], agent_temperature=plan['temperature'], max_calls=plan['max_calls'],
                  max_total_tokens=plan['max_total_tokens'], max_wall_seconds=plan['max_wall_seconds'],
                  max_output_tokens=plan['max_output_tokens'])
    runtime = json.loads((args.storage_root / '.runtime/model_server.json').read_text())
    command = subprocess.check_output(['ps', '-p', str(runtime['supervisor_pid']), '-o', 'command='], text=True)
    remaining, lease_end = lease_remaining(runtime, command, dt.datetime.now(dt.timezone.utc))
    if runtime['status'] != 'ready' or remaining < plan['max_wall_seconds'] + 600:
        raise ValueError('model server must cover the whole P17 budget plus margin')
    with urllib.request.urlopen(config['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(config['model_selection'], runtime, props, root=args.storage_root,
                     expected_ctx=config['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    out = args.storage_root / plan['output_root']
    out.mkdir(parents=True, exist_ok=False)
    for name, value in [('plan.json', plan), ('freeze_record.json', frozen),
                        ('input_manifest.json', manifest), ('schedule.json', order)]:
        write_json(out / name, value)
    write_json(out / 'provenance.json', {'runtime': runtime, 'props': props, 'config': config,
               'server_lease_end_utc': lease_end,
               'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()})
    for name in frozen['source_hashes']:
        target = out / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    infer = Inference(config, out)
    rows, state = [], {'status': 'preflight', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}

    def update():
        state.update(known_total_tokens=infer.tokens, model_calls=len(infer.calls),
                     unknown_usage_calls=sum(c['status'] != 'ok' for c in infer.calls),
                     completed_outputs=len(rows), updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(out / 'results.json', rows)
        write_json(out / 'status.json', state)
        if args.publish:
            try:
                publish(state, rows, plan['publish_issue'])
                state.pop('publish_error', None)
            except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                state['publish_error'] = type(exc).__name__
            write_json(out / 'status.json', state)

    update()
    try:
        counts = []
        count_cfg = dict(config['model'], seed=plan['seeds'][0], temperature=plan['temperature'],
                         num_predict=plan['max_output_tokens'])
        for item in order:
            messages, tool = inputs(cases[item['case_id']], item['variant'], config['observation_page_characters'])
            count = count_input(count_cfg, messages, [tool])
            if count['input_tokens'] + plan['max_output_tokens'] > config['model']['num_ctx']:
                raise ValueError('fixed input exceeds context limit')
            counts.append({**item, **count})
        write_json(out / 'input_counts.json', counts)
        if sum(r['input_tokens'] + plan['max_output_tokens'] for r in counts) > plan['max_total_tokens']:
            raise ValueError('full design upper token bound exceeds declared cap')
        for item in order:
            state.update(status='running', active=item)
            update()
            case = cases[item['case_id']]
            messages, tool = inputs(case, item['variant'], config['observation_page_characters'])
            infer.config['seed'] = item['seed'] - sum(c['role'] == 'ledger' for c in infer.calls)
            answer = infer.call('ledger', messages, [tool])
            call = infer.calls[-1]
            try:
                ledger = validate(parse_submission(answer, 'submit_ledger'), case, item['variant'])
                result = {'schema_valid': True, 'items': len(ledger['items']), 'error_type': None}
                write_json(out / call['id'] / 'ledger_private.json', ledger)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                result = {'schema_valid': False, 'items': None, 'error_type': type(exc).__name__}
            rows.append({**item, **result, 'call_id': call['id'],
                         'known_tokens': call['input_tokens'] + call['output_tokens'],
                         'request_sha256': sha(out / call['id'] / 'request.json'),
                         'response_sha256': sha(out / call['id'] / 'response.json')})
            update()
        state.update(status='complete', active=None)
    except BudgetStop as exc:
        state.update(status='budget_stop', stop_reason=str(exc))
    except KeyboardInterrupt:
        state.update(status='interrupted', stop_reason='user_or_process_interrupt')
    except Exception as exc:
        state.update(status='runtime_error', error_type=type(exc).__name__)
        write_json(out / 'error_private.json', {'type': type(exc).__name__, 'message': str(exc)})
    finally:
        state['wall_seconds'] = time.monotonic() - infer.started
        update()
    print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""P16: bounded memory-only generation after P14, no environment/evaluator calls."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shlex
import signal
import subprocess
import time
import urllib.request

from context_preservation import LEDGER_TOOL, parse_submission, validate_ledger
from execution_event_views import project_spans, rejected_before_dispatch
from local_llama import count_input
from model_provenance import check_live_model
from native_ledger_memory import draft_messages
from prepare_event_view_probe import sha
from run_context_comparison import BudgetStop, Inference, write_json
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'sophiria1225/AI-'
ISSUE = 71
MARKER = '<!-- harness-event-view-probe:P16_01 -->'


def inference_deadline(signum, frame):
    """Let model_call persist unknown usage instead of SIGALRM killing the run."""
    raise TimeoutError('local inference deadline')


def schedule(plan, manifest):
    if (plan['run_id'] != 'P16_01' or plan['variants'] != ['raw', 'execution_tag', 'quarantine']
            or len(manifest['cases']) != 2 * len(plan['source_runs'])):
        raise ValueError('unexpected fixed P16 schedule')
    expected = [(run, condition) for run in plan['source_runs'] for condition in plan['conditions']]
    if [(c['source_run'], c['condition']) for c in manifest['cases']] != expected:
        raise ValueError('case order or identity differs from fixed plan')
    rows = []
    for index, case in enumerate(manifest['cases']):
        variants = plan['variants']
        offset = index % len(variants)
        rows.extend({'case_id': case['case_id'], 'variant': variant,
                     'seed': plan['first_seed']} for variant in variants[offset:] + variants[:offset])
    if len(rows) != plan['max_calls']:
        raise ValueError('schedule and call cap disagree')
    return rows


def lease_remaining(runtime, command, now):
    args = shlex.split(command)
    if not any(Path(arg).name == 'serve_research_model.py' for arg in args):
        raise ValueError('model supervisor process identity differs')
    limit = int(args[args.index('--max-seconds') + 1])
    end = dt.datetime.fromisoformat(runtime['started_at']) + dt.timedelta(seconds=limit)
    return (end - now).total_seconds(), end.isoformat()


def messages_for(case, variant, page_limit):
    spans = project_spans(case['spans'], case['receipts'], variant=variant, consumer='memory')
    return draft_messages(case['task'], spans, list(spans), None, case['tools'], page_limit)


def structural_outcome(message, case):
    try:
        value = validate_ledger(parse_submission(message, 'submit_ledger'), set(case['spans']))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'schema_valid': False, 'error_type': type(exc).__name__, 'items': None,
                'done_items': None, 'done_only_rejected_sources': None}, None
    rejected = {sid for sid, span in case['spans'].items()
                if rejected_before_dispatch(span, case['receipts'].get(sid))}
    done = [item for item in value['items'] if item['status'] == 'done']
    return {'schema_valid': True, 'error_type': None, 'items': len(value['items']),
            'done_items': len(done),
            'done_only_rejected_sources': sum(set(i['source_ids']) <= rejected for i in done)}, value


def body(state, rows):
    lines = [MARKER, 'P16: fixed four-task event-view probe', '',
             'Memory generation only. Recorded observations and controlled pre-dispatch rejection are separate.',
             'A syntactically valid done entry or a rejected-only citation is NOT a semantic truth label.', '',
             '| Case | View | Valid schema | Known tokens |', '|---|---|---:|---:|']
    lines += [f"| {r['case_id']} | {r['variant']} | {r['schema_valid']} | {r['known_tokens']} |" for r in rows]
    lines += ['', f"Status: {state['status']}; completed outputs: {len(rows)}/24; "
              f"known tokens: {state.get('known_total_tokens', 0)}; "
              f"unknown-usage calls: {state.get('unknown_usage_calls', 0)}.",
              'Original records remain local. No task success, novelty or natural error frequency is claimed.']
    return '\n'.join(lines) + '\n'


def publish(text, state):
    endpoint = f'repos/{REPOSITORY}/issues/{ISSUE}'
    if state.get('comment_id'):
        endpoint = f'repos/{REPOSITORY}/issues/comments/{int(state["comment_id"])}'
        existing = gh_api(endpoint)
        if (existing.get('issue_url') != f'https://api.github.com/repos/{REPOSITORY}/issues/{ISSUE}'
                or not existing.get('body', '').startswith(MARKER)):
            raise ValueError('unexpected progress-comment identity')
        result = gh_api(endpoint, method='PATCH', payload={'body': text})
    else:
        issue = gh_api(endpoint)
        if issue['html_url'] != f'https://github.com/{REPOSITORY}/issues/{ISSUE}':
            raise ValueError('unexpected Issue identity')
        result = gh_api(endpoint + '/comments', method='POST', payload={'body': text})
    state.update(comment_id=result['id'], comment_url=result['html_url'])


def main():
    signal.signal(signal.SIGALRM, inference_deadline)
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--freeze-record', type=Path, required=True)
    p.add_argument('--publish', action='store_true')
    args = p.parse_args()
    plan = json.loads(args.plan.read_text())
    manifest = json.loads((args.inputs / 'manifest.json').read_text())
    frozen = json.loads(args.freeze_record.read_text())
    if manifest['plan_sha256'] != sha(args.plan) or frozen['plan_sha256'] != sha(args.plan):
        raise ValueError('plan changed after input preparation or freeze')
    if frozen['input_manifest_sha256'] != sha(args.inputs / 'manifest.json'):
        raise ValueError('input manifest changed')
    for name, digest in frozen['source_hashes'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('frozen source changed: ' + name)
    cases = {}
    for row in manifest['cases']:
        path = args.inputs / (row['case_id'] + '.json')
        if sha(path) != row['case_sha256']:
            raise ValueError('input case changed')
        cases[row['case_id']] = json.loads(path.read_text())
    order = schedule(plan, manifest)
    prerequisite = json.loads((args.storage_root / 'records/context_pilot' /
                               plan['wait_for_batch'] / 'status.json').read_text())
    if prerequisite['status'] != 'complete' or len(prerequisite['completed']) != 4:
        raise ValueError('P14 must finish before any P16 model request')
    config = json.loads((ROOT / plan['memory_model_matches']).read_text())
    config.update(seed=plan['first_seed'], agent_temperature=plan['temperature'],
                  max_calls=plan['max_calls'], max_total_tokens=plan['max_total_tokens'],
                  max_wall_seconds=plan['max_wall_seconds'], max_output_tokens=plan['max_output_tokens'])
    runtime = json.loads((args.storage_root / '.runtime/model_server.json').read_text())
    command = subprocess.check_output(['ps', '-p', str(runtime['supervisor_pid']), '-o', 'command='], text=True)
    remaining, lease_end = lease_remaining(runtime, command, dt.datetime.now(dt.timezone.utc))
    if runtime['status'] != 'ready' or remaining < plan['max_wall_seconds'] + 600:
        raise ValueError('ready model server must cover the whole fixed P16 budget plus margin')
    with urllib.request.urlopen(config['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(config['model_selection'], runtime, props, root=args.storage_root,
                     expected_ctx=config['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    out = args.storage_root / plan['output_root']
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'plan.json', plan)
    write_json(out / 'freeze_record.json', frozen)
    write_json(out / 'input_manifest.json', manifest)
    write_json(out / 'schedule.json', order)
    write_json(out / 'provenance.json', {'runtime': runtime, 'props': props,
               'server_lease_end_utc': lease_end, 'config': config,
               'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()})
    for name in frozen['source_hashes']:
        target = out / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    infer = Inference(config, out)
    rows = []
    state = {'status': 'preflight', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}

    def update():
        state.update(known_total_tokens=infer.tokens,
                     unknown_usage_calls=sum(c['status'] != 'ok' for c in infer.calls),
                     model_calls=len(infer.calls), completed_outputs=len(rows),
                     updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(out / 'results.json', rows)
        write_json(out / 'status.json', state)
        public = body(state, rows)
        (out / 'progress.md').write_text(public)
        if args.publish:
            try:
                publish(public, state)
                state.pop('publish_error', None)
            except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                state['publish_error'] = type(exc).__name__
            write_json(out / 'status.json', state)

    update()
    try:
        counts = []
        count_cfg = dict(config['model'], seed=plan['first_seed'], temperature=plan['temperature'],
                         num_predict=plan['max_output_tokens'])
        for item in order:
            messages = messages_for(cases[item['case_id']], item['variant'], config['observation_page_characters'])
            count = count_input(count_cfg, messages, [LEDGER_TOOL])
            if count['input_tokens'] + plan['max_output_tokens'] > config['model']['num_ctx']:
                raise ValueError('prepared input exceeds fixed context limit')
            counts.append({**item, **count})
        write_json(out / 'input_counts.json', counts)
        for item in order:
            state.update(status='running', active=item)
            update()
            case = cases[item['case_id']]
            messages = messages_for(case, item['variant'], config['observation_page_characters'])
            # Inference increments seeds per role. Compensate to keep the fixed
            # paired seed, and retain the actual request payload for auditing.
            infer.config['seed'] = item['seed'] - sum(c['role'] == 'ledger' for c in infer.calls)
            answer = infer.call('ledger', messages, [LEDGER_TOOL])
            call = infer.calls[-1]
            result, ledger = structural_outcome(answer, case)
            if ledger is not None:
                write_json(out / call['id'] / 'ledger_private.json', ledger)
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

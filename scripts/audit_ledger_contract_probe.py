"""Audit terminal P17 artifacts against frozen inputs; never run models or tasks."""
import argparse
import json
from pathlib import Path

from audit_event_view_probe import digest, read, sha
from context_preservation import parse_submission
from ledger_contract import inputs as make_inputs, validate
from local_llama import parse_response, payload_for
from run_ledger_contract_probe import schedule

ROOT = Path(__file__).resolve().parents[1]


def outcome(message, case, variant):
    try:
        ledger = validate(parse_submission(message, 'submit_ledger'), case, variant)
        return {'schema_valid': True, 'items': len(ledger['items']), 'error_type': None}, ledger
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'schema_valid': False, 'items': None, 'error_type': type(exc).__name__}, None


def audit(run, inputs):
    state, plan, manifest, frozen, provenance = [read(run/name) for name in (
        'status.json', 'plan.json', 'input_manifest.json', 'freeze_record.json', 'provenance.json')]
    if state['status'] in ('running', 'preflight'):
        raise ValueError('wait for terminal P17 status')
    errors = []

    def check(condition, label):
        if not condition:
            errors.append(label)

    source_plan = run/'source/configs/P17_ledger_contract_v01.json'
    check(sha(source_plan) == frozen['plan_sha256'], 'plan hash')
    check(read(source_plan) == plan, 'saved plan')
    check(sha(inputs/'manifest.json') == frozen['input_manifest_sha256'], 'input manifest hash')
    check(read(inputs/'manifest.json') == manifest, 'saved input manifest')
    for name, expected in frozen['source_hashes'].items():
        check(sha(run/'source'/name) == expected, 'archived source '+name)
        check(sha(ROOT/name) == expected, 'audit dependency '+name)
    cases = {}
    for case_id in plan['case_ids']:
        row, = [c for c in manifest['cases'] if c['case_id'] == case_id]
        path = inputs/(case_id+'.json')
        check(sha(path) == row['case_sha256'], 'case hash '+case_id)
        check(row['condition'] == 'recorded', 'recorded input '+case_id)
        cases[case_id] = read(path)
    order = schedule(plan)
    check(read(run/'schedule.json') == order, 'fixed schedule')
    counts = read(run/'input_counts.json') if (run/'input_counts.json').exists() else []
    usages = read(run/'usage.json') if (run/'usage.json').exists() else []
    results = read(run/'results.json')
    config = provenance['config']
    rows = []
    for index, usage in enumerate(usages):
        if index >= len(order):
            errors.append('extra model call')
            break
        item = order[index]
        directory = run/usage['id']
        request, response = read(directory/'request.json'), read(directory/'response.json')
        cfg = dict(config['model'], seed=item['seed'], temperature=plan['temperature'],
                   num_predict=plan['max_output_tokens'])
        messages, tool = make_inputs(cases[item['case_id']], item['variant'],
                                     config['observation_page_characters'])
        check(request == payload_for(cfg, messages, [tool]), usage['id']+' request')
        for key in ('status', 'input_tokens', 'output_tokens'):
            check(usage[key] == response[key], usage['id']+' usage '+key)
        check(index < len(counts) and counts[index]['input_tokens'] == usage['predicted_input_tokens'],
              usage['id']+' input preflight')
        ledger = None
        if response['status'] == 'ok':
            raw = parse_response(read(directory/'raw_response.json'))
            check(all(raw[k] == response[k] for k in raw), usage['id']+' terminal response')
            check(usage['input_tokens'] == usage['predicted_input_tokens'], usage['id']+' counted input')
            result, ledger = outcome(response['message'], cases[item['case_id']], item['variant'])
            check(index < len(results), usage['id']+' result exists')
            if index < len(results):
                saved = results[index]
                check(all(saved[k] == item[k] for k in item), usage['id']+' result schedule')
                check(saved['call_id'] == usage['id'], usage['id']+' result call')
                check(all(saved[k] == v for k, v in result.items()), usage['id']+' result outcome')
                check(saved['known_tokens'] == usage['input_tokens']+usage['output_tokens'], usage['id']+' result cost')
                for name in ('request', 'response'):
                    check(saved[name+'_sha256'] == sha(directory/(name+'.json')), usage['id']+' '+name+' hash')
            if ledger is not None:
                check(read(directory/'ledger_private.json') == ledger, usage['id']+' parsed ledger')
        else:
            check(usage['input_tokens'] is None and usage['output_tokens'] is None,
                  usage['id']+' unknown cost remains null')
            check(index == len(usages)-1, usage['id']+' did not continue after unknown cost')
            result = {'schema_valid': None, 'items': None, 'error_type': None}
        rows.append({**item, **result, 'condition': 'recorded', 'call_id': usage['id'],
                     'status': usage['status'], 'input_tokens': usage['input_tokens'],
                     'output_tokens': usage['output_tokens'], 'wall_seconds': usage['wall_seconds'],
                     'done_items': sum(i['status'] == 'done' for i in ledger['items']) if ledger else None,
                     'request_sha256': sha(directory/'request.json'),
                     'response_sha256': sha(directory/'response.json'),
                     'prepared_request_digest': digest(request)})
    tokens = sum(r['input_tokens']+r['output_tokens'] for r in rows if r['status'] == 'ok')
    unknown = sum(r['status'] != 'ok' for r in rows)
    check(state['model_calls'] == len(usages), 'status calls')
    check(state['completed_outputs'] == len(results), 'status outputs')
    check(state['known_total_tokens'] == tokens, 'status tokens')
    check(state['unknown_usage_calls'] == unknown, 'status unknown')
    check(len(results) == sum(r['status'] == 'ok' for r in rows), 'result count')
    check(tokens <= plan['max_total_tokens'], 'total token cap')
    if state['status'] == 'complete':
        check(len(rows) == plan['max_calls'] and unknown == 0, 'complete run size')
    groups = []
    for variant in plan['variants']:
        group = [r for r in rows if r['variant'] == variant]
        groups.append({'condition': 'recorded', 'variant': variant, 'seeds': plan['seeds'],
                       'calls': len(group), 'schema_valid': sum(r['schema_valid'] is True for r in group),
                       'known_tokens': sum(r['input_tokens']+r['output_tokens'] for r in group if r['status'] == 'ok'),
                       'unknown_usage_calls': sum(r['status'] != 'ok' for r in group)})
    return {'run_id': plan['run_id'], 'status': state['status'], 'audit_errors': errors,
            'calls': len(usages), 'known_total_tokens': tokens, 'unknown_usage_calls': unknown,
            'wall_seconds': state['wall_seconds'], 'rows': rows, 'groups': groups,
            'source_hashes': {name: sha(run/name) for name in (
                'status.json', 'plan.json', 'provenance.json', 'results.json', 'freeze_record.json')},
            'auditor_sha256': sha(Path(__file__)), 'additional_model_calls': 0,
            'environment_requests': 0, 'evaluation_files_read': False,
            'semantic_scope': 'Four known development inputs, two paired seeds per interface. '
                              'Schema calibration of our baseline, not new-method efficacy or final task success. '
                              'Invalid outputs and unknown costs remain separate; no independent human labels.',
            'scope': 'Frozen request, source, input, response, structure and cost audit. Semantic review is separate.'}


def main():
    parser = argparse.ArgumentParser()
    for name in ('run', 'inputs', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run, args.inputs)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: report[k] for k in ('status', 'calls', 'known_total_tokens', 'unknown_usage_calls', 'audit_errors')}))
    return bool(report['audit_errors'])


if __name__ == '__main__':
    raise SystemExit(main())

"""Judge all P20 exports after the whole batch; public evidence only."""
import argparse
import csv
import io
import json
from pathlib import Path
import time

from data_export_probe import inputs, schedule, sha, submission
from data_python import run_program
from local_llama import payload_for, parse_response

ROOT = Path(__file__).resolve().parents[1]


def expected_from_observations(case):
    wanted, known = set(), {}
    for obs in case['observations']:
        name, value = obs['api'], obs['result']
        if name == 'spotify__show_song_library':
            for row in value:
                wanted.add(row['song_id'])
                known[row['song_id']] = row
        elif name in ('spotify__show_album_library', 'spotify__show_playlist_library'):
            wanted.update(i for row in value for i in row['song_ids'])
        elif name == 'spotify__show_song':
            known[value['song_id']] = value
        else:
            raise ValueError('unexpected source API')
    if wanted-known.keys():
        raise ValueError('not all source metadata observed')
    if any('|' in a['name'] for i in wanted for a in known[i]['artists']):
        raise ValueError('ambiguous artist separator')
    pairs = {(known[i]['title'], tuple(sorted(a['name'] for a in known[i]['artists']))) for i in wanted}
    if len(pairs) != len(wanted):
        raise ValueError('distinct song IDs have ambiguous exported fields')
    return pairs


def check_csv(content, expected):
    reader = csv.DictReader(io.StringIO(content), strict=True)
    if reader.fieldnames != ['Title', 'Artists']:
        raise ValueError('header mismatch')
    rows = list(reader)
    if any(set(r) != {'Title', 'Artists'} or None in r.values() for r in rows):
        raise ValueError('row shape mismatch')
    pairs = [(r['Title'], tuple(sorted(r['Artists'].split('|')))) for r in rows]
    actual = set(pairs)
    return {'rows': len(rows), 'unique_rows': len(actual), 'missing': len(expected-actual),
            'extra': len(actual-expected), 'duplicates': len(rows)-len(actual),
            'complete_export': actual == expected and len(rows) == len(actual)}


def evaluate(directory):
    state = json.loads((directory/'status.json').read_text())
    if state['status'] != 'complete':
        raise ValueError('all fixed generations must finish before judging content')
    plan = json.loads((directory/'plan.json').read_text())
    frozen = json.loads((directory/'freeze_record.json').read_text())
    config = json.loads((directory/'provenance.json').read_text())['config']
    case = json.loads((directory/'input_private.json').read_text())
    if sha(directory/'input_private.json') != frozen['input_sha256'] or sha(directory/'plan.json') != frozen['plan_sha256']:
        raise ValueError('frozen input or plan changed')
    for name, expected in frozen['source_hashes'].items():
        if sha(directory/'source'/name) != expected or sha(ROOT/name) != expected:
            raise ValueError('frozen generation/evaluation source changed')
    order = schedule(plan)
    if json.loads((directory/'schedule.json').read_text()) != order:
        raise ValueError('schedule changed')
    usage = json.loads((directory/'usage.json').read_text())
    original_rows = json.loads((directory/'results.json').read_text())
    if len(usage) != len(order) or len(original_rows) != len(order) or any(c['status'] != 'ok' for c in usage):
        raise ValueError('incomplete or unknown-usage batch')
    analysis = directory/'evaluation_v01'
    analysis.mkdir(exist_ok=False)
    expected = expected_from_observations(case)
    rows = []
    for i, (item, call, original) in enumerate(zip(order, usage, original_rows), 1):
        call_id = f'call_{i:03d}'
        if call['id'] != call_id or original['call_id'] != call_id or any(original[k] != item[k] for k in item):
            raise ValueError('call order mismatch')
        request = json.loads((directory/call_id/'request.json').read_text())
        response = json.loads((directory/call_id/'response.json').read_text())
        raw = json.loads((directory/call_id/'raw_response.json').read_text())
        parsed = parse_response(raw)
        messages, tools = inputs(case, item['variant'])
        cfg = dict(config['model'], seed=item['seed'], temperature=plan['temperature'], num_predict=plan['max_output_tokens'])
        if request != payload_for(cfg, messages, tools):
            raise ValueError('request differs from fixed public input')
        if sha(directory/call_id/'request.json') != original['request_sha256'] or sha(directory/call_id/'response.json') != original['response_sha256']:
            raise ValueError('record hash mismatch')
        for key in ('message', 'input_tokens', 'output_tokens', 'done_reason'):
            if response[key] != parsed[key]:
                raise ValueError('raw response mismatch')
        if (call['input_tokens'] != response['input_tokens'] or call['output_tokens'] != response['output_tokens']
                or call['input_tokens'] != call['predicted_input_tokens']):
            raise ValueError('usage mismatch')
        result = {**item, 'call_id': call_id, 'known_tokens': call['input_tokens']+call['output_tokens'],
                  'schema_valid': original['schema_valid'], 'program_executed': False,
                  'program_steps': None, 'csv_valid': False, 'complete_export': False, 'error_type': None}
        started = time.monotonic()
        try:
            if not original['schema_valid'] or call['finish_reason'] == 'length':
                raise ValueError('invalid or truncated submission')
            value = submission(response['message'], item['variant'])
            if value != json.loads((directory/call_id/'submission_private.json').read_text()):
                raise ValueError('submission record differs')
            if item['variant'] == 'data_program':
                program = run_program(value['code'], case['observations'])
                content = program['content']
                result.update(program_executed=True, program_steps=program['steps'])
            else:
                content = value['content']
            (analysis/(call_id+'.csv')).write_text(content)
            result.update(check_csv(content, expected), csv_valid=True)
        except Exception as exc:
            result['error_type'] = type(exc).__name__
            (analysis/(call_id+'_error_private.json')).write_text(json.dumps(
                {'type': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False, indent=2)+'\n')
        result['evaluation_seconds'] = time.monotonic()-started
        rows.append(result)
    if sum(r['known_tokens'] for r in rows) != state['known_total_tokens']:
        raise ValueError('batch total mismatch')
    groups = [{'variant': variant, 'outputs': sum(r['variant'] == variant for r in rows),
               'complete_exports': sum(r['variant'] == variant and r['complete_export'] for r in rows),
               'known_tokens': sum(r['known_tokens'] for r in rows if r['variant'] == variant)}
              for variant in plan['variants']]
    return {'phase': 'P20', 'plan_sha256': frozen['plan_sha256'], 'input_sha256': frozen['input_sha256'],
            'expected_unique_public_pairs': len(expected), 'outputs': rows, 'groups': groups,
            'model_calls': len(usage), 'known_total_tokens': state['known_total_tokens'],
            'unknown_usage_calls': 0, 'audit_errors': [], 'evaluator_source_sha256': sha(Path(__file__)),
            'environment_requests': 0, 'hidden_evaluator_loaded': False, 'reserved_tasks_read': 0,
            'scope': plan['scope'], 'limitations': plan['limitations']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = evaluate(a.run_dir)
    with a.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'groups': result['groups'], 'audit_errors': result['audit_errors']}))

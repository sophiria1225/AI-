"""After P21 primary evaluation, apply the separately frozen supplementary checks."""
import argparse
import json
from pathlib import Path
import time

from audit_export_generation import audit
from data_export_probe import inputs, schedule, sha, submission
from evaluate_data_export_probe_v02 import check_csv, expected_from_observations
from export_robustness import TRANSFORMS, inspect_program
from data_python import run_program
from local_llama import payload_for, parse_response

ROOT = Path(__file__).resolve().parents[1]


def evaluate(directory, primary_path, supplement_path, original_plan):
    state = json.loads((directory/'status.json').read_text())
    if state['status'] != 'complete':
        raise ValueError('all fixed generations must finish before supplementary evaluation')
    frozen = json.loads((directory/'freeze_record.json').read_text())
    supplement = json.loads(supplement_path.read_text())
    plan = json.loads((directory/'plan.json').read_text())
    primary = json.loads(primary_path.read_text())
    if (plan['phase'] != 'P21' or primary['phase'] != 'P21'
            or primary['audit_errors'] or primary['model_calls'] != 6
            or supplement['generation_status_at_freeze'] != 'running'
            or supplement['model_output_content_inspected'] is not False
            or supplement['transformations'] != list(TRANSFORMS)):
        raise ValueError('unexpected evaluation scope')
    if (sha(original_plan) != frozen['plan_sha256']
            or json.loads(original_plan.read_text()) != plan
            or sha(directory/'input_private.json') != frozen['input_sha256']
            or primary['input_sha256'] != frozen['input_sha256']
            or primary['plan_sha256'] != frozen['plan_sha256']
            or supplement['primary_input_sha256'] != frozen['input_sha256']
            or supplement['primary_plan_sha256'] != frozen['plan_sha256']):
        raise ValueError('primary input or plan changed')
    for name, digest in frozen['source_hashes'].items():
        if sha(directory/'source'/name) != digest or sha(ROOT/name) != digest:
            raise ValueError('primary source changed')
    for name, digest in supplement['source_hashes'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('supplementary source changed')
    audited = audit(directory)
    order = schedule(plan)
    if json.loads((directory/'schedule.json').read_text()) != order:
        raise ValueError('generation schedule changed')
    case = json.loads((directory/'input_private.json').read_text())
    config = json.loads((directory/'provenance.json').read_text())['config']
    original = json.loads((directory/'results.json').read_text())
    if len(primary['outputs']) != len(order):
        raise ValueError('incomplete primary evaluation')
    expected = expected_from_observations(case)
    rows = []
    for i, (item, checked, prior, recorded) in enumerate(zip(order, audited['outputs'], primary['outputs'], original), 1):
        cid = f'call_{i:03d}'
        if any(row['call_id'] != cid or any(row[k] != item[k] for k in item)
               for row in (checked, prior, recorded)):
            raise ValueError('primary call order mismatch')
        request = json.loads((directory/cid/'request.json').read_text())
        messages, tools = inputs(case, item['variant'])
        cfg = dict(config['model'], seed=item['seed'], temperature=plan['temperature'], num_predict=plan['max_output_tokens'])
        if request != payload_for(cfg, messages, tools) or sha(directory/cid/'request.json') != recorded['request_sha256']:
            raise ValueError('request changed')
        row = dict(item, call_id=cid, primary_complete_export=prior['complete_export'],
                   eligible=False, skip_reason=None, checks=[], wall_seconds=0.0)
        if item['variant'] != 'data_program':
            row['skip_reason'] = 'fixed_csv_not_a_reexecutable_program'
        elif not checked['schema_valid']:
            row['skip_reason'] = 'unsubmitted_truncated_or_invalid_program'
        else:
            message = parse_response(json.loads((directory/cid/'raw_response.json').read_text()))['message']
            value = submission(message, item['variant'])
            if value != json.loads((directory/cid/'submission_private.json').read_text()):
                raise ValueError('stored program changed')
            nominal = False
            try:
                nominal = check_csv(run_program(value['code'], case['observations'])['content'], expected)['complete_export']
            except Exception:
                pass
            if nominal != prior['complete_export']:
                raise ValueError('nominal evaluation disagrees')
            started = time.monotonic()
            row.update(eligible=True, checks=inspect_program(value['code'], case))
            row['wall_seconds'] = time.monotonic()-started
        rows.append(row)
    eligible = [r for r in rows if r['eligible']]
    return {'phase': 'P21_supplementary', 'outputs': rows,
            'eligible_programs': len(eligible),
            'programs_passing_all_four': sum(all(c['complete_export'] for c in r['checks']) for r in eligible),
            'primary_result_sha256': sha(primary_path), 'supplement_sha256': sha(supplement_path),
            'input_sha256': frozen['input_sha256'], 'new_model_calls': 0, 'environment_requests': 0,
            'scope': 'Analyst-defined task-specific input transformations; no repair, no literal/program rate comparison, no independent new tasks or novelty claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--primary-result', type=Path, required=True)
    parser.add_argument('--supplement-freeze', type=Path, required=True)
    parser.add_argument('--original-plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.run_dir, args.primary_result, args.supplement_freeze, args.original_plan)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('eligible_programs', 'programs_passing_all_four', 'new_model_calls')}))

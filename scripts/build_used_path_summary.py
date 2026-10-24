"""Publish all metadata rows of a closed P109 diagnosis; no private inputs."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def save_csv(path, rows, fields=None):
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True)
                if isinstance(v, (dict, list, tuple)) else v for k, v in row.items()})


def build(root):
    source = root / 'reports/P109_used_paths.json'
    data = json.loads(source.read_text())
    if data['status'] != 'complete' or data['errors'] or len(data['rows']) != 2:
        raise ValueError('all_two_completed_diagnosis_rows_required')
    directory = root / 'materials/20261025_p109_results'
    directory.mkdir()
    conditions = []; calls = []; programs = []; sites = []; requests = []
    for row in data['rows']:
        tags = dict(run_id=row['run_id'], policy=row['policy'])
        all_sites = [s for p in row['programs'] for s in p['sites']]
        artist_requests = [r for r in row['acquisition_history']['requests']
                           if r['api'] == 'spotify__show_artist']
        conditions.append(dict(**tags, original_success=row['original_success'],
            original_stop_reason=row['original_stop_reason'],
            original_known_total_tokens=row['original_known_total_tokens'],
            original_API_requests=row['original_API_requests'], model_calls=len(row['calls']),
            syntax_programs=row['syntax_programs'], API_syntax_sites=len(all_sites),
            actual_artist_requests=len(artist_requests),
            artist_requests_with_prior_name=sum(bool(r['prior_artist_name_observations']) for r in artist_requests),
            artist_requests_with_matching_prior_name=sum(r['prior_artist_name_matches_current'] is True for r in artist_requests),
            artist_requests_with_conflicting_prior_names=sum(r['prior_artist_names_conflict'] for r in artist_requests),
            **row['acquisition_history']['counts'],
            input_character_exposures=row['input_character_exposures'],
            output_character_totals=row['output_character_totals'],
            final_input_components=row['calls'][-1]['input'],
            final_input_tokens=row['calls'][-1]['input_tokens'],
            whole_task_savings_established=False))
        for call in row['calls']:
            calls.append(dict(**tags, **{k: v for k, v in call.items() if k not in ('input', 'output')},
                **{'input_' + k: v for k, v in call['input'].items()},
                **{'output_' + k: v for k, v in call['output'].items()}))
        for program in row['programs']:
            programs.append(dict(**tags, **{k: v for k, v in program.items() if k != 'sites'}))
            sites.extend(dict(**tags, record_name=program['record_name'], **site) for site in program['sites'])
        requests.extend(dict(**tags, **r) for r in row['acquisition_history']['requests'])
    save_csv(directory / 'all_conditions.csv', conditions)
    save_csv(directory / 'all_model_calls.csv', calls)
    save_csv(directory / 'all_programs.csv', programs)
    save_csv(directory / 'all_API_syntax_sites.csv', sites)
    save_csv(directory / 'all_actual_API_requests.csv', requests)
    save_json(directory / 'summary.json', dict(source_sha256=sha(source), conditions=conditions,
        actual_model_calls=len(calls), actual_API_requests=len(requests), syntax_programs=len(programs),
        API_syntax_sites=len(sites), analysis_wall_seconds=data['wall_seconds'],
        model_generations=0, environment_API_requests=0, saved_code_executions=0, evaluations=0,
        character_counts_are_not_token_counts=True, manuscript_changed=False))
    save_json(directory / 'build_manifest.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=sha(source), builder_sha256=sha(Path(__file__)),
        output_sha256={p.name: sha(p) for p in sorted(directory.iterdir())},
        all_original_cells_retained=True, no_private_content_published=True))
    print(json.dumps(dict(conditions=len(conditions), model_calls=len(calls), programs=len(programs),
        syntax_sites=len(sites), actual_API_requests=len(requests))))


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])

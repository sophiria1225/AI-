"""Describe pagination in saved public observations; never certify task coverage.

Query identity, including authorization and filters, is kept only in memory.
Exports contain no argument values, result rows, evaluator bodies, or reasoning.
The observation model assumes no relevant cross-app/external mutation; that
assumption is NOT verified by this descriptive audit.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack(value):
    return json.loads(value) if isinstance(value, str) else value


def group_status(pages, unknown, changed):
    if changed:
        return 'inconsistent_page_replay'
    if unknown or not pages:
        return 'inconclusive_response'
    if any(n > limit for _, n, limit in pages):
        return 'over_limit_response'
    counts = {p: n for p, n, _ in pages}
    terminal = sorted(p for p, n, limit in pages if n < limit)
    if not terminal:
        return 'no_terminal_observed'
    first = terminal[0]
    if any(p > first and n > 0 for p, n in counts.items()):
        return 'inconsistent_after_terminal'
    # Avoid allocating a potentially enormous range from untrusted page_index.
    prefix = sorted(p for p in counts if p <= first)
    if len(prefix) != first + 1 or any(p != i for i, p in enumerate(prefix)):
        return 'gap_before_terminal'
    return 'contiguous_terminal_observed'


def audit_spans(spans, schemas):
    epochs = defaultdict(int)
    groups = {}
    unclassified = []
    writes = Counter()
    paginated_calls = 0
    for sid, span in spans.items():
        action = span.get('action') or {}
        name = action.get('name')
        receipt = span.get('observation') or {}
        if not isinstance(name, str) or '__' not in name or 'observation' not in receipt:
            continue
        app, _ = name.split('__', 1)
        schema = schemas.get(name)
        if not schema or schema.get('method') not in ('GET', 'HEAD', 'OPTIONS'):
            epochs[app] += 1
            writes[app] += 1
            continue
        params = {p['name']: p for p in schema.get('parameters', [])}
        if schema['method'] != 'GET' or not {'page_index', 'page_limit'} <= params.keys():
            continue
        paginated_calls += 1
        try:
            args = unpack(action.get('arguments', '{}'))
        except (ValueError, TypeError):
            args = None
        reason = None
        if not isinstance(args, dict):
            reason = 'non_object_arguments'
        elif any(p.get('required') and k not in args for k, p in params.items()):
            reason = 'missing_required_argument'
        elif args.keys() - params.keys():
            reason = 'unknown_argument'
        if reason:
            unclassified.append(dict(span_id=sid, api=name, reason=reason))
            continue
        normalized = {k: args[k] if k in args else p.get('default') for k, p in params.items()}
        page, limit = normalized.pop('page_index'), normalized['page_limit']
        if type(page) is not int or page < 0 or type(limit) is not int or limit < 1:
            unclassified.append(dict(span_id=sid, api=name, reason='invalid_page_parameters'))
            continue
        key = (name, epochs[app], json.dumps(normalized, sort_keys=True, ensure_ascii=False))
        if key not in groups:
            groups[key] = dict(group_id=f'q{len(groups)+1:03d}', api=name,
                               app=app, epoch=epochs[app], pages=[], unknown=[], seen={}, changed=False)
        group = groups[key]
        try:
            data = unpack(receipt['observation'])
        except (ValueError, TypeError):
            data = None
        if not isinstance(data, list):
            group['unknown'].append(sid)
            unclassified.append(dict(span_id=sid, api=name, reason='non_list_response'))
            continue
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if page in group['seen'] and group['seen'][page] != fingerprint:
            group['changed'] = True
        group['seen'][page] = fingerprint
        group['pages'].append(dict(span_id=sid, page_index=page, count=len(data), page_limit=limit))
    result = []
    for group in groups.values():
        pages = group['pages']
        status = group_status([(p['page_index'], p['count'], p['page_limit']) for p in pages],
                              group['unknown'], group['changed'])
        result.append(dict(group_id=group['group_id'], api=group['api'], epoch=group['epoch'],
                           status=status, pages=pages, unclassified_span_ids=group['unknown'],
                           later_same_app_write=group['epoch'] != epochs[group['app']]))
    return dict(paginated_calls=paginated_calls, groups=result, unclassified_calls=unclassified,
                potential_write_requests=dict(writes),
                group_status_counts=dict(Counter(g['status'] for g in result)),
                any_no_terminal=any(g['status']=='no_terminal_observed' for g in result),
                any_no_terminal_without_later_app_write=any(
                    g['status']=='no_terminal_observed' and not g['later_same_app_write'] for g in result))


def load_schemas(data_root):
    schemas, hashes = {}, {}
    paths = sorted((data_root / 'api_docs/standard').glob('*.json'))
    if not paths:
        raise ValueError('public API schemas not found')
    for path in paths:
        if path.stem == 'admin':
            raise ValueError('admin schema is not an allowed public source')
        raw = json.loads(path.read_text())
        hashes[str(path.relative_to(data_root))] = digest(path)
        for name, spec in raw.items():
            if spec['app_name'] != path.stem or spec['api_name'] != name:
                raise ValueError('schema name mismatch')
            schemas[path.stem + '__' + name] = spec
    return schemas, hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('preserve the existing audit; choose a new output file')
    plan = json.loads(args.plan.read_text())
    rows = plan['trials']
    if (len(rows) != 16 or len({r['task_id'] for r in rows}) != 16
            or Counter(r['phase'] for r in rows) != {'P10': 2, 'P11': 4, 'P18': 4, 'P22': 6}
            or plan.get('live_runs_allowed') is not False):
        raise ValueError('not the fixed completed development cohort')
    schemas, schema_hashes = load_schemas(args.data_root)
    trials = []
    for row in rows:
        measurement = args.repo_root / row['measurement_source']
        matches = [m for m in json.loads(measurement.read_text())['trials'] if m['run_id']==row['run_id']]
        if len(matches) != 1 or matches[0]['task_id'] != row['task_id']:
            raise ValueError('completed measurement identity mismatch')
        m = matches[0]
        path = args.storage_root / 'records/context_pilot' / row['run_id'] / 'spans.json'
        analysis = audit_spans(json.loads(path.read_text()), schemas)
        trials.append(dict(run_id=row['run_id'], task_id=row['task_id'],
                           official_success=m['evaluation']['official_success'],
                           declared_complete=m['declared_complete'], stop_reason=m['stop_reason'],
                           source_hashes={'spans':digest(path), 'measurement':digest(measurement)}, **analysis))
    strata = []
    for success in (True, False):
        subset = [t for t in trials if t['official_success'] is success]
        strata.append(dict(official_success=success, tasks=len(subset),
                           with_paginated_calls=sum(t['paginated_calls']>0 for t in subset),
                           with_any_no_terminal=sum(t['any_no_terminal'] for t in subset),
                           with_no_terminal_without_later_app_write=sum(
                               t['any_no_terminal_without_later_app_write'] for t in subset),
                           unclassified_calls=sum(len(t['unclassified_calls']) for t in subset)))
    report = dict(kind='descriptive_public_collection_frontier_audit', plan_sha256=digest(args.plan),
                   policy_sha256=digest(args.repo_root / plan['policy']), script_sha256=digest(Path(__file__)),
                   schema_hashes=schema_hashes, trials=trials, strata=strata,
                   total_groups=sum(len(t['groups']) for t in trials),
                   model_calls=0, environment_calls=0, hidden_evaluator_details_read=False,
                   limitations=['Terminal observations are not a proof of complete enumeration.',
                                'Task relevance, cross-app mutation, external changes and stable order are unverified.',
                                'Already observed development cases; not a diagnostic accuracy or causal estimate.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(tasks=len(trials), groups=report['total_groups'], strata=strata), ensure_ascii=False))


if __name__ == '__main__':
    main()

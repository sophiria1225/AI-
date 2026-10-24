"""Finite differential check on a handwritten in-memory operation language.

No AppWorld data, generated Python, model, network or task evaluator is used.
These sequences are construction checks, not independent research tasks.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import time

from deferred_read_obligations import Assumptions, DeferredReadModel

ROOT=Path(__file__).resolve().parents[1]
OBJECTS={'a':{'title':'alpha','rating':1}, 'b':{'title':'beta','rating':2}}
TRUSTED=Assumptions(True,True,True)
ACTIONS=('bind_a','bind_b','read_title','read_rating','alias','drop','effect','escape_alias')
DEPTH=4
LIMIT=DEPTH+1


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def replay(sequence, defer):
    model=DeferredReadModel(OBJECTS,LIMIT,defer=defer)
    model.bind('x','a',{'title':'alpha'},TRUSTED)
    observations=[]
    for action in sequence:
        try:
            if action in ('bind_a','bind_b'):
                key=action[-1];model.bind('x',key,{'title':'alpha' if key=='a' else 'beta'},TRUSTED)
            elif action=='read_title':observations.append(model.field('x','title'))
            elif action=='read_rating':observations.append(model.field('x','rating'))
            elif action=='alias':model.alias('y','x')
            elif action=='drop':model.drop('x')
            elif action=='effect':model.effect({'a':{'title':'alpha','rating':9}})
            elif action=='escape_alias':observations.append(model.materialize('y'))
            else:raise ValueError('outside_fixed_operation_language')
        except KeyError as error:
            observations.append({'key_error':str(error)})
            break
        model._ready()
    # Retain every name; these are future-readable snapshots. Taking this
    # observation deliberately forces all remaining objects on both sides.
    before_final=model.snapshot()
    future={name:model.materialize(name) for name in sorted(model.bindings)}
    return dict(observations=observations, future=future, world=model.objects,
        before_final=before_final, final=model.snapshot(),
        cancelled_fetches=sum(e['kind']=='cancel_unused_fetch' for e in model.events))


def probe(output):
    if output.exists():raise FileExistsError('preserve_first_deferred_read_probe')
    start=time.monotonic();rows=[]
    for sequence in itertools.product(ACTIONS,repeat=DEPTH):
        eager,deferred=(replay(sequence,mode) for mode in (False,True))
        signature=lambda r:{k:r[k] for k in ('observations','future','world')}
        matched=signature(eager)==signature(deferred)
        bounded=deferred['final']['spent']<=eager['final']['spent']<=LIMIT
        rows.append(dict(sequence=' '.join(sequence),observations_match=matched,budget_bound_holds=bounded,
            eager_requests=eager['final']['spent'],deferred_requests=deferred['final']['spent'],
            pending_before_final_observation=deferred['before_final']['pending'],
            cancelled_unused_fetches=deferred['cancelled_fetches'],
            eager_observations_sha256=digest(signature(eager)),
            deferred_observations_sha256=digest(signature(deferred))))
    output.mkdir(parents=True,exist_ok=False)
    with (output/'all_synthetic_sequences.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='deferred_read_explicit_operation_model',created_at=datetime.now(timezone.utc).isoformat(),
        synthetic=True,operation_alphabet=list(ACTIONS),sequence_depth=DEPTH,modelled_request_limit=LIMIT,
        planned_sequences=len(ACTIONS)**DEPTH,checked_sequences=len(rows),
        observation_mismatches=sum(not r['observations_match'] for r in rows),
        budget_bound_failures=sum(not r['budget_bound_holds'] for r in rows),
        equal_modelled_request_counts=sum(r['eager_requests']==r['deferred_requests'] for r in rows),
        lower_modelled_request_counts=sum(r['deferred_requests']<r['eager_requests'] for r in rows),
        all_remaining_aliases_materialized_for_final_comparison=True,
        original_python_type_and_implicit_alias_compatibility_tested=False,
        trusted_assumptions_derived_automatically=False,prior_partial_information_acquisition_cost_measured=False,
        local_time_seconds=time.monotonic()-start,
        source_sha256={p:sha(ROOT/p) for p in ('scripts/deferred_read_obligations.py',
                                             'scripts/probe_deferred_read_obligations.py')},
        all_sequences_sha256=sha(output/'all_synthetic_sequences.csv'),
        research_tasks=0,model_generations=0,real_api_requests=0,task_evaluations=0,
        live_P88_records_read=False,new_method_novelty_established=False,
        limitations='Handwritten operations, trusted total and pure reads, exact initial partial fields, '
            'intercepted state changes, explicit names/aliases/deaths/escapes. No arbitrary Python adapter, '
            'transport guarantees, hidden aliases, wall deadlines, source evidence costs, or task-quality comparison.')
    (output/'diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print({k:result[k] for k in ('checked_sequences','observation_mismatches','budget_bound_failures',
        'equal_modelled_request_counts','lower_modelled_request_counts','local_time_seconds')})
    if result['observation_mismatches'] or result['budget_bound_failures']:
        raise ValueError('synthetic_obligation_model_failed_preserve_results')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();probe(args.output.resolve())

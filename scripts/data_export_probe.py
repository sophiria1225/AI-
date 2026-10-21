"""Common public-data inputs for the P20/P21 export diagnostics."""
import hashlib
import json
from pathlib import Path

from context_preservation import function, parse_submission

APIS = frozenset({'spotify__show_song_library', 'spotify__show_album_library',
                  'spotify__show_playlist_library', 'spotify__show_song'})
COMMON = '''Complete only the data-export portion of the user's request from the recorded public
observations below. This is an offline continuation, not a new search. The observations
are already available; do not call environment APIs or terminate an account. Produce the
file content requested by the user, respecting all of its data, uniqueness and format
conditions. No evaluator or correct answer is available. Do not add a task-completion
claim or invent records. Submit exactly one call of the supplied submission function.'''
PROGRAM = '''Submit Python-shaped data transformation code with submit_program.
At execution, the variable observations is exactly the same list of parsed objects
shown in the input. Assign the final file content as a string to the variable result.
The interpreter supports assignment, for loops over finite data, if/else, comprehensions,
indexing/slicing, arithmetic and set operators, comparisons and boolean expressions.
Available functions: list, tuple, set, dict, sorted (reverse is allowed, key/lambda is not),
enumerate, reversed, len, str/int/float (scalar conversion only), bool, range, min, max,
sum, abs, zip. Data methods: list.append/extend/sort/count/index; dict.get/keys/values/items/
update/setdefault; set.add/update/union/intersection/difference; str.join/strip/lower/upper/
replace/split/startswith/endswith. csv_text(rows, headers) returns properly quoted CSV
from a list of row lists and a list of header strings. It only formats the rows you supply.
For example, result = csv_text([['sample', 'value']], ['A', 'B']) produces a two-column file.
Imports, files, network, processes, while, functions/classes, break/continue, lambdas,
attribute introspection, eval/exec and arbitrary Python extensions are unavailable.
Limits: 20,000 source characters, 100,000 interpreted steps, 10,000 items per collection,
1 MiB output. This is a restricted data interpreter, not a general Python environment.'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_case(directory):
    events = json.loads((directory/'events.json').read_text())
    spans = json.loads((directory/'spans.json').read_text())
    public = json.loads((directory/'public_task.json').read_text())
    observations, cut = [], None
    for event in events:
        span = spans[event['span_id']]
        name = span['action']['name']
        if name == 'file_system__create_file':
            cut = event['span_id']
            break
        if name in APIS:
            if not event['api_request_sent'] or event.get('effects_unknown'):
                raise ValueError('uncertain source observation')
            observations.append({'span_id': event['span_id'], 'api': name,
                                 'result': json.loads(span['observation']['observation'])})
    if cut is None or not observations:
        raise ValueError('recorded pre-export observations required')
    case = {'instruction': public['instruction'], 'observations': observations}
    manifest = {'source_run': directory.name, 'cut_before_span': cut,
                'observation_count': len(observations),
                'source_sha256': {name: sha(directory/name) for name in (
                    'events.json', 'spans.json', 'public_task.json')},
                'read_scope': 'Public task and recorded responses before first file creation. '
                              'No submitted CSV, assistant reasoning, evaluation, hidden solution or reserved task.'}
    return case, manifest


def inputs(case, variant):
    if set(case) != {'instruction', 'observations'} or variant not in ('literal_csv', 'data_program'):
        raise ValueError('unexpected input or variant')
    if variant == 'literal_csv':
        suffix = 'Submit the complete file content as the content string in submit_csv.'
        tool = function('submit_csv', 'Submit the complete requested export file.',
                        {'content': {'type': 'string'}}, ['content'])
    else:
        suffix = PROGRAM
        tool = function('submit_program', 'Submit code that constructs the requested export from observations.',
                        {'code': {'type': 'string'}}, ['code'])
    return [{'role': 'system', 'content': COMMON+'\n\n'+suffix},
            {'role': 'user', 'content': json.dumps(case, ensure_ascii=False, separators=(',', ':'))}], [tool]


def submission(message, variant):
    name, key = ('submit_csv', 'content') if variant == 'literal_csv' else ('submit_program', 'code')
    value = parse_submission(message, name)
    if set(value) != {key} or type(value[key]) is not str:
        raise ValueError('submission shape')
    return value


def schedule(plan):
    if (plan['run_id'] not in ('P20_01', 'P21_01') or plan['variants'] != ['literal_csv', 'data_program']
            or plan['seeds'] != [51, 52, 53] or plan['max_calls'] != 6):
        raise ValueError('unexpected fixed export design')
    rows = []
    for index, seed in enumerate(plan['seeds']):
        variants = plan['variants'][index % 2:] + plan['variants'][:index % 2]
        rows.extend({'variant': v, 'seed': seed} for v in variants)
    return rows

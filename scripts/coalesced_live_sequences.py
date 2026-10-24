"""Fixed handwritten integration cases for the coalesced read host.

These programs are not a generated task solution. They deliberately exercise
duplicate references, last-reference release, ordinary reads, and mutation.
"""
from probe_public_read_views_live import PROGRAMS as ORIGINAL_PROGRAMS


POLICIES = ('eager', 'deferred', 'coalesced')
PROGRAMS = [
    ORIGINAL_PROGRAMS[0],
    """first = read_view('spotify', 'show_song', song_id=ids[0])
second = read_view('spotify', 'show_song', song_id=ids[0])
assert first['title'] == second['title'] == library[0]['title']
print(json.dumps({'title': first['title'], 'artists': second['artists']}, sort_keys=True))""",
    """genre = first['genre']
full = dict(second)
assert genre == full['genre'] and dict(first) == full
print(json.dumps(full, sort_keys=True))
del first, second, genre, full""",
    """discarded = read_view('spotify', 'show_song', song_id=ids[1])
held = read_view('spotify', 'show_song', song_id=ids[1])
assert discarded['title'] == held['title'] == library[1]['title']
del discarded
print(json.dumps({'title': held['title'], 'artists': held['artists']}, sort_keys=True))""",
    """assert held['title'] == library[1]['title']
del held
print('last reference released')""",
    """first = read_view('spotify', 'show_song', song_id=ids[2])
second = read_view('spotify', 'show_song', song_id=ids[2])
full = call_api('spotify', 'show_song', song_id=ids[2])
assert dict(first) == dict(second) == full
print(json.dumps(full, sort_keys=True))
del first, second, full""",
    """refreshed = call_api('spotify', 'show_song_library', access_token=token, page_index=0, page_limit=3)
assert refreshed == library
first = read_view('spotify', 'show_song', song_id=ids[1])
second = read_view('spotify', 'show_song', song_id=ids[1])
operation = 'unlike_song' if was_liked else 'like_song'
delta = -1 if was_liked else 1
call_api('spotify', operation, song_id=ids[1], access_token=token)
before = dict(first)
assert dict(second) == before
after = call_api('spotify', 'show_song', song_id=ids[1])
assert after['like_count'] == before['like_count'] + delta
assert before['title'] == after['title'] == library[1]['title']
print(json.dumps({'before': before, 'after': after}, sort_keys=True))
del first, second, before, after, refreshed, library, ids, token""",
]

EXPECTED_API = {
    'eager': [6, 1, 0, 1, 0, 2, 3],
    'deferred': [6, 0, 2, 0, 0, 3, 5],
    'coalesced': [6, 0, 1, 0, 0, 1, 4],
}
EXPECTED_PENDING = {
    'eager': [0, 0, 0, 0, 0, 0, 0],
    'deferred': [0, 2, 0, 1, 0, 0, 0],
    'coalesced': [0, 1, 0, 1, 0, 0, 0],
}
EXPECTED_EXACT_REUSES = {'eager': 5, 'deferred': 0, 'coalesced': 0}
EXPECTED_COALESCED_REUSES = {'eager': 0, 'deferred': 0, 'coalesced': 4}
EXPECTED_MATERIALIZATION_CACHE_REUSES = {'eager': 0, 'deferred': 0, 'coalesced': 1}


def validate_plan(plan):
    fixed = dict(phase='P105_coalesced_read_live', task_id='6104387_1', seed=42,
        policies=list(POLICIES), fresh_world_per_policy=True,
        experiment_prefix='P105_COALESCED_READ_LIVE_V01',
        private_output='records/context_pilot/P105_coalesced_read_live_v01',
        stop_marker='.runtime/P105.stop', max_task_initializations=3,
        max_python_containers=3, handwritten_programs_per_policy=7,
        max_api_requests_per_policy=20, max_total_api_requests=60,
        active_deadline_seconds=300, program_timeout_seconds=30, bridge_timeout_seconds=30,
        expected_api_requests_per_program=EXPECTED_API,
        expected_pending_after_program=EXPECTED_PENDING,
        expected_exact_reuses=EXPECTED_EXACT_REUSES,
        expected_coalesced_reuses=EXPECTED_COALESCED_REUSES,
        expected_materialization_cache_reuses=EXPECTED_MATERIALIZATION_CACHE_REUSES,
        model_calls=0, evaluator_calls=0, automatic_retries=0,
        task_quality_measured=False, novel_method_claim=False)
    import hashlib
    fixed['program_sha256'] = [hashlib.sha256(s.encode()).hexdigest() for s in PROGRAMS]
    for key,value in fixed.items():
        if plan.get(key) != value:
            raise ValueError('fixed_P105_plan_changed:'+key)
    return plan

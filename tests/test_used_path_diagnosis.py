"""Synthetic data only; saved-source analysis never executes source text."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_used_paths import analyze_cell, bound_inventory, fixed_parameters
from replay_read_view_controls import sha
from used_path_diagnosis import acquisition_history, message_components, program_syntax

NAMES = {'spotify__show_artist', 'spotify__show_song_library', 'spotify__show_song',
         'spotify__show_album', 'spotify__like_song', 'api_docs__show_api_doc'}


def records(calls):
    events = []; spans = {}
    for i, (api, args, value, status) in enumerate(calls, 1):
        sid = 's' + str(i)
        events.append(dict(span_id=sid, call='call_001', api_request_sent=True, stage='python_api',
            api_execution=dict(bridge_request_sent=True, automatic_retries=0, status=status)))
        spans[sid] = dict(action=dict(name=api, arguments=json.dumps(args)),
                         observation={'observation': value})
    return events, spans, [{'id': 'call_001'}]


def inspect_calls(calls):
    return acquisition_history(*records(calls), NAMES)


LIBRARY = ('spotify__show_song_library', {},
    [{'song_id': 2, 'artists': [{'id': 7, 'name': 'synthetic artist'}]}], 'returned')
ARTIST = ('spotify__show_artist', {'artist_id': 7},
    {'artist_id': 7, 'name': 'synthetic artist', 'genre': 'synthetic genre'}, 'returned')
SONG = ('spotify__show_song', {'song_id': 2}, {'song_id': 2, 'title': 'synthetic song'}, 'returned')


class UsedPathTests(unittest.TestCase):
    def test_direct_field_and_stored_root_are_separate_syntax_sites(self):
        source = "print(call_api('spotify','show_artist',artist_id=7)['name'])\na=call_api('spotify','show_artist',artist_id=8)\nprint(a['name'])"
        r = program_syntax(source, NAMES)
        self.assertEqual(r['call_api_syntax_sites'], 2)
        self.assertEqual(r['sites'][0]['root_use'], 'literal_subscript')
        self.assertEqual(r['sites'][1]['public_literal_field_counts'], {'name': 1})
        self.assertFalse(r['sites'][1]['safe_substitution_established'])

    def test_later_same_spelling_store_limits_window(self):
        r = program_syntax("a=call_api('spotify','show_artist',artist_id=7)\nprint(a['name'])\na={}\nprint(a['genre'])", NAMES)
        self.assertEqual(r['sites'][0]['public_literal_field_counts'], {'name': 1})
        self.assertEqual(r['sites'][0]['later_same_spelling_store_position'], (3, 0))

    def test_same_spelling_in_function_is_marked_without_alias_claim(self):
        r = program_syntax("a=call_api('spotify','show_artist',artist_id=7)\ndef f(a):\n return a['name']", NAMES)
        site = r['sites'][0]
        self.assertEqual(site['nested_scope_same_spelling_loads'], 1)
        self.assertFalse(site['alias_or_liveness_proved'])

    def test_loop_site_is_not_expanded_to_invent_API_requests(self):
        r = program_syntax("for i in range(10):\n a=call_api('spotify','show_artist',artist_id=i)\n print(a.get('name'))", NAMES)
        self.assertEqual(r['call_api_syntax_sites'], 1)
        self.assertEqual(r['sites'][0]['binding_scope_kinds'], ['For'])
        self.assertEqual(r['sites'][0]['public_literal_field_counts'], {'name': 1})

    def test_escaping_and_mutating_roots_are_not_field_only(self):
        r = program_syntax("a=call_api('spotify','show_artist',artist_id=7)\nitems.append(a)\na['name']='changed'", NAMES)
        self.assertEqual(r['sites'][0]['lexical_load_counts'], {'whole_root_syntax': 1, 'member_mutation': 1})

    def test_unpublished_fields_and_API_names_are_not_serialized(self):
        r = program_syntax("x=call_api('private','secret',password='do-not-publish')\nprint(x['confidential-secret'])", NAMES)
        encoded = json.dumps(r)
        self.assertNotIn('do-not-publish', encoded)
        self.assertNotIn('confidential-secret', encoded)
        self.assertNotIn('private__secret', encoded)
        self.assertIsNone(r['sites'][0]['api'])

    def test_dynamic_code_is_described_but_never_executed(self):
        with patch('builtins.exec', side_effect=AssertionError('must not execute')):
            r = program_syntax("exec('raise AssertionError()')\na=call_api('spotify','show_artist',artist_id=7)", NAMES)
        self.assertIn('dynamic_execution_or_namespace_access', r['current_program_hazards'])

    def test_source_and_message_bounds_reject_unsupported_inputs(self):
        with self.assertRaisesRegex(ValueError, 'source_bound'):
            program_syntax('x' * 20001, NAMES)
        with self.assertRaisesRegex(ValueError, 'text_content_required'):
            message_components([{'role': 'tool', 'content': [{'text': 'x'}]}])

    def test_character_fields_are_disjoint_and_are_not_tokens(self):
        r = message_components([dict(role='system', content='日本'),
            dict(role='assistant', content='a', reasoning_content='bc', tool_calls=[
                {'function': {'name': 'run_python', 'arguments': '{}'}}]),
            dict(role='tool', content='xyz')])
        self.assertEqual(r['total_text_field_characters'], 20)
        self.assertEqual(r['assistant_reasoning_characters'], 2)
        self.assertTrue(r['character_counts_are_not_token_counts'])
        self.assertNotIn('bc', json.dumps(r))

    def test_only_preceding_artist_observations_are_counted(self):
        r = inspect_calls([ARTIST, LIBRARY, ARTIST])['requests']
        self.assertEqual(r[0]['prior_artist_name_observations'], 0)
        self.assertEqual(r[2]['prior_artist_name_observations'], 2)
        self.assertTrue(r[2]['prior_artist_name_matches_current'])
        self.assertFalse(r[2]['existing_contract_authorizes_artist_name_substitution'])

    def test_name_agreement_does_not_claim_full_response_or_safe_reuse(self):
        r = inspect_calls([LIBRARY, ARTIST])
        self.assertTrue(r['requests'][1]['prior_artist_name_matches_current'])
        self.assertFalse(r['requests'][1]['online_API_omission_established'])
        self.assertTrue(r['name_only_is_not_full_artist_response'])

    def test_names_changed_between_observations_remain_visible_as_conflicts(self):
        changed = deepcopy(LIBRARY)
        changed[2][0]['artists'][0]['name'] = 'different'
        r = inspect_calls([LIBRARY, changed, ARTIST])['requests'][-1]
        self.assertTrue(r['prior_artist_names_conflict'])
        self.assertFalse(r['prior_artist_name_matches_current'])

    def test_mutation_separates_historical_equality_from_conservative_epoch(self):
        mutate = ('spotify__like_song', {'song_id': 2}, {'message': 'ok'}, 'returned')
        r = inspect_calls([SONG, SONG, mutate, SONG])['requests']
        self.assertTrue(r[1]['prior_identical_return_same_conservative_epoch'])
        self.assertTrue(r[3]['prior_complete_return_equals_current'])
        self.assertFalse(r[3]['prior_identical_return_same_conservative_epoch'])

    def test_failed_and_unknown_responses_do_not_create_prior_values(self):
        failed = (ARTIST[0], ARTIST[1], {'artist_id': 7, 'name': 'ignored'}, 'raised')
        unknown = (ARTIST[0], ARTIST[1], {'artist_id': 7, 'name': 'ignored'}, 'unknown')
        r = inspect_calls([failed, unknown, ARTIST])
        self.assertEqual(r['requests'][-1]['prior_artist_name_observations'], 0)
        self.assertFalse(r['requests'][-1]['prior_identical_returned_request'])
        self.assertEqual(r['counts']['sent_API_requests'], 3)

    def test_all_arguments_and_types_participate_in_identical_requests(self):
        other = (SONG[0], {'song_id': '2'}, SONG[2], 'returned')
        r = inspect_calls([SONG, other])['requests']
        self.assertFalse(r[1]['prior_identical_returned_request'])

    def test_unapproved_api_and_event_order_are_rejected(self):
        events, spans, usage = records([SONG])
        events[0]['call'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'chronological_complete_events_required'):
            acquisition_history(events, spans, usage, NAMES)
        with self.assertRaisesRegex(ValueError, 'known_public_API_required'):
            inspect_calls([('private__secret', {}, {}, 'returned')])

    def fixture(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        source = "x=call_api('spotify','show_song',song_id=2)\nprint(x['title'])"
        events, spans, usage = records([SONG])
        events.append(dict(span_id='outer', call='call_001', stage='model_tool', api_request_sent=False))
        spans['outer'] = dict(action=dict(name='run_python', arguments=json.dumps({'code': source})))
        u = usage[0]; u.update(status='ok', input_tokens=10, output_tokens=5, cached_input_tokens=0)
        response = dict(status='ok', input_tokens=10, output_tokens=5, cached_input_tokens=0,
            message=dict(role='assistant', content='', reasoning_content='synthetic private reasoning',
                         tool_calls=[{'function': spans['outer']['action']}]))
        values = {'usage.json': usage, 'events.json': events, 'spans.json': spans, 'summary.json': {},
            'call_001/request.json': {'messages': [dict(role='system', content='synthetic')]},
            'call_001/response.json': response, 'programs/call_001_01/input_private.json': {'code': source}}
        for name, value in values.items():
            path = folder / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
        hashes = {n: sha(folder / n) for n in values}
        original = dict(run_id='fixture', model_calls=1, api_requests=1, usage_sha256=hashes['usage.json'],
            read_view_policy='eager_cached', success=False, stop_reason='synthetic_stop', known_total_tokens=15,
            request_checks=[dict(call_id='call_001', status='ok', input_tokens=10, output_tokens=5,
                cached_input_tokens=0, API_requests=1, Python_execution_errors=0,
                request_sha256=hashes['call_001/request.json'], response_sha256=hashes['call_001/response.json'])])
        replay = dict(private_record_sha256={'fixture': hashes})
        return folder, original, replay

    def test_complete_synthetic_cell_retains_costs_failure_and_private_text(self):
        folder, original, replay = self.fixture()
        inventory = bound_inventory(original, replay, folder, fixed_parameters())
        with patch('subprocess.Popen', side_effect=AssertionError('must not launch any process')):
            r = analyze_cell(folder, original, inventory, NAMES, fixed_parameters())
        self.assertEqual(r['syntax_programs'], 1)
        self.assertFalse(r['original_success'])
        self.assertEqual(r['original_known_total_tokens'], 15)
        self.assertNotIn('synthetic private reasoning', json.dumps(r))
        self.assertEqual(r['calls'][0]['input']['assistant_reasoning_characters'], 0)

    def test_input_hash_change_rejected_before_analysis(self):
        folder, original, replay = self.fixture()
        (folder / 'programs/call_001_01/input_private.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'saved_private_input_changed'):
            bound_inventory(original, replay, folder, fixed_parameters())

    def test_generated_source_cannot_be_silently_rewritten(self):
        folder, original, replay = self.fixture()
        name = 'programs/call_001_01/input_private.json'
        (folder / name).write_text(json.dumps({'code': 'pass'}))
        replay['private_record_sha256']['fixture'][name] = sha(folder / name)
        inventory = bound_inventory(original, replay, folder, fixed_parameters())
        with self.assertRaisesRegex(ValueError, 'submitted_source_and_executed_input_differ'):
            analyze_cell(folder, original, inventory, NAMES, fixed_parameters())


if __name__ == '__main__':
    unittest.main()

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from observation_growth_profile import ObservationExposure, api_repetitions, summarize_call_characters


def history(steps):
    events = []; spans = {}
    for i, step in enumerate(steps, 1):
        name, args, result = step[:3]
        status = step[3] if len(step) > 3 else 'returned'
        effects_unknown = step[4] if len(step) > 4 else status == 'unknown'
        sid = 's'+str(i)
        events.append(dict(span_id=sid, call='call_'+str(i), stage='python_api',
            api_request_sent=True, effects_unknown=effects_unknown,
            api_execution=dict(bridge_request_sent=True, automatic_retries=0, status=status)))
        spans[sid] = dict(id=sid, action=dict(name=name, arguments=json.dumps(args)),
                         observation=dict(observation=result))
    return events, spans


class ObservationGrowthTests(unittest.TestCase):
    def test_unicode_characters_are_disjoint_and_not_token_estimates(self):
        request = dict(messages=[dict(role='system', content='規則'),
            dict(role='user', content='課題'),
            dict(role='assistant', content='答', reasoning_content='思考',
                 tool_calls=[dict(function=dict(name='run_python', arguments='{}'))]),
            dict(role='tool', content='結果', tool_call_id='a')])
        old = copy.deepcopy(request); profile = ObservationExposure()
        row = profile.add(request, 1)
        self.assertEqual(row['components']['total_text_field_characters'], 21)
        self.assertEqual(row['tool_exposure']['first_seen_characters'], 2)
        self.assertFalse(row['token_attribution'])
        self.assertEqual(request, old)

    def test_replay_retains_distinct_ids_and_duplicate_occurrences(self):
        a = dict(role='tool', tool_call_id='a', content='abc')
        b = dict(role='tool', tool_call_id='b', content='abc')
        p = ObservationExposure()
        self.assertEqual(p.add(dict(messages=[a,a]), 1)['tool_exposure']['first_seen_characters'], 6)
        row = p.add(dict(messages=[a,a,b]), 2)
        self.assertEqual(row['tool_exposure']['first_seen_characters'], 3)
        self.assertEqual(row['tool_exposure']['replayed_characters'], 6)
        s = p.summary()
        self.assertEqual((s['unique_message_occurrences'],s['first_seen_characters'],s['replayed_characters']), (3,9,6))
        self.assertEqual(s['total_characters'], 15)

    def test_changed_content_and_missing_input_do_not_become_zero_known_inputs(self):
        p = ObservationExposure()
        p.add(dict(messages=[dict(role='tool', tool_call_id='a', content='old')]),1)
        self.assertEqual(p.add(None,2)['status'], 'unavailable')
        row = p.add(dict(messages=[dict(role='tool', tool_call_id='a', content='new')]),3)
        self.assertEqual(row['tool_exposure']['first_seen_characters'], 3)
        with self.assertRaisesRegex(ValueError,'chronological'):
            p.add(dict(messages=[]),3)

    def test_equal_full_arguments_include_auth_and_ignore_only_object_key_order(self):
        steps = [('spotify__show_song', {'song_id':1,'access_token':'a'}, {'title':'x'}),
                 ('spotify__show_song', {'access_token':'a','song_id':1}, {'title':'x'}),
                 ('spotify__show_song', {'song_id':1,'access_token':'b'}, {'title':'x'})]
        events, spans = history(steps); old = copy.deepcopy((events, spans))
        r = api_repetitions(events,spans)
        self.assertEqual(r['exact_request_repeats'],1)
        self.assertEqual(r['same_conservative_read_epoch_repeats'],1)
        self.assertEqual((events,spans),old)
        published = json.dumps(r)
        self.assertNotIn('access_token',published)
        self.assertNotIn('title',published)

    def test_same_request_with_changed_reply_remains_visible_not_a_safe_cache_claim(self):
        r = api_repetitions(*history([('spotify__show_song',{'id':1},1),
                                      ('spotify__show_song',{'id':1},2)]))
        self.assertTrue(r['rows'][1]['exact_request_seen_before'])
        self.assertFalse(r['rows'][1]['same_returned_observation_as_previous'])
        self.assertTrue(r['rows'][1]['same_conservative_read_epoch_repeat'])
        self.assertFalse(r['rows'][1]['cache_validity_or_savings_established'])

    def test_unreviewed_operation_and_write_break_conservative_epoch(self):
        for barrier in ('spotify__show_artist','spotify__delete_playlist'):
            r = api_repetitions(*history([('spotify__show_song',{'id':1},1),
                (barrier,{'id':7},0),('spotify__show_song',{'id':1},1)]))
            self.assertEqual(r['exact_request_repeats'],1)
            self.assertEqual(r['same_conservative_read_epoch_repeats'],0)

    def test_failed_and_unknown_requests_are_kept_and_not_used_as_cached_reads(self):
        for status, effects in (('raised',False),('unknown',True),('returned',True)):
            r = api_repetitions(*history([('spotify__show_song',{'id':1},1,status,effects),
                ('spotify__show_song',{'id':1},1)]))
            self.assertEqual(r['requests'],2)
            self.assertEqual(r['same_conservative_read_epoch_repeats'],0)
            self.assertEqual(r['by_api']['spotify__show_song'][status], 2 if status == 'returned' else 1)

    def test_unknown_outer_effect_breaks_epoch_even_without_API(self):
        events, spans = history([('spotify__show_song',{'id':1},1),('spotify__show_song',{'id':1},1)])
        events.insert(1,dict(span_id='outer',call='call_1',stage='model_tool',api_request_sent=False,effects_unknown=True))
        spans['outer'] = dict(id='outer',observation={})
        self.assertEqual(api_repetitions(events,spans)['same_conservative_read_epoch_repeats'],0)

    def test_receipt_unknown_or_duplicate_inventory_rejected(self):
        events, spans = history([('spotify__show_song',{},1)])
        events[0]['api_execution']['automatic_retries'] = 1
        with self.assertRaisesRegex(ValueError,'typed_actual'):
            api_repetitions(events,spans)
        events, spans = history([('spotify__show_song',{},1)])
        with self.assertRaisesRegex(ValueError,'bounded_events'):
            api_repetitions(events+events,spans)

    def test_API_free_known_call_and_unknown_call_are_distinct(self):
        p=ObservationExposure()
        calls=[dict(input=p.add(dict(messages=[dict(role='user',content='a')]),1),usage_status='ok',API_requests=0),
               dict(input=p.add(None,2),usage_status='unknown',API_requests=0)]
        s=summarize_call_characters(calls)
        self.assertEqual((s['checked_requests'],s['unavailable_requests'],s['known_response_calls_with_no_API']),(1,1,1))
        self.assertTrue(s['API_free_calls_are_not_classified_as_waste'])


if __name__ == '__main__': unittest.main()

"""Handwritten public-return/write-payload fixtures; no task traces or APIs."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import sys
import hashlib
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_api_envelope import PROTOCOL
from public_output_grounding import PublicExportMonitor, csv_compare
import public_output_grounding as monitor_module

TASK = {'ground_truth_loaded': False, 'supervisor': {'email': 'synthetic@example.test'},
    'instruction': 'Export a unique list of all the songs in my song and album library and all playlists '
        'in my Spotify account into "~/backup/export.csv" file in my file system. The file should have '
        'headers, "Title" and "Artists" and artists should be separated by "|". '
        'Terminate my account after this backup is complete.'}
SONGS = [dict(song_id=1, title='First, with comma', artists=[dict(id=10, name='A'), dict(id=11, name='B')]),
         dict(song_id=2, title='Second\nwith line', artists=[dict(id=12, name='日本語')])]


class Fixture:
    def __init__(self, task=None):
        self.monitor = PublicExportMonitor(deepcopy(task or TASK), execution_scope='synthetic_execution')
        self.number = 0
        self.rows = []

    def send(self, name, args, value=None, *, status='returned', sent=True, unknown=False):
        self.number += 1
        sid = f's{self.number}'
        event = dict(span_id=sid, call=f'call_{self.number:03d}', stage='python_api',
            api_request_sent=sent, effects_unknown=unknown, new_tools=[])
        if sent:
            event['api_execution'] = dict(protocol=PROTOCOL, nonce='nonce-' + sid,
                status=status, bridge_request_sent=True, automatic_retries=0)
        span = dict(id=sid, action=dict(name=name, arguments=json.dumps(args)),
                    observation={'observation': json.dumps(value)})
        self.rows.append((deepcopy(event), deepcopy(span)))
        self.monitor.observe(event, span)
        return event, span

    def login(self, app, token, username=None, **kwargs):
        self.send(app + '__login', {'username': username or TASK['supervisor']['email'], 'password': 'synthetic'},
                  {'access_token': token, 'token_type': 'Bearer'}, **kwargs)

    def ready(self, *, joined=False, complete=True):
        self.login('spotify', 'spotify-one'); self.login('file_system', 'file-one')
        self.send('spotify__show_song_library', {'access_token': 'spotify-one', 'page_limit': 2}, [SONGS[0]])
        self.send('spotify__show_album_library', {'access_token': 'spotify-one', 'page_limit': 2},
            [{'album_id': 20, 'song_ids': [2], 'artists': [dict(id=12, name='日本語')]}])
        if complete:
            self.send('spotify__show_playlist_library', {'access_token': 'spotify-one', 'page_limit': 2},
                      [{'playlist_id': 30, 'song_ids': [1, 2]}])
        if joined:
            self.send('spotify__show_album', {'album_id': 20}, {'album_id': 20,
                'songs': [{'id': 2, 'title': SONGS[1]['title'], 'artist_ids': [12]}],
                'artists': [dict(id=12, name='日本語')]})
        else:
            self.send('spotify__show_song', {'song_id': 2}, SONGS[1])
        return self

    def arguments(self, content='Title,Artists\nInvented,Wrong\n'):
        return dict(access_token='file-one', file_path='~/backup/export.csv', content=content, overwrite=False)

    def proposal(self, args=None, **kwargs):
        return self.monitor.propose('file_system__create_file', args or self.arguments(), **kwargs)


class PublicOutputGroundingTests(unittest.TestCase):
    def test_actual_write_payload_repair_uses_only_prior_values_and_changes_content_only(self):
        f = Fixture().ready(); args = f.arguments(); before = deepcopy(args)
        decision = f.proposal(args, mode='repair')
        self.assertEqual(decision['status'], 'contradicted')
        replacement = decision['replacement_args']
        self.assertEqual({k: v for k, v in replacement.items() if k != 'content'},
                         {k: v for k, v in args.items() if k != 'content'})
        self.assertEqual(args, before)
        self.assertEqual(list(csv.reader(io.StringIO(replacement['content']))),
                         [['Title', 'Artists'], [SONGS[0]['title'], 'A|B'], [SONGS[1]['title'], '日本語']])
        self.assertEqual(f.proposal(replacement)['status'], 'supported')
        self.assertIsNone(f.proposal(replacement, mode='repair')['replacement_args'])
        self.assertIsNone(f.monitor.summary()['backup'])

    def test_check_mode_and_unrelated_payloads_do_not_modify_arguments(self):
        f = Fixture().ready(); args = f.arguments()
        self.assertIsNone(f.proposal(args)['replacement_args'])
        for name, modified in [('file_system__create_file', {**args, 'file_path': '~/unrelated.txt'}),
                               ('spotify__delete_account', args), ('other__write', args)]:
            self.assertEqual(f.monitor.propose(name, modified, mode='repair')['status'], 'outside_scope')

    def test_short_terminal_page_and_repeated_login_preserve_same_principal(self):
        f = Fixture().ready()
        f.login('spotify', 'spotify-two')
        f.send('spotify__show_song_library', {'access_token': 'spotify-two', 'page_limit': 2}, [SONGS[0]])
        self.assertEqual(f.proposal(mode='repair')['status'], 'contradicted')
        self.assertTrue(all(f.monitor.summary()['evidence']['source_complete'].values()))
        self.assertFalse(f.monitor.taints)

    def test_different_limits_are_separate_series_with_cross_series_consistency(self):
        f = Fixture().ready()
        f.send('spotify__show_song_library', {'access_token': 'spotify-one', 'page_limit': 1}, [SONGS[0]])
        self.assertEqual(f.proposal()['status'], 'contradicted')
        f.send('spotify__show_song_library', {'access_token': 'spotify-one', 'page_limit': 1, 'page_index': 1}, [])
        self.assertEqual(f.proposal()['status'], 'contradicted')
        f.send('spotify__show_song_library', {'access_token': 'spotify-one', 'page_limit': 3}, [SONGS[1]])
        self.assertEqual(f.proposal()['status'], 'unknown')
        self.assertIn('changed_complete_library_inventory', f.monitor.taints)

    def test_gap_full_page_and_filtered_inventory_are_not_complete_proofs(self):
        for case in ('missing', 'full_only', 'gap', 'filtered'):
            with self.subTest(case=case):
                f = Fixture().ready(complete=False)
                if case != 'missing':
                    args = dict(access_token='spotify-one', page_limit=1 if case == 'full_only' else 2)
                    if case == 'gap': args['page_index'] = 1
                    if case == 'filtered': args['is_public'] = True
                    f.send('spotify__show_playlist_library', args, [{'playlist_id': 30, 'song_ids': [2]}])
                decision = f.proposal(mode='repair')
                self.assertEqual(decision['status'], 'unknown')
                self.assertIsNone(decision['replacement_args'])

    def test_failed_read_and_unsent_payload_never_become_witnesses_or_erase_valid_reads(self):
        f = Fixture().ready()
        f.send('spotify__show_playlist', {'playlist_id': 30}, {'songs': []}, status='raised')
        f.send('spotify__show_song_library', {}, [], status='raised')
        f.send('spotify__show_song', {'song_id': 1}, {'song_id': 1, 'title': 'invented'}, sent=False)
        self.assertFalse(f.monitor.taints)
        self.assertEqual(f.proposal()['status'], 'contradicted')
        self.assertEqual(f.monitor.stats['failed_non_source_reads_ignored'], 2)

    def test_unknown_effect_or_unhandled_mutation_blocks_repair(self):
        for name, kwargs in [('spotify__show_song', {'status': 'unknown', 'unknown': True}),
                             ('spotify__remove_song_from_library', {})]:
            f = Fixture().ready(); f.send(name, {'song_id': 1}, {}, **kwargs)
            decision = f.proposal(mode='repair')
            self.assertEqual(decision['status'], 'unknown')
            self.assertIsNone(decision['replacement_args'])

    def test_other_principal_and_cross_app_token_cannot_authorize_sources_or_write(self):
        f = Fixture().ready()
        f.login('spotify', 'other-token', username='other@example.test')
        f.send('spotify__show_playlist_library', {'access_token': 'other-token'}, [])
        self.assertEqual(f.proposal()['status'], 'unknown')
        g = Fixture().ready()
        self.assertEqual(g.proposal({**g.arguments(), 'access_token': 'spotify-one'})['status'], 'unknown')
        h = Fixture().ready(); h.login('file_system', 'failed', status='raised')
        self.assertEqual(h.proposal({**h.arguments(), 'access_token': 'failed'})['status'], 'unknown')

    def test_public_artist_join_preserves_song_specific_membership(self):
        f = Fixture().ready(joined=True)
        self.assertEqual(f.proposal(mode='repair')['status'], 'contradicted')
        evidence = f.monitor.summary()['evidence']
        self.assertEqual((evidence['direct_metadata_ids'], evidence['joined_metadata_ids']), (1, 1))
        g = Fixture().ready(complete=False)
        g.send('spotify__show_playlist_library', {'access_token': 'spotify-one', 'page_limit': 2},
               [{'playlist_id': 30, 'song_ids': [1, 2, 3]}])
        g.send('spotify__show_album', {'album_id': 20}, {'album_id': 20,
            'artists': [{'id': 12, 'name': '日本語'}],
            'songs': [{'id': 3, 'title': 'Third', 'artist_ids': [99]}]})
        self.assertEqual(g.proposal()['status'], 'unknown')
        g.send('spotify__show_artist', {'artist_id': 99}, {'artist_id': 99, 'name': 'Other'})
        self.assertEqual(g.proposal()['status'], 'contradicted')

    def test_requested_identity_changed_values_and_ambiguous_pair_remain_unknown(self):
        for case in ('identity', 'value', 'ambiguous'):
            f = Fixture().ready(); value = deepcopy(SONGS[1])
            if case == 'identity': value['song_id'] = 3
            elif case == 'value': value['title'] = 'changed'
            else:
                value.update(song_id=3, title=SONGS[0]['title'], artists=SONGS[0]['artists'])
                f.send('spotify__show_song_library', {'access_token': 'spotify-one', 'page_limit': 3}, [SONGS[0], value])
            f.send('spotify__show_song', {'song_id': 2 if case != 'ambiguous' else 3}, value)
            self.assertEqual(f.proposal(mode='repair')['status'], 'unknown')

    def test_artist_and_row_order_are_not_unstated_quality_conditions(self):
        pairs = [('First', 'A|B'), ('Second', 'C')]
        self.assertEqual(csv_compare('Title,Artists\r\nSecond,C\r\nFirst,B|A\r\n', pairs)['status'], 'supported')
        self.assertEqual(csv_compare('Title,Artists\nFirst,A|A\nSecond,C\n', pairs)['status'], 'contradicted')

    def test_quoting_malformed_rows_duplicate_missing_wrong_header_are_detected(self):
        pairs = [('One', 'A'), ('Two', 'B')]
        for content in ('Title,Artists\nOne,A\nOne,A\n', 'Title,Artists\nOne,A,extra\nTwo,B\n',
                        'Title,Artist\nOne,A\nTwo,B\n', 'Title,Artists\nOne,A\n',
                        'Title,Artists\n"unterminated,A\nTwo,B\n'):
            self.assertEqual(csv_compare(content, pairs)['status'], 'contradicted')

    def test_proposal_neither_registers_requested_values_nor_consumes_future_response(self):
        f = Fixture().ready(complete=False); before = deepcopy(f.monitor.summary())
        for _ in range(3): self.assertIsNone(f.proposal(mode='repair')['replacement_args'])
        self.assertEqual(before, f.monitor.summary())
        g = Fixture().ready(); self.assertNotEqual(f.proposal()['status'], g.proposal()['status'])

    def test_write_success_does_not_prove_backup_content_and_later_delete_is_not_authorized(self):
        f = Fixture().ready(); args = f.arguments()
        f.send('file_system__create_file', args, {'message': 'File created.', 'file_path': '/home/fixture/backup/export.csv'})
        self.assertFalse(f.monitor.summary()['backup']['confirmed'])
        f.send('spotify__delete_account', {'access_token': 'spotify-one'},
               {'message': 'User account with all data belonging to it have been deleted.'})
        self.assertFalse(f.monitor.summary()['deletion']['supported_backup_preceded'])
        self.assertEqual(f.proposal(mode='repair')['status'], 'unknown')

    def test_correct_proposal_must_receive_actual_success_before_backup_is_confirmed(self):
        f = Fixture().ready(); args = f.proposal(mode='repair')['replacement_args']
        self.assertIsNone(f.monitor.summary()['backup'])
        f.send('file_system__create_file', args, {'message': 'File created.', 'file_path': '/home/fixture/backup/export.csv'})
        self.assertTrue(f.monitor.summary()['backup']['confirmed'])
        self.assertNotIn('path', f.monitor.summary()['backup'])

    def test_duplicate_nonce_event_and_wrong_template_fail_closed(self):
        f = Fixture().ready()
        event, span = deepcopy(f.rows[-1])
        with self.assertRaisesRegex(ValueError, 'unique_ordered_source_event_required'):
            f.monitor.observe(event, span)
        event['span_id'] = span['id'] = 'new-event-same-nonce'
        with self.assertRaisesRegex(ValueError, 'unique_typed_dispatch_nonce_required'):
            f.monitor.observe(event, span)
        with self.assertRaises(ValueError): PublicExportMonitor({**TASK, 'ground_truth_loaded': True}, execution_scope='test')
        with self.assertRaises(ValueError): PublicExportMonitor({**TASK, 'instruction': 'other task'}, execution_scope='test')

    def test_public_implementation_verifier_rejects_changed_bytes_without_importing_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'apps/synthetic.py'
            source.parent.mkdir(); source.write_text('raise AssertionError("must never execute")\n')
            expected = {'apps/synthetic.py': hashlib.sha256(source.read_bytes()).hexdigest()}
            with patch.object(monitor_module, 'PUBLIC_SOURCE_SHA256', expected):
                self.assertEqual(monitor_module.verify_public_export_sources(root), monitor_module.PUBLIC_CONTRACT_ID)
                source.write_text('changed bytes')
                with self.assertRaisesRegex(ValueError, 'public_export_implementation_changed'):
                    monitor_module.verify_public_export_sources(root)


if __name__ == '__main__':
    unittest.main()

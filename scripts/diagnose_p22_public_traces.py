"""Post-hoc descriptive checks of six completed public traces, not a task oracle.

Reads no task database, hidden test, solution, or model reasoning. Export counts
and source digests only. A set reconstructed from observations is not the full
environment population. It must never be reused as a generation target list.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(root, number):
    path = root / 'records/context_pilot' / f'P22_{number:02d}_ROLES'
    spans = json.loads((path / 'spans.json').read_text())
    result = []
    for sid, span in spans.items():
        action = span.get('action') or {}
        try:
            args = json.loads(action.get('arguments', '{}'))
        except (ValueError, TypeError):
            args = {}
        raw = span.get('observation', {})
        try:
            data = json.loads(raw.get('observation', ''))
        except (ValueError, TypeError):
            data = None
        result.append(dict(id=sid, name=action.get('name'), args=args,
                           data=data, dispatched='observation' in raw))
    return result, {name: sha(path / name) for name in ('public_task.json', 'spans.json')}


def named(rows_, name):
    return [r for r in rows_ if r['name'] == name and r['dispatched']]


def flatten(rows_, name):
    return [item for r in named(rows_, name) for item in r['data']]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    groups, hashes = {}, {}
    for n in range(1, 7):
        groups[n], hashes[str(n)] = rows(args.storage_root, n)
    findings = {}
    rr = groups[1]
    playlists = flatten(rr, 'spotify__show_liked_playlists')
    ids = {i for p in playlists for i in p['song_ids']}
    review_queries = named(rr, 'spotify__show_song_reviews')
    new = named(rr, 'spotify__review_song')
    updated = named(rr, 'spotify__update_song_review')
    review_to_song = {}
    for r in review_queries:
        for review in r['data']:
            # Public schema uses song_review_id; fail visibly if that changes.
            review_to_song[review['song_review_id']] = r['args']['song_id']
    acted = {r['args']['song_id'] for r in new}
    acted |= {review_to_song[r['args']['review_id']] for r in updated}
    findings['1'] = dict(
        liked_playlists_observed=len(playlists), selected_unique_songs=len(ids),
        reviewed_song_ids=len({r['args']['song_id'] for r in review_queries}),
        new_reviews_sent=len(new), review_updates_sent=len(updated),
        selected_songs_without_rating_request=len(ids-acted),
        rating_requests_outside_observed_selection=len(acted-ids),
        playlist_library_calls=len(named(rr, 'spotify__show_playlist_library')),
        liked_song_calls=len(named(rr, 'spotify__show_liked_songs')),
        limitation='Observed selection was processed; whether it equals the requested set is unestablished.')
    rr = groups[2]
    contacts = flatten(rr, 'phone__search_contacts')
    emails = {r['email'] for r in contacts}
    pending = flatten(rr, 'venmo__show_received_payment_requests')
    eligible = {p['payment_request_id'] for p in pending if p['sender']['email'] in emails}
    approvals = {r['args']['payment_request_id'] for r in named(rr, 'venmo__approve_payment_request')}
    done = named(rr, 'supervisor__complete_task')[0]
    findings['2'] = dict(
        contact_rows=len(contacts), observed_pending_requests=len(pending),
        pending_page_counts=[len(r['data']) for r in named(rr, 'venmo__show_received_payment_requests')],
        eligible_in_observations=len(eligible), approved=len(approvals),
        observed_eligible_not_approved=len(eligible-approvals),
        approvals_outside_observed_eligible=len(approvals-eligible),
        answer_supplied_for_action_request=done['args'].get('answer') is not None,
        limitation='Completion answer conflicts with public API guidance. It is not proven to be the only cause of failure.')
    rr = groups[3]
    findings['3'] = dict(
        environment_clock_calls=len(named(rr, 'phone__get_current_date_and_time')),
        task_datetime_in_initial_input='datetime' in json.loads((args.storage_root/'records/context_pilot/P22_03_ROLES/public_task.json').read_text()),
        completion_calls=len(named(rr, 'supervisor__complete_task')),
        limitation='A documented environment clock was available through discovery but not invoked. Do not replace it with the host clock or claim that no clock existed.')
    rr = groups[4]
    findings['4'] = {}
    for kind in ('text', 'voice'):
        read = named(rr, f'phone__search_{kind}_messages')
        ids = {r[f'{kind}_message_id'] for p in read for r in p['data']}
        deleted = {r['args'][f'{kind}_message_id'] for r in named(rr, f'phone__delete_{kind}_message')}
        findings['4'][kind] = dict(page_counts=[len(p['data']) for p in read],
            observed=len(ids), deletion_requests=len(deleted),
            observed_not_requested=len(ids-deleted), unobserved_requested=len(deleted-ids))
    rr = groups[5]
    compressions = named(rr, 'file_system__compress_directory')
    findings['5'] = dict(compressions_sent=len(compressions),
        delete_original_flags=sum(r['args'].get('delete_directory') is True for r in compressions),
        subsequent_directory_read=any(r['name']=='file_system__show_directory' for r in rr[rr.index(compressions[-1])+1:]),
        limitation='Compression API performs the requested directory removal with its delete flag; absence of a separate delete call is not an omission.')
    rr = groups[6]
    pages = named(rr, 'spotify__show_playlist_library')
    ids = {i for p in pages for r in p['data'] for i in r['song_ids']}
    songs = [r['data'] for r in named(rr, 'spotify__show_song')]
    examined = {s['song_id'] for s in songs}
    maximum = max(s['like_count'] for s in songs)
    answer = named(rr, 'supervisor__complete_task')[0]['args']['answer']
    findings['6'] = dict(playlist_page_counts=[len(p['data']) for p in pages],
        explicit_page_limit='page_limit' in pages[0]['args'],
        explicit_next_page_calls=sum(p['args'].get('page_index', 0)>0 for p in pages),
        observed_unique_songs=len(ids), examined_songs=len(examined),
        observed_songs_not_examined=len(ids-examined), observed_maximum=maximum,
        answer_matches_maximum_in_observations=answer in {s['title'] for s in songs if s['like_count']==maximum},
        limitation='Default limit is five. A full first page alone does not establish exhaustive enumeration. No unseen global maximum was read or supplied.')
    output = dict(phase='P22', kind='posthoc_public_trace_diagnostics', all_six_reviewed=True,
        findings=findings, source_hashes=hashes, script_sha256=sha(Path(__file__)),
        model_calls=0, environment_calls=0, hidden_evaluator_details_read=False,
        purpose='Describe observable behavior, not assign definitive causal error labels or create an execution oracle.')
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

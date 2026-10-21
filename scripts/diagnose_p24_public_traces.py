"""Post-hoc observable behavior of all six completed P24 development tasks.

No hidden tests, database state, evaluator bodies or model reasoning are read.
These task-specific descriptive computations are not an autonomous verifier.
"""
import argparse
import hashlib
import json
from pathlib import Path

from diagnose_p22_public_traces import named, flatten


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(root, phase, number):
    suffix='GUIDED' if phase=='P24' else 'ROLES'
    folder=root/'records/context_pilot'/f'{phase}_{number:02d}_{suffix}'
    rows=[]
    for sid,span in json.loads((folder/'spans.json').read_text()).items():
        action=span.get('action') or {}
        observation=span.get('observation',{})
        try:
            data=json.loads(observation.get('observation','null'))
        except (ValueError,TypeError):
            data=None
        rows.append(dict(id=sid,name=action.get('name'),
            args=json.loads(action.get('arguments','{}')),data=data,
            dispatched='observation' in observation))
    return rows,{name:sha(folder/name) for name in ('public_task.json','spans.json')}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError('preserve previous diagnosis')
    root=args.storage_root
    for phase in ('P22','P24'):
        if json.loads((root/'records/context_pilot'/f'{phase}_batch_v01/status.json').read_text())['status']!='complete':
            raise ValueError('wait for the complete batches')
    groups,hashes={},{}
    for i in range(1,7):
        groups[i],hashes[f'P24_{i:02d}']=read(root,'P24',i)
    findings={}
    r=groups[1]
    playlists=flatten(r,'spotify__show_playlist_library')
    playlist_ids={i for row in playlists for i in row['song_ids']}
    liked=flatten(r,'spotify__show_liked_songs')
    liked_ids={row['song_id'] for row in liked}
    intersection=playlist_ids & liked_ids
    queries=named(r,'spotify__show_song_reviews')
    review_to_song={v['song_review_id']:q['args']['song_id'] for q in queries for v in q['data']}
    new=named(r,'spotify__review_song');updates=named(r,'spotify__update_song_review')
    acted={q['args']['song_id'] for q in new}|{review_to_song[q['args']['review_id']] for q in updates}
    findings['1']=dict(playlist_rows=len(playlists),playlist_song_ids=len(playlist_ids),
        liked_song_ids=len(liked_ids),liked_page_counts=[len(q['data']) for q in named(r,'spotify__show_liked_songs')],
        observed_intersection=len(intersection),review_queries=len(queries),
        unique_songs_queried=len({q['args']['song_id'] for q in queries}),
        new_reviews=len(new),review_updates=len(updates),
        observed_intersection_not_acted=len(intersection-acted),
        actions_outside_observed_intersection=len(acted-intersection),
        limitation='The intersection is reconstructed after execution from public observations, not a hidden target or runtime contract.')

    old,hashes['P22_02']=read(root,'P22',2)
    def approvals(rows):
        return {q['args']['payment_request_id']:{k:v for k,v in q['args'].items() if k!='access_token'}
                for q in named(rows,'venmo__approve_payment_request')}
    before,after=approvals(old),approvals(groups[2])
    findings['2']=dict(approval_count=len(after),same_approval_ids=set(before)==set(after),
        same_explicit_non_auth_approval_arguments=before==after,
        baseline_answer_supplied=named(old,'supervisor__complete_task')[0]['args'].get('answer') is not None,
        guided_answer_supplied=named(groups[2],'supervisor__complete_task')[0]['args'].get('answer') is not None,
        contact_queries=len(named(groups[2],'phone__search_contacts')),
        limitation='Approval arguments match and the completion answer was omitted, but no isolated completion-only replay or hidden-test diagnosis was performed.')

    r=groups[3];files=named(r,'file_system__show_file')
    contents=[q['data'].get('content') for q in files if isinstance(q['data'],dict)]
    findings['3']=dict(environment_clock_calls=len(named(r,'phone__get_current_date_and_time')),
        environment_clock_spans=[q['id'] for q in named(r,'phone__get_current_date_and_time')],
        show_file_calls=len(files),string_contents=sum(isinstance(c,str) for c in contents),
        binary_label_20_character_contents=sum(isinstance(c,str) and len(c)==20 and 'binary' in c.lower() for c in contents),
        completion_calls=len(named(r,'supervisor__complete_task')),
        limitation='Clock use and successful completion co-occur. No per-instruction causal effect or PDF decoding mechanism is inferred.')

    r=groups[4];findings['4']={}
    for kind in ('text','voice'):
        pages=named(r,f'phone__search_{kind}_messages')
        observed={v[f'{kind}_message_id'] for q in pages for v in q['data']}
        sent={q['args'][f'{kind}_message_id'] for q in named(r,f'phone__delete_{kind}_message')}
        findings['4'][kind]=dict(page_counts=[len(q['data']) for q in pages],
            observed=len(observed),delete_requests=len(sent),
            observed_not_requested=len(observed-sent),unobserved_requested=len(sent-observed))
    r=groups[5];compressed=named(r,'file_system__compress_directory')
    findings['5']=dict(compressions_sent=len(compressed),
        delete_original_flags=sum(q['args'].get('delete_directory') is True for q in compressed),
        directory_reads=len(named(r,'file_system__show_directory')),
        non_json_directory_observations=sum(q['data'] is None for q in named(r,'file_system__show_directory')),
        subsequent_directory_read=any(q['name']=='file_system__show_directory' for q in r[r.index(compressed[-1])+1:]),
        limitation='A non-JSON directory response is retained, not silently counted as an empty directory or a successful read.')

    r=groups[6];pages=named(r,'spotify__show_playlist_library')
    ids={i for q in pages for playlist in q['data'] for i in playlist['song_ids']}
    songs=[q['data'] for q in named(r,'spotify__show_song')]
    examined={s['song_id'] for s in songs};maximum=max(s['like_count'] for s in songs)
    answer=named(r,'supervisor__complete_task')[0]['args']['answer']
    findings['6']=dict(playlist_page_counts=[len(q['data']) for q in pages],
        requested_page_limits=[q['args'].get('page_limit') for q in pages],
        observed_unique_songs=len(ids),examined_unique_songs=len(examined),
        observed_songs_not_examined=len(ids-examined),
        answer_matches_maximum_in_observations=answer in {s['title'] for s in songs if s['like_count']==maximum},
        limitation='Eight rows are below the requested limit of twenty. Observed coverage is described; no unseen database population was read.')
    output=dict(phase='P24',kind='posthoc_public_trace_diagnostics',all_six_reviewed=True,
        findings=findings,source_hashes=hashes,script_sha256=sha(Path(__file__)),
        model_calls=0,environment_calls=0,hidden_evaluator_details_read=False,
        purpose='Descriptive behavior checks, not causal attribution, a learned mechanism, or a runtime oracle.')
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(findings,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

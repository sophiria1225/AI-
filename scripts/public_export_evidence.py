"""Ordinary public-prefix checks for one known export-then-delete instruction.

Hand-authored task interpretation and trusted API semantics are prerequisites.
No API execution, private state, evaluator, model, or filesystem read occurs.
The checker does not authorize deletion; it describes already observed events.
"""
import json
from pathlib import PurePosixPath
import re

from diagnose_p25_public_traces import compare_csv
from inspect_public_move_scope import payload, digest_text
from public_move_evidence import canonical

TEMPLATE = re.compile(
    r'Export a unique list of all the songs in my song and album library and all playlists '
    r'in my Spotify account into "([^"]+)" file in my file system\. The file should have '
    r'headers, "Title" and "Artists" and artists should be separated by "\|"\. '
    r'Terminate my account after this backup is complete\.')
LIBRARIES = ('song', 'album', 'playlist')
DELETED = 'User account with all data belonging to it have been deleted.'
SAFE_OTHER = frozenset({'api_docs__show_app_descriptions','api_docs__show_api_descriptions',
    'api_docs__show_api_doc','supervisor__show_account_passwords','supervisor__show_profile',
    'supervisor__show_active_task','supervisor__complete_task','phone__get_current_date_and_time'})


def inspect_export(task, spans, events, usage):
    """Report supported/contradicted/unknown at each whole model-call boundary."""
    match = TEMPLATE.fullmatch(task.get('instruction', ''))
    if not match or task.get('ground_truth_loaded') is not False:
        raise ValueError('public task in the single known instruction template required')
    target = match.group(1)
    if not target.startswith('~/') or str(PurePosixPath(target)) != target or '..' in PurePosixPath(target).parts:
        raise ValueError('only a canonical home-relative target is supported')
    if len(events)>4000 or len(usage)>80: raise ValueError('bounded public prefix exceeded')
    positions={u['id']:n for n,u in enumerate(usage)}
    ranks=[positions.get(e['call'],-1) for e in events]
    if (len(positions)!=len(usage) or -1 in ranks or ranks!=sorted(ranks)
            or len(events)!=len(spans) or len({e['span_id'] for e in events})!=len(events)
            or {e['span_id'] for e in events}!=set(spans)):
        raise ValueError('chronological complete public events required')
    pages={k:{} for k in LIBRARIES};limits={};metadata={};taints=set()
    spotify_scope=file_scope=None;home=None
    writes=[];deletions=[];boundaries=[];readbacks=0

    def source_state():
        complete={};ids=set()
        for kind,group in pages.items():
            empty=sorted(n for n,v in group.items() if not v)
            terminal=empty[0] if empty else None
            complete[kind]=(terminal is not None and set(range(terminal+1))<=set(group)
                and not any(v for n,v in group.items() if n>terminal))
            object_ids=set()
            for values in group.values():
                for item in values:
                    key='song_id' if kind=='song' else kind+'_id'
                    if item[key] in object_ids: taints.add('duplicate_source_object_across_pages')
                    object_ids.add(item[key])
                    ids.update([item['song_id']] if kind=='song' else item['song_ids'])
        return complete,ids

    def csv_evidence(content):
        complete,ids=source_state()
        result={'trace_support':'unknown','reasons':[], 'source_terminal_pages':complete,
            'source_ids':len(ids),'source_metadata_ids':len(ids & set(metadata))}
        if taints or not all(complete.values()):
            result['reasons']=['tainted_or_incomplete_source_scope'];return result
        if not ids<=set(metadata):
            result['reasons']=['missing_source_metadata'];return result
        if len({metadata[i] for i in ids}) != len(ids):
            result['reasons']=['ambiguous_same_title_artists_for_distinct_song_ids'];return result
        if not isinstance(content,str) or len(content)>1048576:
            result['reasons']=['unsupported_content_size_or_type'];return result
        comparison=compare_csv(content,metadata,ids);result['csv']=comparison
        good=(comparison['status']=='compared_to_observed_metadata'
            and comparison['all_observed_ids_have_metadata']
            and comparison['rows']==len(ids) and comparison['duplicate_rows']==0
            and comparison['missing_known_pairs']==0 and comparison['unmatched_pairs']==0)
        result['trace_support']='supported' if good else 'contradicted'
        result['reasons']=[] if good else ['written_csv_differs_from_complete_observed_sources']
        return result

    def add_song(item, expected=None):
        if not isinstance(item,dict):return
        if expected is not None and item.get('song_id')!=expected:
            taints.add('song_response_identity_mismatch');return
        if not all(k in item for k in ('song_id','title','artists')):return
        sid=item['song_id'];artists=item['artists']
        if (type(sid)is not int or sid<=0 or not isinstance(item['title'],str)
                or not isinstance(artists,list) or not artists or not all(isinstance(a,dict)
                and isinstance(a.get('name'),str) and a['name'] and '|' not in a['name'] for a in artists)):
            taints.add('unsupported_song_metadata');return
        pair=(item['title'],'|'.join(a['name'] for a in artists))
        if sid in metadata and metadata[sid]!=pair:taints.add('changed_song_metadata')
        metadata[sid]=pair
        if len(metadata)>512:raise ValueError('metadata capacity exceeded')

    def bind(args,kind):
        nonlocal spotify_scope,file_scope
        token=args.get('access_token')
        if not isinstance(token,str) or not token:taints.add('missing_credential_scope');return False
        digest=digest_text(token);old=spotify_scope if kind=='spotify' else file_scope
        if old is not None and digest!=old:taints.add('changed_'+kind+'_credential_scope');return False
        if kind=='spotify':spotify_scope=digest
        else:file_scope=digest
        return True

    def consume(e):
        nonlocal home,readbacks
        if e.get('effects_unknown'):taints.add('unknown_effects');return
        if not e.get('api_request_sent'):return
        span=spans[e['span_id']];fn=span.get('action') or {};name=fn.get('name')
        if name in SAFE_OTHER:return
        if not isinstance(name,str):raise ValueError('sent event without API name')
        raw=fn.get('arguments');args=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(args,dict):raise ValueError('invalid public action arguments')
        value=payload(span)
        if name in ('spotify__login','file_system__login'):return
        if name.startswith('spotify__'):
            authenticated=(name!='spotify__show_song' and name!='spotify__show_album')
            if authenticated and not bind(args,'spotify'):return
            if name in {f'spotify__show_{k}_library' for k in LIBRARIES}:
                if deletions:taints.add('source_read_after_account_deletion')
                kind=name[len('spotify__show_'):-len('_library')]
                allowed={'page_index','page_limit','access_token'} | ({'is_public'} if kind=='playlist' else set())
                page,limit=args.get('page_index',0),args.get('page_limit',5)
                key='song_id' if kind=='song' else kind+'_id'
                if (set(args)-allowed or args.get('is_public') is not None or type(page)is not int
                        or not 0<=page<80 or type(limit)is not int or not 1<=limit<=20
                        or not isinstance(value,list) or len(value)>limit):
                    taints.add('filtered_or_unrecognized_source_page');return
                if kind in limits and limits[kind]!=limit:taints.add('changed_page_limit');return
                limits[kind]=limit
                for item in value:
                    if not isinstance(item,dict) or type(item.get(key))is not int or item[key]<=0:
                        taints.add('invalid_source_object');return
                    song_ids=[item['song_id']] if kind=='song' else item.get('song_ids')
                    if not isinstance(song_ids,list) or any(type(i)is not int or i<=0 for i in song_ids):
                        taints.add('unrecognized_source_membership');return
                if page in pages[kind] and pages[kind][page]!=value:taints.add('changed_source_page');return
                pages[kind][page]=value
                if kind=='song':
                    for item in value:add_song(item)
                _,ids=source_state()
                if len(ids)>512:raise ValueError('source capacity exceeded')
            elif name=='spotify__show_song':add_song(value,args.get('song_id'))
            elif name in ('spotify__show_album','spotify__show_playlist'):
                key='album_id' if name.endswith('show_album') else 'playlist_id'
                if not isinstance(value,dict) or value.get(key)!=args.get(key):
                    taints.add('collection_response_identity_mismatch');return
                if not isinstance(value.get('songs'),list):taints.add('unrecognized_collection_details');return
                for item in value['songs']:add_song(item)
            elif name=='spotify__delete_account':
                success=isinstance(value,dict) and value.get('message')==DELETED
                backup=writes[-1] if writes else None
                ordered=bool(backup and backup['confirmed_write'] and backup['evidence']['trace_support']=='supported')
                deletions.append({'call':e['call'],'confirmed':success,'supported_backup_preceded':ordered})
                if not success:taints.add('deletion_without_confirmed_success')
                if len(deletions)>1:taints.add('multiple_deletion_attempts')
            else:taints.add('unhandled_spotify_effect')
        elif name.startswith('file_system__'):
            if not bind(args,'file'):return
            if name=='file_system__create_directory':
                requested=args.get('directory_path','').rstrip('/')
                if requested!=str(PurePosixPath(target).parent):taints.add('directory_outside_target_parent')
            elif name=='file_system__create_file':
                confirmed=(args.get('file_path')==target and isinstance(value,dict)
                    and value.get('message')=='File created.' and isinstance(value.get('file_path'),str))
                if confirmed:
                    returned=str(canonical(value['file_path']));suffix=target[1:]
                    confirmed=returned.endswith(suffix)
                    if confirmed:
                        candidate=returned[:-len(suffix)];canonical(candidate)
                        if home is not None and home!=candidate:confirmed=False
                        home=candidate
                evidence=csv_evidence(args.get('content'))
                content=args.get('content')
                writes.append({'call':e['call'],'confirmed_write':confirmed,'evidence':evidence,
                    'content_sha256':digest_text(content) if isinstance(content,str) else None})
                if not confirmed:taints.add('unconfirmed_target_write')
                if len(writes)>1:taints.add('multiple_writes_outside_declared_adapter_scope')
                if deletions:taints.add('backup_write_after_account_deletion')
            elif name=='file_system__show_file':
                expected=home+target[1:] if home is not None else None
                if (args.get('file_path')!=target or not isinstance(value,dict) or value.get('path')!=expected
                        or not isinstance(value.get('content'),str)):
                    taints.add('unrecognized_target_readback');return
                readbacks+=1
                if not writes or digest_text(value['content'])!=writes[-1]['content_sha256']:
                    taints.add('readback_differs_from_written_backup')
            else:taints.add('unhandled_file_effect')
        else:taints.add('unhandled_other_app_effect')

    def snapshot(cid):
        complete,ids=source_state();last=writes[-1] if writes else None
        result={'boundary':cid,'trace_support':'unknown','reasons':[],
            'source_terminal_pages':complete,'source_ids':len(ids), 'source_metadata_ids':len(ids & set(metadata)),
            'write_attempts':len(writes),'confirmed_target_writes':sum(w['confirmed_write'] for w in writes),
            'deletion_attempts':len(deletions),'confirmed_deletions':sum(d['confirmed'] for d in deletions),
            'supported_backup_preceded_deletion':bool(deletions and deletions[-1]['supported_backup_preceded']),
            'last_written_csv':last['evidence'] if last else None,'target_readbacks':readbacks}
        if taints:result['reasons']=['unsupported_or_uncertain_trace']
        elif last and last['evidence']['trace_support']=='contradicted':
            result.update(trace_support='contradicted',reasons=['written_csv_differs_from_declared_requirement'])
        elif not last:result['reasons']=['no_confirmed_backup']
        elif not deletions:result['reasons']=['required_account_deletion_not_observed']
        elif not deletions[-1]['supported_backup_preceded']:result['reasons']=['no_supported_backup_before_deletion']
        elif deletions[-1]['confirmed'] and last['confirmed_write']:
            result['trace_support']='supported'
        return result

    cursor=0
    for u in usage:
        while cursor<len(events) and events[cursor]['call']==u['id']:
            consume(events[cursor]);cursor+=1
        boundaries.append(snapshot(u['id']))
    if cursor!=len(events):raise ValueError('unconsumed public event')
    return {'boundaries':boundaries,'final':boundaries[-1] if boundaries else snapshot('initial'),
        'taint_reasons':sorted(taints),'contract_origin':'analyst-authored single known export-then-delete template',
        'official_outcome_relabelled':False,'autonomous_completion_validated':False}

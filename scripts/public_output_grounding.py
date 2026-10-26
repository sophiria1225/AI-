"""Ordinary, single-template export checking from prior public API evidence.

This is a pure prototype: it never dispatches an API, executes generated code,
reads a task database, or authorizes account deletion. A host may inspect an
actual write payload and, only on a complete contradicted proof, substitute
the returned content proposal before its one ordinary paid dispatch.
"""
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath

from public_export_evidence import TEMPLATE, LIBRARIES, DELETED, SAFE_OTHER
from public_api_envelope import PROTOCOL

VERSION = 'ordinary_public_export_grounding_v1'
PAGE_APIS = {f'spotify__show_{kind}_library': kind for kind in LIBRARIES}
PUBLIC_READS = frozenset({'spotify__show_song', 'spotify__show_album', 'spotify__show_artist'})
READS = PUBLIC_READS | frozenset(PAGE_APIS) | frozenset({'spotify__show_playlist',
    'file_system__directory_exists', 'file_system__file_exists', 'file_system__show_file'}) | SAFE_OTHER
WRITES = frozenset({'file_system__create_file', 'file_system__update_file'})


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()

PUBLIC_SOURCE_SHA256 = {'apps/api_lib.py': '573657c3db8d99def6ee92b6833fbc2fedd894be41031fe38feebab49e597485', 'apps/spotify/apis.py': 'eaa23bb250094ee3ff50330d3b75bdac86999394611a15b0b44934c90464b3f1', 'apps/spotify/models.py': 'e35f8c4cd5fcd090d8e6d187bce0ee4c2e1e2f3202ec719186d0e663a13430a6', 'apps/file_system/apis.py': '5717b0cbabf4b8647c7429a187db3b3c278e9778798a51ff83f14815f8065e22', 'apps/supervisor/apis.py': 'd9796e20cd5f4ebe21e06f7347f73ab399164d73451edbaa658cd7ff66ddaaf5'}
PUBLIC_CONTRACT_ID = digest({"version": VERSION, "public_sources": PUBLIC_SOURCE_SHA256})

def verify_public_export_sources(package_root):
    """Read pinned public implementation bytes only; do not import/execute them."""
    root = Path(package_root)
    actual = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
              for name in PUBLIC_SOURCE_SHA256}
    require(actual == PUBLIC_SOURCE_SHA256, "public_export_implementation_changed")
    return PUBLIC_CONTRACT_ID


def positive(value):
    return type(value) is int and value > 0


def text(value):
    return type(value) is str and bool(value) and len(value) <= 65536


def csv_compare(content, pairs):
    """Exact columns and artist multisets; the request specifies no artist order."""
    result = dict(status='contradicted', reasons=[], expected_rows=len(pairs))
    if type(content) is not str or len(content) > 1048576:
        return {**result, 'status': 'unknown', 'reasons': ['unsupported_content_size_or_type']}
    try:
        rows = list(csv.reader(io.StringIO(content, newline=''), strict=True))
    except csv.Error:
        return {**result, 'reasons': ['malformed_CSV']}
    header = bool(rows and rows[0] == ['Title', 'Artists'])
    values = rows[1:] if rows else []
    shaped = [tuple(row) for row in values if len(row) == 2]
    normalize = lambda pair: (pair[0], tuple(sorted(pair[1].split('|'))))
    counts, wanted = Counter(map(normalize, shaped)), Counter(map(normalize, pairs))
    result.update(header_matches=header, rows=len(values), malformed_rows=len(values)-len(shaped),
        duplicate_rows=len(shaped)-len(counts),
        missing_pairs=sum((wanted-counts).values()), extra_pairs=sum((counts-wanted).values()))
    good = header and len(values) == len(pairs) and len(shaped) == len(values) and counts == wanted
    result.update(status='supported' if good else 'contradicted',
                  reasons=[] if good else ['write_payload_differs_from_complete_observed_sources'])
    return result


class PublicExportMonitor:
    """One execution, one known public task; credentials are never public evidence."""
    def __init__(self, task, *, execution_scope):
        require(type(execution_scope) is str and bool(execution_scope), 'execution_scope_required')
        match = TEMPLATE.fullmatch(task.get('instruction', ''))
        require(match is not None and task.get('ground_truth_loaded') is False,
                'single_public_export_template_required')
        target = match.group(1)
        require(target.startswith('~/') and str(PurePosixPath(target)) == target
                and '..' not in PurePosixPath(target).parts, 'canonical_home_target_required')
        principal = task.get('supervisor', {}).get('email')
        require(text(principal), 'public_supervisor_email_required')
        self.target, self.principal = target, principal
        self.execution_scope_sha256 = digest(execution_scope)
        self.requirement_sha256 = digest(task)
        self.tokens = {'spotify': set(), 'file_system': set()}
        self.pages = {kind: {} for kind in LIBRARIES}
        self.songs, self.song_parts, self.artists = {}, {}, {}
        self.taints, self.seen, self.source_digests = set(), set(), []
        self.nonces = set()
        self.stats = Counter()
        self.backup, self.deletion = None, None

    def _credential(self, app, args):
        token = args.get('access_token')
        return text(token) and digest(token) in self.tokens[app]

    def _put(self, mapping, key, value, conflict):
        if key in mapping and mapping[key] != value:
            self.taints.add(conflict)
        else:
            mapping[key] = value
        require(len(mapping) <= 512, 'bounded_metadata_capacity')

    def _artist(self, value, expected=None):
        if not (type(value) is dict and positive(value.get('artist_id', value.get('id')))
                and text(value.get('name')) and '|' not in value['name']):
            self.taints.add('unsupported_artist_metadata'); return
        aid = value.get('artist_id', value.get('id'))
        if expected is not None and aid != expected:
            self.taints.add('artist_response_identity_mismatch'); return
        self._put(self.artists, aid, value['name'], 'changed_artist_name')

    def _song(self, value, expected=None, *, partial=False):
        key = 'id' if partial else 'song_id'
        if not (type(value) is dict and positive(value.get(key)) and text(value.get('title'))):
            self.taints.add('unsupported_song_metadata'); return
        sid = value[key]
        if expected is not None and sid != expected:
            self.taints.add('song_response_identity_mismatch'); return
        if partial:
            ids = value.get('artist_ids')
            if not (type(ids) is list and ids and len(ids) <= 512 and all(positive(i) for i in ids)):
                self.taints.add('unsupported_song_artist_references'); return
            self._put(self.song_parts, sid, (value['title'], tuple(ids)), 'changed_song_metadata')
        else:
            artists = value.get('artists')
            if not (type(artists) is list and artists and len(artists) <= 512 and all(
                    type(a) is dict and positive(a.get('id')) and text(a.get('name'))
                    and '|' not in a['name'] for a in artists)):
                self.taints.add('unsupported_song_artist_names'); return
            for artist in artists:
                self._artist(artist)
            self._put(self.songs, sid, (value['title'], '|'.join(a['name'] for a in artists)),
                      'changed_song_metadata')

    def _page(self, kind, args, value):
        allowed = {'access_token', 'page_index', 'page_limit'} | ({'is_public'} if kind == 'playlist' else set())
        page, limit = args.get('page_index', 0), args.get('page_limit', 5)
        if (set(args) - allowed or args.get('is_public') is not None or type(page) is not int
                or not 0 <= page < 80 or type(limit) is not int or not 1 <= limit <= 20
                or type(value) is not list or len(value) > limit):
            self.taints.add('filtered_or_unsupported_source_page'); return
        normalized = []
        for item in value:
            key = 'song_id' if kind == 'song' else kind + '_id'
            if not (type(item) is dict and positive(item.get(key))):
                self.taints.add('invalid_library_object'); return
            ids = [item[key]] if kind == 'song' else item.get('song_ids')
            if not (type(ids) is list and len(ids) <= 512 and all(positive(i) for i in ids)):
                self.taints.add('invalid_library_membership'); return
            normalized.append((item[key], tuple(ids)))
            if kind == 'song':
                self._song(item, item[key])
            elif kind == 'album':
                artists = item.get('artists')
                if type(artists) is list:
                    for artist in artists:
                        self._artist(artist)
        group = self.pages[kind].setdefault(limit, {})
        if page in group and group[page] != normalized:
            self.taints.add('changed_source_page')
        group[page] = normalized

    def source_state(self):
        complete, wanted = {}, set()
        for kind, series in self.pages.items():
            complete_sequences = []
            for limit, pages in series.items():
                terminals = sorted(n for n, rows in pages.items() if len(rows) < limit)
                if not terminals or not set(range(terminals[0]+1)) <= set(pages):
                    continue
                end = terminals[0]
                sequence = sum((pages[n] for n in range(end+1)), [])
                if len({item[0] for item in sequence}) != len(sequence) or any(
                        rows for n, rows in pages.items() if n > end):
                    self.taints.add('inconsistent_library_pagination'); continue
                complete_sequences.append(sequence)
            complete[kind] = bool(complete_sequences)
            if complete_sequences:
                sequence = complete_sequences[0]
                if any(other != sequence for other in complete_sequences):
                    self.taints.add('changed_complete_library_inventory')
                for limit, pages in series.items():
                    if any(rows != sequence[n*limit:(n+1)*limit] for n, rows in pages.items()):
                        self.taints.add('source_page_disagrees_with_complete_inventory')
                wanted.update(sid for _, ids in sequence for sid in ids)
        require(len(wanted) <= 512, 'bounded_source_union')
        metadata = dict(self.songs)
        for sid, (title, aids) in self.song_parts.items():
            if all(aid in self.artists for aid in aids):
                pair = (title, '|'.join(self.artists[aid] for aid in aids))
                if sid in metadata and metadata[sid] != pair:
                    self.taints.add('direct_and_joined_song_metadata_disagree')
                metadata[sid] = pair
        evidence = dict(source_complete=complete, source_ids=len(wanted),
            metadata_ids=len(wanted & metadata.keys()),
            missing_metadata_ids=len(wanted - metadata.keys()),
            direct_metadata_ids=len(wanted & self.songs.keys()),
            joined_metadata_ids=len((wanted & metadata.keys()) - self.songs.keys()),
            source_evidence_sha256=digest(self.source_digests))
        return evidence, wanted, metadata

    def propose(self, name, args, *, mode='check'):
        """Inspect the actual imminent API arguments, before dispatch/observation.

        Unknown/out-of-scope writes retain their original arguments. No future
        response or request-supplied ID/value becomes source evidence here.
        """
        require(mode in ('check', 'repair'), 'fixed_monitor_mode_required')
        evidence, ids, metadata = self.source_state()
        result = dict(status='outside_scope', reasons=[], replacement_args=None,
                      evidence=evidence, execution_scope_sha256=self.execution_scope_sha256,
                      requirement_sha256=self.requirement_sha256, public_source_contract_id=PUBLIC_CONTRACT_ID)
        if name not in WRITES or type(args) is not dict or args.get('file_path') != self.target:
            return result
        result.update(status='unknown', original_arguments_sha256=digest(args))
        allowed = {'access_token', 'file_path', 'content'} | ({'overwrite'} if name.endswith('create_file') else set())
        reasons = []
        if (set(args) - allowed or not self._credential('file_system', args)
                or ('overwrite' in args and type(args['overwrite']) is not bool)):
            reasons.append('write_scope_or_argument_shape_unverified')
        if self.taints: reasons.append('uncertain_or_changed_public_source')
        if not all(evidence['source_complete'].values()): reasons.append('incomplete_source_inventory')
        if evidence['missing_metadata_ids']: reasons.append('missing_source_metadata')
        if self.deletion is not None: reasons.append('account_already_deleted_or_deletion_attempted')
        pairs = [metadata[i] for i in sorted(ids) if i in metadata]
        if len({(p[0], tuple(sorted(p[1].split('|')))) for p in pairs}) != len(pairs):
            reasons.append('ambiguous_duplicate_title_artist_pairs')
        if reasons:
            result['reasons'] = reasons; return result
        comparison = csv_compare(args.get('content', ''), pairs)
        result.update(status=comparison['status'], reasons=comparison['reasons'], csv=comparison)
        if comparison['status'] == 'contradicted' and mode == 'repair':
            output = io.StringIO(newline='')
            writer = csv.writer(output, lineterminator='\n')
            writer.writerow(['Title', 'Artists']); writer.writerows(pairs)
            replacement = {**deepcopy(args), 'content': output.getvalue()}
            require(csv_compare(replacement['content'], pairs)['status'] == 'supported',
                    'deterministic_repair_did_not_satisfy_observed_contract')
            result.update(replacement_args=replacement,
                          replacement_arguments_sha256=digest(replacement))
        return result

    def observe(self, event, span):
        """Consume one closed trusted event; register only successful dispatches."""
        sid = event.get('span_id')
        require(type(sid) is str and sid and sid == span.get('id') and sid not in self.seen,
                'unique_ordered_source_event_required')
        require(len(self.seen) < 4000, 'bounded_source_events')
        self.seen.add(sid)
        if event.get('stage') != 'python_api':
            return
        self.stats['python_api_records'] += 1
        require(type(event.get('api_request_sent')) is bool, 'explicit_dispatch_flag_required')
        if event.get('api_request_sent') is not True:
            self.stats['unsent_ignored'] += 1; return
        fn = span.get('action')
        require(type(fn) is dict and type(fn.get('name')) is str, 'public_API_action_required')
        name = fn['name']; args = json.loads(fn['arguments'])
        require(type(args) is dict, 'public_API_arguments_required')
        receipt = event.get('api_execution')
        if (event.get('effects_unknown') or type(receipt) is not dict
                or receipt.get('protocol') != PROTOCOL
                or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries') != 0
                or receipt.get('status') in ('unknown', 'not_dispatched')):
            self.taints.add('unknown_or_untyped_API_effect'); return
        nonce = receipt.get('nonce')
        require(text(nonce) and nonce not in self.nonces, 'unique_typed_dispatch_nonce_required')
        self.nonces.add(nonce)
        status = receipt.get('status')
        if status not in ('returned', 'raised'):
            self.taints.add('unknown_typed_dispatch_status'); return
        if status != 'returned':
            self.stats['failed_dispatches'] += 1
            if name in READS or name in ('spotify__login', 'file_system__login'):
                self.stats['failed_non_source_reads_ignored'] += 1; return
            if name in WRITES:
                self.backup = None; self.stats['failed_target_write_invalidated'] += 1; return
            self.taints.add('unverified_failed_mutation'); return
        value = span.get('observation', {}).get('observation')
        if type(value) is str:
            try: value = json.loads(value)
            except ValueError: self.taints.add('unrecognized_public_return'); return
        self.stats['returned_dispatches'] += 1
        if name in ('spotify__login', 'file_system__login'):
            app = name.split('__')[0]
            if (args.get('username') == self.principal and type(value) is dict
                    and text(value.get('access_token')) and value.get('token_type') == 'Bearer'):
                self.tokens[app].add(digest(value['access_token']))
                self.stats['same_principal_logins'] += 1
                self.source_digests.append(digest({'event': event, 'span': span}))
            else:
                self.stats['unbound_logins'] += 1
            return
        if name in SAFE_OTHER:
            return
        if name in PAGE_APIS or name == 'spotify__show_playlist':
            if not self._credential('spotify', args):
                self.taints.add('unverified_library_principal'); return
        if name in PAGE_APIS:
            self._page(PAGE_APIS[name], args, value)
        elif name == 'spotify__show_song':
            if not positive(args.get('song_id')):
                self.taints.add('invalid_requested_song_ID'); return
            self._song(value, args['song_id'])
        elif name == 'spotify__show_artist':
            if not positive(args.get('artist_id')):
                self.taints.add('invalid_requested_artist_ID'); return
            self._artist(value, args.get('artist_id'))
        elif name in ('spotify__show_album', 'spotify__show_playlist'):
            key = 'album_id' if name.endswith('show_album') else 'playlist_id'
            if not (positive(args.get(key)) and type(value) is dict and value.get(key) == args[key]
                    and type(value.get('songs')) is list and len(value['songs']) <= 512):
                self.taints.add('collection_response_identity_or_shape_mismatch'); return
            for song in value['songs']:
                self._song(song, partial=True)
            if name == 'spotify__show_album' and type(value.get('artists')) is list:
                for artist in value['artists']:
                    self._artist(artist)
        elif name in WRITES:
            assessment = self.propose(name, args)
            valid = (assessment['status'] == 'supported' and type(value) is dict
                and value.get('message') == ('File created.' if name.endswith('create_file') else 'File content updated.')
                and text(value.get('file_path')) and value['file_path'].endswith(self.target[1:]))
            self.backup = dict(confirmed=bool(valid), source_status=assessment['status'],
                content_sha256=digest(args.get('content', '')), path=value.get('file_path') if type(value) is dict else None)
            self.stats['target_write_returns'] += 1
            return
        elif name == 'spotify__delete_account':
            self.deletion = dict(confirmed=self._credential('spotify', args) and type(value) is dict
                and value.get('message') == DELETED,
                supported_backup_preceded=bool(self.backup and self.backup['confirmed']))
            return
        elif name.startswith('file_system__'):
            if name in READS or name == 'file_system__create_directory':
                return
            self.backup = None; self.taints.add('unhandled_file_mutation'); return
        else:
            self.taints.add('unhandled_source_effect'); return
        self.source_digests.append(digest({'event': event, 'span': span}))

    def summary(self):
        evidence, _, _ = self.source_state()
        backup = deepcopy(self.backup)
        if backup is not None:
            backup['path_sha256'] = digest(backup.pop('path'))
        return dict(version=VERSION, public_source_contract_id=PUBLIC_CONTRACT_ID, evidence=evidence, taint_reasons=sorted(self.taints),
            counts=dict(self.stats), backup=backup, deletion=deepcopy(self.deletion),
            task_quality_established=False, live_integration=False, novel_method_claim=False)

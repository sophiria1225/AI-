"""Observed public fields from libraries, albums and playlists in one epoch.

This is ordinary bounded cross-API reuse, not a new-method claim. In particular,
album artist_ids are not assumed to match Song.artists order. Only a playlist's
ordered Song.artists IDs may be joined with already-observed artist names.
The existing six read-only exemptions and conservative barriers are unchanged.
"""
from copy import deepcopy

from deferred_read_obligations import Assumptions
from deferred_view_protocol import DeferredReadHost, ReadAuthority
from field_read_contract import (CONTRACT_ID, FIELDS, SOURCE, TARGET, canonical,
                                 target_identity, valid_field, verify_public_implementation)
from persistent_read_view_python import ReadViewProgram
from public_contract_read_views import PublicContractReadHost, PublicReadAuthority
from shared_api_reservations import BudgetedApiChannel

JOINED_CONTRACT_ID = 'appworld-public-song-observation-joins-v1'


def verify_joined_implementation(spotify_directory):
    verify_public_implementation(spotify_directory)
    return JOINED_CONTRACT_ID


def positive_id(value):return type(value) is int and value > 0


class JoinedPublicReadAuthority:
    def __init__(self, execution_scope, *, verified_contract, max_entities=512, max_value_bytes=65536):
        if verified_contract != JOINED_CONTRACT_ID:
            raise ValueError('reviewed_join_contract_required')
        if type(max_entities) is not int or not 1 <= max_entities <= 512:
            raise ValueError('bounded_entity_limit_required')
        if type(max_value_bytes) is not int or not 1 <= max_value_bytes <= 65536:
            raise ValueError('bounded_value_limit_required')
        self.base = PublicReadAuthority(execution_scope,verified_contract=CONTRACT_ID)
        self.max_entities,self.max_value_bytes = max_entities,max_value_bytes
        self.bounds_rejected = 0
        self.cache = self  # Existing host invalidates every source together.
        self.invalidate()

    def invalidate(self):
        self.base.cache.invalidate()
        self.epoch = None
        self.songs,self.artist_names,self.artist_orders = {},{},{}

    def _activate(self, epoch):
        if type(epoch) is not int or epoch < 0:
            self.invalidate()
            return False
        if self.epoch != epoch:
            self.invalidate()
            self.epoch = epoch
        return True

    def _bounded(self, value):
        try:ok = len(canonical(value).encode()) <= self.max_value_bytes
        except (ValueError,TypeError,RecursionError):ok = False
        self.bounds_rejected += int(not ok)
        return ok

    def _versions(self, versions, value):
        if self._bounded(value) and len(versions) < 2:
            versions[canonical(value)] = deepcopy(value)

    def _song(self, identity):
        if identity not in self.songs and len(self.songs) >= self.max_entities:
            self.bounds_rejected += 1
            return None
        return self.songs.setdefault(identity,{})

    def _names(self, artists):
        if not valid_field('artists',artists):return
        for artist in artists:
            identity = artist['id']
            if identity not in self.artist_names and len(self.artist_names) >= self.max_entities:
                self.bounds_rejected += 1
                continue
            self._versions(self.artist_names.setdefault(identity,{}),artist['name'])

    def _full_fields(self, record):
        if (type(record) is not dict or not positive_id(record.get('song_id'))
                or not self._bounded(record)):return
        fields = self._song(record['song_id'])
        if fields is None:return
        for key in FIELDS:
            if key in record and valid_field(key,record[key]):
                self._versions(fields.setdefault(key,{}),record[key])
        self._names(record.get('artists'))

    def observe(self, action, value, epoch):
        if not self._activate(epoch):return
        name = action['app']+'__'+action['api'];args = action['args']
        if name == TARGET:
            identity = target_identity(name,args)
            if (identity is None or type(value) is not dict
                    or type(value.get('song_id')) is not int or value['song_id'] != identity
                    or not all(k in value and valid_field(k,value[k]) for k in FIELDS)):
                return
            self.base.observe(action,value,epoch)
            self._full_fields(value)
            return
        self.base.observe(action,value,epoch)
        if name == SOURCE:
            if (not set(args) <= {'access_token','page_index','page_limit'}
                    or type(args.get('access_token')) is not str or not args['access_token']
                    or type(value) is not list):return
            for record in value:self._full_fields(record)
            return
        playlist = name == 'spotify__show_playlist'
        album = name == 'spotify__show_album'
        key = 'playlist_id' if playlist else 'album_id'
        required = {key,'access_token'} if playlist else {key}
        if (not (playlist or album) or set(args) != required or not positive_id(args.get(key))
                or type(value) is not dict or type(value.get(key)) is not int or value[key] != args[key]
                or type(value.get('songs')) is not list
                or playlist and (type(args.get('access_token')) is not str or not args['access_token'])):
            return
        if album:self._names(value.get('artists'))
        for record in value['songs']:
            if (type(record) is not dict or not positive_id(record.get('id'))
                    or type(record.get('title')) is not str or not self._bounded(record)):
                continue
            identity = record['id'];fields = self._song(identity)
            if fields is None:continue
            self._versions(fields.setdefault('song_id',{}),identity)
            self._versions(fields.setdefault('title',{}),record['title'])
            order = record.get('artist_ids')
            if (playlist and type(order) is list and all(positive_id(i) for i in order)
                    and len(order) == len(set(order))):
                self._versions(self.artist_orders.setdefault(identity,{}),order)

    def _partial(self, identity):
        fields = self.songs.get(identity,{})
        if any(len(v) > 1 for v in fields.values()):return None
        partial = {k:deepcopy(next(iter(v.values()))) for k,v in fields.items() if len(v)==1}
        orders = self.artist_orders.get(identity,{})
        if len(orders) > 1:return None
        if len(orders) == 1:
            order = next(iter(orders.values()))
            names = [self.artist_names.get(i,{}) for i in order]
            if any(len(v) > 1 for v in names):return None
            if all(len(v) == 1 for v in names):
                artists = [{'id':i,'name':next(iter(v.values()))} for i,v in zip(order,names,strict=True)]
                if 'artists' in partial and canonical(partial['artists']) != canonical(artists):return None
                partial['artists'] = artists
        return partial

    def lookup(self, action, epoch):
        if not self._activate(epoch):return None
        identity = target_identity(action['app']+'__'+action['api'],action['args'])
        if identity is None:return None
        partial = self._partial(identity)
        if partial is None:return None
        existing = self.base.lookup(action,epoch)
        if existing is not None and existing[0] == 'complete':
            if any(k not in existing[1] or canonical(existing[1][k]) != canonical(v)
                   for k,v in partial.items()):return None
            return existing
        if existing is not None:
            for k,v in existing[1].items():
                if k in partial and canonical(partial[k]) != canonical(v):return None
                partial[k] = deepcopy(v)
        return ('partial',partial) if partial else None

    def grant(self, action, epoch):
        found = self.lookup(action,epoch)
        return ReadAuthority(epoch,deepcopy(found[1]),Assumptions(True,True,True)) if found else None


class JoinedPublicReadHost(PublicContractReadHost):
    def __init__(self, channel, *, execution_scope, verified_contract, defer=True):
        self.provider = JoinedPublicReadAuthority(execution_scope,verified_contract=verified_contract)
        self.active_action = None
        self.exact_reuses = 0
        DeferredReadHost.__init__(self,channel,authority=self.provider.grant,defer=defer)


class JoinedPublicReadProgram(ReadViewProgram):
    def __init__(self, session, budget, *, execution_scope, verified_contract, defer=True):
        super().__init__(session,budget,authority=None,defer=defer)
        JoinedPublicReadAuthority(execution_scope,verified_contract=verified_contract)
        self.execution_scope,self.verified_contract = execution_scope,verified_contract

    def __call__(self, source, observations, channel, **kwargs):
        if self.host is None:
            self.host = JoinedPublicReadHost(BudgetedApiChannel(channel,self.budget),
                execution_scope=self.execution_scope,verified_contract=self.verified_contract,defer=self.defer)
        return super().__call__(source,observations,channel,**kwargs)

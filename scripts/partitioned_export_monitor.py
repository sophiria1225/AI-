"""Bounded boolean-partition extension of the ordinary public export monitor.

This module dispatches no API and executes no generated source. The two boolean
playlist pages justify the whole library only under the pinned public filter,
serializer and immutable-source assumptions. Complete flags never override a
source taint. This is an ordinary evidence monitor, not a novel claim.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

import public_api_envelope
import public_export_evidence
import public_output_grounding
from public_output_grounding import PublicExportMonitor, digest, require, verify_public_export_sources

VERSION = 'ordinary_partitioned_public_export_v1'
PINNED_MONITOR_SHA256 = {
    'public_output_grounding.py': '8942b4c65bf09a572453266d64227398f9255e934ad848e63de786d849b2f535',
    'public_export_evidence.py': '7f0126dbdc59814832b0148acbc94c10fe3688c9a19ec20d142aa29a01eb672c',
    'public_api_envelope.py': 'fbfcb5bbe975f57b7f7047d1789293b1e45b165ef68e7ebd1160e51b366b6790',
}
_MODULES = (public_output_grounding, public_export_evidence, public_api_envelope)
_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_CONTRACT = {
    'version': VERSION,
    'original_public_contract_id': public_output_grounding.PUBLIC_CONTRACT_ID,
    'public_source_sha256': public_output_grounding.PUBLIC_SOURCE_SHA256,
    'monitor_source_sha256': {**PINNED_MONITOR_SHA256, 'partitioned_export_monitor.py': _SOURCE_SHA256},
    'assumption': 'one_execution_observed_effects_and_immutable_unobserved_source',
}
CONTRACT_ID = digest(_CONTRACT)


def contract_identity():
    return {**deepcopy(_CONTRACT), 'contract_id': CONTRACT_ID}


def verify_partitioned_export_sources(package_root):
    """Read public implementation bytes only; reject drift before observation."""
    require(verify_public_export_sources(package_root) == public_output_grounding.PUBLIC_CONTRACT_ID,
            'public_export_contract_changed')
    for module in _MODULES:
        path = Path(module.__file__)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == PINNED_MONITOR_SHA256[path.name],
                'ordinary_monitor_dependency_changed')
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == _SOURCE_SHA256,
            'partition_monitor_changed_since_import')
    return CONTRACT_ID


class PartitionedExportMonitor(PublicExportMonitor):
    """Keep each boolean page series distinct; never invent an unfiltered page."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.playlist_partition_pages = {False: {}, True: {}}

    def _page(self, kind, args, value):
        flag = args.get('is_public')
        if kind != 'playlist' or flag is None:
            return super()._page(kind, args, value)
        if type(flag) is not bool:
            self.taints.add('unsupported_playlist_partition_type')
            return
        if type(value) is not list or any(type(row) is not dict or row.get('is_public') is not flag
                                          for row in value):
            self.taints.add('playlist_partition_return_disagrees')
            return
        original = self.pages['playlist']
        self.pages['playlist'] = self.playlist_partition_pages[flag]
        try:
            # Internal shape validation only: original receipt/source hashes are
            # retained and no unfiltered observation is registered.
            super()._page(kind, {**args, 'is_public': None}, value)
        finally:
            self.pages['playlist'] = original

    def _complete_partition(self, series):
        sequences = []
        for limit, pages in series.items():
            terminals = sorted(n for n, rows in pages.items() if len(rows) < limit)
            if not terminals or not set(range(terminals[0]+1)) <= set(pages):
                continue
            end = terminals[0]
            sequence = sum((pages[n] for n in range(end+1)), [])
            if (len({row[0] for row in sequence}) != len(sequence)
                    or any(rows for n, rows in pages.items() if n > end)):
                self.taints.add('inconsistent_partition_pagination')
                continue
            sequences.append(sequence)
        if not sequences:
            return None
        first = sequences[0]
        if any(other != first for other in sequences):
            self.taints.add('changed_complete_partition_inventory')
        for limit, pages in series.items():
            if any(rows != first[n*limit:(n+1)*limit] for n, rows in pages.items()):
                self.taints.add('partition_page_disagrees_with_complete_inventory')
        return first

    def source_state(self):
        evidence, wanted, metadata = super().source_state()
        if self.pages['playlist'] and any(self.playlist_partition_pages.values()):
            self.taints.add('mixed_partition_and_unfiltered_scope_unsupported')
        parts = {flag: self._complete_partition(series)
                 for flag, series in self.playlist_partition_pages.items()}
        complete = all(part is not None for part in parts.values())
        if complete:
            first, second = parts[False], parts[True]
            if {row[0] for row in first} & {row[0] for row in second}:
                self.taints.add('playlist_ID_in_both_boolean_partitions')
            else:
                for _, ids in first+second:
                    wanted.update(ids)
                require(len(wanted) <= 512, 'bounded_partition_union')
                evidence['source_complete']['playlist'] = True
        evidence.update(source_ids=len(wanted), metadata_ids=len(wanted & metadata.keys()),
            missing_metadata_ids=len(wanted-metadata.keys()), direct_metadata_ids=len(wanted & self.songs.keys()),
            joined_metadata_ids=len((wanted & metadata.keys())-self.songs.keys()),
            playlist_boolean_partitions_complete=complete,
            playlist_partition_complete={'private': parts[False] is not None, 'public': parts[True] is not None})
        return evidence, wanted, metadata

    def observe(self, event, span):
        super().observe(event, span)
        if self.deletion is not None:
            # Historical acquisition evidence is retained, but a deleted source
            # is not a current, enumerable API source for new obligations.
            self.taints.add('source_account_deletion_observed')

    def propose(self, *args, **kwargs):
        result = super().propose(*args, **kwargs)
        result['public_source_contract_id'] = CONTRACT_ID
        result['original_public_source_contract_id'] = public_output_grounding.PUBLIC_CONTRACT_ID
        return result

    def summary(self):
        result = super().summary()
        result.update(version=VERSION, public_source_contract_id=CONTRACT_ID,
                      original_public_source_contract_id=public_output_grounding.PUBLIC_CONTRACT_ID)
        return result

"""P136 passive monitor: pinned boolean partitions plus one auxiliary GET.

The liked-playlist response is never target membership or metadata evidence.
Only its exact pinned read-only endpoint is exempt from the unknown-effect
fallback. Typed dispatch, nonce, credentials and prior taints remain required.
No global allowlist or previous class is modified.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import partitioned_export_monitor as previous
from partitioned_export_monitor import PartitionedExportMonitor
from public_api_envelope import PROTOCOL
from public_output_grounding import digest, require, text

VERSION = 'late_public_obligation_monitor_p136_v1'
AUXILIARY_READ = 'spotify__show_liked_playlists'
PINNED_PARTITION_SHA256 = '3a68cd2a3335b0b8d5f348ff7b174a366ed2ce6c46fc84fd81ec0225332dc007'
_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_CONTRACT = dict(version=VERSION, prior_partition_contract_id=previous.CONTRACT_ID,
    public_source_sha256=deepcopy(previous._CONTRACT['public_source_sha256']),
    partition_source_sha256=PINNED_PARTITION_SHA256, monitor_source_sha256=_SOURCE_SHA256,
    auxiliary_read=AUXILIARY_READ, auxiliary_values_enter_target_union=False,
    auxiliary_values_supply_metadata=False,
    assumption='one_execution_observed_effects_and_immutable_unobserved_source')
CONTRACT_ID = digest(_CONTRACT)


def contract_identity():
    return {**deepcopy(_CONTRACT), 'contract_id':CONTRACT_ID}


def verify_late_obligation_sources(package_root):
    require(previous.verify_partitioned_export_sources(package_root) == previous.CONTRACT_ID,
            'pinned_partition_contract_changed')
    require(hashlib.sha256(Path(previous.__file__).read_bytes()).hexdigest() == PINNED_PARTITION_SHA256,
            'pinned_partition_source_changed')
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == _SOURCE_SHA256,
            'late_monitor_changed_since_import')
    return CONTRACT_ID


class LateObligationMonitor(PartitionedExportMonitor):
    def observe(self, event, span):
        action = span.get('action')
        if (event.get('stage') != 'python_api' or type(action) is not dict
                or action.get('name') != AUXILIARY_READ):
            return super().observe(event, span)
        # This branch copies the old typed receipt boundary, without renaming an
        # API, rewriting its value, clearing a taint or touching old READS.
        sid = event.get('span_id')
        require(type(sid) is str and sid and sid == span.get('id') and sid not in self.seen,
                'unique_ordered_source_event_required')
        require(len(self.seen) < 4000, 'bounded_source_events')
        self.seen.add(sid)
        self.stats['python_api_records'] += 1
        require(type(event.get('api_request_sent')) is bool, 'explicit_dispatch_flag_required')
        if event['api_request_sent'] is not True:
            self.stats['unsent_ignored'] += 1
            return
        args = json.loads(action['arguments'])
        require(type(args) is dict, 'public_API_arguments_required')
        receipt = event.get('api_execution')
        if (event.get('effects_unknown') or type(receipt) is not dict
                or receipt.get('protocol') != PROTOCOL
                or receipt.get('bridge_request_sent') is not True
                or type(receipt.get('automatic_retries')) is not int
                or receipt['automatic_retries'] != 0
                or receipt.get('status') in ('unknown', 'not_dispatched')):
            self.taints.add('unknown_or_untyped_API_effect')
            return
        nonce = receipt.get('nonce')
        require(text(nonce) and nonce not in self.nonces, 'unique_typed_dispatch_nonce_required')
        self.nonces.add(nonce)
        status = receipt.get('status')
        if status not in ('returned', 'raised'):
            self.taints.add('unknown_typed_dispatch_status')
            return
        # A returned read from an unverified account must not be certified as a
        # same-principal auxiliary observation. A raised read supplies nothing.
        if status == 'raised':
            self.stats['failed_dispatches'] += 1
            self.stats['failed_non_source_reads_ignored'] += 1
            return
        if not self._credential('spotify', args):
            self.taints.add('unverified_auxiliary_principal')
            return
        page, limit, sort_by = args.get('page_index', 0), args.get('page_limit', 5), args.get('sort_by', '-liked_at')
        if (set(args) - {'access_token','page_index','page_limit','sort_by'}
                or type(page) is not int or page < 0
                or type(limit) is not int or not 1 <= limit <= 20
                or type(sort_by) is not str or sort_by not in ('liked_at','-liked_at','title','-title')):
            self.taints.add('unsupported_auxiliary_read_arguments')
            return
        value = span.get('observation', {}).get('observation')
        if type(value) is str:
            try:
                value = json.loads(value)
            except ValueError:
                self.taints.add('unrecognized_public_return')
                return
        if type(value) is not list or len(value) > limit:
            self.taints.add('unsupported_auxiliary_return_shape')
            return
        self.stats['returned_dispatches'] += 1
        self.stats['auxiliary_reads_ignored'] += 1
        # Raw observation remains in the host archive, and its digest binds the
        # passive evidence history. None of its IDs/values enter source tables.
        self.source_digests.append(digest({'event':event, 'span':span}))

    def summary(self):
        result = super().summary()
        result.update(version=VERSION, public_source_contract_id=CONTRACT_ID,
                      previous_partition_contract_id=previous.CONTRACT_ID)
        return result

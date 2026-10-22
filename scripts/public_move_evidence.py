"""Ordinary conditional checks for a caller-specified photo-move requirement.

Inputs are normalized public receipts from a trusted adapter, not a task oracle.
The caller supplies the interpretation of the task, a complete initial inventory,
pre-move metadata, successful move receipts, and (if observed) the current year.
This is not an autonomous task interpreter, a general file verifier, or an API
executor. A matching conditional year must never be promoted into an observed
current year. Original metadata remains anchored before the moves.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath


@dataclass(frozen=True)
class MoveRequirement:
    root: str
    month_destinations: tuple[tuple[int, str], ...]
    other_destination: str
    max_files: int = 256


def canonical(path):
    if not isinstance(path, str) or not path.startswith('/') or '\x00' in path:
        raise ValueError('an absolute public-response path is required')
    value = PurePosixPath(path)
    if '..' in value.parts or str(value) != path or path.startswith('//'):
        raise ValueError('path is not canonical')
    return value


def assess_moves(requirement, inventory, metadata, moves, *, current_year=None,
                 inventory_complete=False, evidence_tainted=False):
    """Check declared trace obligations; do not infer official task success.

    ``metadata`` has path/file_id/created_at from BEFORE any move of that file.
    ``moves`` has source/destination/response_destination/overwrite. The adapter
    admits only successful, same-scope receipts in chronological order and must
    set evidence_tainted for unaccounted mutations or uncertain effects.
    The caller must bind current_year to a successful public time observation.
    """
    result = {'trace_support': 'unknown', 'reasons': [], 'inventory_files': len(inventory),
        'metadata_files': len(metadata), 'successful_move_receipts': len(moves),
        'unique_moved_sources': 0, 'missing_sources': None, 'extra_sources': None,
        'filename_preserved_moves': 0, 'current_year_observed': current_year is not None,
        'conditional_year_checks': [], 'matched_year_is_clock_evidence': False}
    try:
        root = canonical(requirement.root)
        month_map = dict(requirement.month_destinations)
        if (len(month_map) != len(requirement.month_destinations) or not month_map
                or any(type(month) is not int or month < 1 or month > 12 for month in month_map)):
            raise ValueError('invalid month mapping')
        destinations = [*month_map.values(), requirement.other_destination]
        if any(not isinstance(x, str) or not x or x in ('.', '..') or '/' in x or '\x00' in x for x in destinations):
            raise ValueError('invalid destination component')
        if len(set(destinations)) != len(destinations):
            raise ValueError('destinations must be distinct')
        if (not inventory_complete or not inventory or evidence_tainted
                or any(len(x) > requirement.max_files for x in (inventory, metadata, moves))):
            raise ValueError('incomplete, tainted, empty, or over-capacity evidence')
        paths = [canonical(p) for p in inventory]
        if len(set(paths)) != len(paths) or any(p.parent != root for p in paths):
            raise ValueError('inventory must be a unique flat source directory')
        records = {}
        ids = set()
        for item in metadata:
            path = canonical(item['path'])
            if path in records or item['file_id'] in ids or type(item['file_id']) is not int:
                raise ValueError('duplicate or invalid source metadata')
            records[path] = datetime.fromisoformat(item['created_at'])
            ids.add(item['file_id'])
        if set(records) != set(paths):
            raise ValueError('pre-move metadata does not cover the exact inventory')
        by_source = {}
        for item in moves:
            src, dst, returned = (canonical(item[k]) for k in ('source', 'destination', 'response_destination'))
            if src in by_source or item['overwrite'] is not False or dst != returned:
                raise ValueError('duplicate move, overwrite, or response mismatch')
            by_source[src] = dst
            result['filename_preserved_moves'] += int(src.name == dst.name)
        result['unique_moved_sources'] = len(by_source)
        result['missing_sources'] = len(set(paths) - set(by_source))
        result['extra_sources'] = len(set(by_source) - set(paths))
        if set(by_source) != set(paths):
            result['reasons'].append('move_evidence_does_not_cover_exact_source_set')
            return result

        def mismatches(year):
            count = 0
            for path, created in records.items():
                folder = month_map.get(created.month, requirement.other_destination) if created.year == year else requirement.other_destination
                count += by_source[path] != root / folder / path.name
            return count

        # Every year not represented in source metadata has the same fallback
        # assignment. None denotes that symbolic class, not an invented date.
        for year in [*sorted({d.year for d in records.values()}), None]:
            result['conditional_year_checks'].append({'year': year, 'destination_mismatches': mismatches(year)})
        if current_year is None:
            result['reasons'].append('no_observed_current_year')
        elif type(current_year) is not int or not 1 <= current_year <= 9999:
            result['reasons'].append('invalid_observed_year')
        elif mismatches(current_year):
            result['trace_support'] = 'contradicted'
            result['reasons'].append('destinations_disagree_with_observed_year')
        else:
            result['trace_support'] = 'supported'
        return result
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        result['reasons'].append(str(error))
        return result

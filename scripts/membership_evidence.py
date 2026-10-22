"""Ordinary three-valued membership reuse with explicit coverage and scope.

Only a trusted adapter may supply pages, terminal-page evidence and epochs.
This answers membership in an OR of exact relation labels, never a full search.
It does not interpret a task, authorize writes, detect external changes, or
claim a new query-reuse algorithm.
"""
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceScope:
    source: str
    principal: str
    epoch: str
    contract: str

    def validate(self):
        if any(not isinstance(x, str) or not x for x in
               (self.source, self.principal, self.epoch, self.contract)):
            raise ValueError('scope fields must be nonempty strings')


@dataclass(frozen=True)
class MembershipAnswer:
    value: bool | None
    reason: str
    receipts: tuple[str, ...] = ()


class MembershipEvidence:
    def __init__(self, scope, relations, *, max_rows=4096, max_pages=128):
        if not isinstance(scope, EvidenceScope): raise ValueError('explicit scope required')
        scope.validate()
        if (not isinstance(relations, tuple) or not relations or len(relations) > 32
                or any(not isinstance(v, str) or not v for v in relations)
                or len(set(relations)) != len(relations)):
            raise ValueError('nonempty unique exact relation labels required')
        if (type(max_rows) is not int or not 1 <= max_rows <= 100000
                or type(max_pages) is not int or not 1 <= max_pages <= 10000):
            raise ValueError('finite positive bounds required')
        self.relations = relations
        self.max_rows, self.max_pages = max_rows, max_pages
        self.counts = Counter()
        self.reset(scope)

    def reset(self, scope):
        if not isinstance(scope, EvidenceScope): raise ValueError('explicit scope required')
        scope.validate()
        self.scope = scope
        self._pages = {v: {'next': 0, 'limit': None, 'closed': False, 'receipts': [], 'ids': set()}
                       for v in self.relations}
        self._identities = {}
        self._witnesses = {}
        self._receipts = set()
        self._rows = 0
        self._tainted = False
        self.counts['resets'] += 1

    def observe_page(self, *, scope, relation, page_index, page_limit, records,
                     terminal, receipt_id):
        """Atomically retain a validated page; malformed streams fail closed."""
        self.counts['pages_attempted'] += 1
        try:
            if self._tainted: raise ValueError('invalidated evidence stream')
            if scope != self.scope: raise ValueError('scope changed')
            if relation not in self._pages: raise ValueError('unsupported relation')
            page = self._pages[relation]
            if (type(page_index) is not int or page_index != page['next'] or page['closed']
                    or type(page_limit) is not int or not 1 <= page_limit <= 1000
                    or page['limit'] not in (None, page_limit)):
                raise ValueError('page sequence or size changed')
            if (type(terminal) is not bool or not isinstance(receipt_id, str) or not receipt_id
                    or receipt_id in self._receipts):
                raise ValueError('invalid terminal evidence or repeated receipt')
            if not isinstance(records, list) or len(records) > page_limit:
                raise ValueError('invalid page cardinality')
            if self._rows + len(records) > self.max_rows or len(self._receipts) >= self.max_pages:
                raise ValueError('evidence budget exhausted')
            checked = {}; keys = []
            for row in records:
                if not isinstance(row, dict): raise ValueError('invalid row')
                key = row.get('contact_id')
                if (type(key) is not int or key <= 0 or key in checked or key in page['ids']
                        or 'email' not in row):
                    raise ValueError('missing key or duplicate entity')
                email, labels = row['email'], row.get('relationships')
                if (email is not None and (not isinstance(email, str) or not email)
                        or not isinstance(labels, list)
                        or any(not isinstance(v, str) for v in labels) or relation not in labels):
                    raise ValueError('invalid key or predicate witness')
                if key in self._identities and self._identities[key] != email:
                    raise ValueError('entity key changed within epoch')
                checked[key] = email
                if email is not None: keys.append(email)
            # Do not retain part of a malformed page.
            self._identities.update(checked)
            for email in keys:
                self._witnesses.setdefault(email, set()).add(receipt_id)
            page['ids'].update(checked)
            page['next'] += 1; page['limit'] = page_limit; page['closed'] = terminal
            page['receipts'].append(receipt_id)
            self._receipts.add(receipt_id); self._rows += len(records)
            self.counts['pages_accepted'] += 1
        except (ValueError, TypeError):
            self._tainted = True
            self.counts['pages_rejected'] += 1
            raise ValueError('page rejected; reset evidence before reuse') from None

    def lookup(self, email, scope):
        if not isinstance(email, str) or not email:
            raise ValueError('membership requires a nonempty exact string key')
        if scope != self.scope:
            answer = MembershipAnswer(None, 'scope_mismatch')
        elif self._tainted:
            answer = MembershipAnswer(None, 'invalidated_evidence')
        elif email in self._witnesses:
            answer = MembershipAnswer(True, 'observed_witness', tuple(sorted(self._witnesses[email])))
        elif all(p['closed'] for p in self._pages.values()):
            receipts = tuple(r for p in self._pages.values() for r in p['receipts'])
            answer = MembershipAnswer(False, 'complete_union_absence', receipts)
        else:
            answer = MembershipAnswer(None, 'incomplete_union')
        self.counts[{True: 'positive', False: 'negative', None: 'unknown'}[answer.value]] += 1
        return answer

    def summary(self):
        """Counts only; no keys, records, principals or source values exported."""
        return {'counts': dict(self.counts), 'relations': len(self.relations),
                'closed_relations': sum(p['closed'] for p in self._pages.values()),
                'retained_rows': self._rows, 'accepted_pages': len(self._receipts),
                'tainted': self._tainted, 'full_response_supported': False}

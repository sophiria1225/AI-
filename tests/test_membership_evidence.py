import dataclasses
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from membership_evidence import EvidenceScope, MembershipEvidence


SCOPE = EvidenceScope('fixture-source', 'fixture-account', '0', 'fixture-contract')


def row(key=1, email='a@example.test', labels=None):
    return {'contact_id': key, 'email': email, 'relationships': labels or ['member']}


class MembershipEvidenceTests(unittest.TestCase):
    def cache(self, relations=('member',), **bounds):
        return MembershipEvidence(SCOPE, relations, **bounds)

    def add(self, cache, records, **changes):
        args = dict(scope=SCOPE, relation='member', page_index=0, page_limit=2,
                    terminal=False, receipt_id='r1', records=records)
        cache.observe_page(**(args | changes))

    def test_positive_witness_does_not_require_complete_enumeration(self):
        c = self.cache(); self.add(c, [row()])
        self.assertTrue(c.lookup('a@example.test', SCOPE).value)
        self.assertIsNone(c.lookup('absent@example.test', SCOPE).value)

    def test_short_page_without_terminal_evidence_is_not_closed(self):
        c = self.cache(); self.add(c, [])
        self.assertIsNone(c.lookup('absent@example.test', SCOPE).value)

    def test_negative_requires_every_disjunct_to_be_complete(self):
        c = self.cache(('member', 'colleague'))
        self.add(c, [row()], terminal=True)
        self.assertIsNone(c.lookup('b@example.test', SCOPE).value)
        self.add(c, [], relation='colleague', terminal=True, receipt_id='r2')
        result = c.lookup('b@example.test', SCOPE)
        self.assertFalse(result.value); self.assertEqual(result.receipts, ('r1', 'r2'))

    def test_full_page_then_empty_terminal_closes(self):
        c = self.cache(); self.add(c, [row(), row(2, 'b@example.test')])
        self.assertIsNone(c.lookup('c@example.test', SCOPE).value)
        self.add(c, [], page_index=1, terminal=True, receipt_id='r2')
        self.assertFalse(c.lookup('c@example.test', SCOPE).value)

    def test_every_scope_dimension_blocks_both_positive_and_negative(self):
        c = self.cache(); self.add(c, [row()], terminal=True)
        for field in ('source', 'principal', 'epoch', 'contract'):
            changed = dataclasses.replace(SCOPE, **{field: 'changed'})
            for email in ('a@example.test', 'b@example.test'):
                self.assertIsNone(c.lookup(email, changed).value)

    def test_missing_or_invalid_fields_poison_all_prior_evidence(self):
        mutations = [lambda r: r.pop('email'), lambda r: r.update(email=''),
                     lambda r: r.update(contact_id=True), lambda r: r.update(relationships=[])]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                c = self.cache(); self.add(c, [row()])
                bad = row(2, 'b@example.test'); mutation(bad)
                with self.assertRaises(ValueError):
                    self.add(c, [bad], page_index=1, receipt_id='r2', terminal=True)
                self.assertIsNone(c.lookup('a@example.test', SCOPE).value)
                self.assertIsNone(c.lookup('b@example.test', SCOPE).value)

    def test_null_email_is_known_nonmatching_value(self):
        c = self.cache(); self.add(c, [row(email=None)], terminal=True)
        self.assertFalse(c.lookup('a@example.test', SCOPE).value)

    def test_out_of_order_and_duplicate_pages_do_not_certify_absence(self):
        for changes in ({'page_index': 1}, {'page_index': -1}, {'page_index': True}):
            c = self.cache()
            with self.assertRaises(ValueError): self.add(c, [], terminal=True, **changes)
            self.assertIsNone(c.lookup('a@example.test', SCOPE).value)
        c = self.cache(); self.add(c, [row()])
        with self.assertRaises(ValueError): self.add(c, [], receipt_id='r2', terminal=True)

    def test_conflicting_identity_across_relations_invalidates(self):
        c = self.cache(('member', 'colleague')); self.add(c, [row()], terminal=True)
        with self.assertRaises(ValueError):
            self.add(c, [row(email='other@example.test', labels=['colleague'])],
                     relation='colleague', receipt_id='r2', terminal=True)
        self.assertIsNone(c.lookup('a@example.test', SCOPE).value)

    def test_shared_identity_across_relations_is_valid(self):
        c = self.cache(('member', 'colleague')); self.add(c, [row()], terminal=True)
        self.add(c, [row(labels=['colleague'])], relation='colleague', receipt_id='r2', terminal=True)
        self.assertTrue(c.lookup('a@example.test', SCOPE).value)
        self.assertFalse(c.lookup('b@example.test', SCOPE).value)

    def test_evidence_limits_cannot_silently_truncate_a_collection(self):
        for bounds in ({'max_rows': 1}, {'max_pages': 1}):
            c = self.cache(**bounds); self.add(c, [row()])
            with self.assertRaises(ValueError):
                self.add(c, [row(2, 'b@example.test')], page_index=1, receipt_id='r2', terminal=True)
            self.assertIsNone(c.lookup('b@example.test', SCOPE).value)

    def test_reset_removes_stale_positive_and_negative_evidence(self):
        c = self.cache(); self.add(c, [row()], terminal=True)
        new = dataclasses.replace(SCOPE, epoch='1'); c.reset(new)
        self.assertIsNone(c.lookup('a@example.test', new).value)
        self.assertIsNone(c.lookup('b@example.test', new).value)

    def test_later_caller_mutation_cannot_change_retained_evidence(self):
        c = self.cache(); records = [row()]; self.add(c, records, terminal=True)
        records[0]['email'] = 'changed@example.test'; records.clear()
        self.assertTrue(c.lookup('a@example.test', SCOPE).value)
        self.assertFalse(c.lookup('changed@example.test', SCOPE).value)

    def test_changing_page_size_or_reusing_receipt_fails_closed(self):
        for changes in ({'page_limit': 3, 'receipt_id': 'r2'}, {'receipt_id': 'r1'}):
            c = self.cache(); self.add(c, [row()])
            with self.assertRaises(ValueError): self.add(c, [], page_index=1, terminal=True, **changes)
            self.assertIsNone(c.lookup('x@example.test', SCOPE).value)

    def test_failed_page_does_not_retain_its_first_valid_row(self):
        c = self.cache()
        with self.assertRaises(ValueError):
            self.add(c, [row(), {'contact_id': 2}], terminal=True)
        self.assertEqual(c.summary()['retained_rows'], 0)
        self.assertIsNone(c.lookup('a@example.test', SCOPE).value)

    def test_exact_email_semantics_and_no_private_summary_values(self):
        c = self.cache(); self.add(c, [row()], terminal=True)
        self.assertFalse(c.lookup('A@example.test', SCOPE).value)
        self.assertNotIn('a@example.test', str(c.summary()))
        self.assertFalse(c.summary()['full_response_supported'])

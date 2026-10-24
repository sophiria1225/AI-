"""Check the executable specification, not arbitrary Python or real APIs."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deferred_read_obligations import (Assumptions, BudgetExhausted, ContractViolation,
                                       DeferredReadModel)

TRUSTED=Assumptions(True,True,True)
OBJECTS={'a':{'title':'alpha','rating':1}, 'b':{'title':'beta','rating':2}}


class DeferredReadObligationTests(unittest.TestCase):
    def test_partial_read_does_not_free_reserved_budget_and_last_alias_cancels(self):
        m=DeferredReadModel(OBJECTS,1); m.bind('x','a',{'title':'alpha'},TRUSTED)
        self.assertEqual(m.field('x','title'),'alpha')
        self.assertEqual(m.snapshot(),dict(spent=0,pending=1,available=0,live_objects=1,live_names=1))
        with self.assertRaises(BudgetExhausted): m.bind('z','b',{},Assumptions())
        m.alias('y','x');m.drop('x');self.assertEqual(m.pending,1)
        m.drop('y');self.assertEqual(m.snapshot()['available'],1);self.assertEqual(m.spent,0)

    def test_future_unknown_field_preserves_full_snapshot_across_mutation(self):
        m=DeferredReadModel(OBJECTS,3);m.bind('x','a',{'title':'alpha'},TRUSTED)
        self.assertEqual(m.field('x','title'),'alpha')
        m.effect({'a':{'title':'changed','rating':9}})
        self.assertEqual(m.field('x','rating'),1)
        self.assertEqual(m.field('x','title'),'alpha')
        self.assertEqual(m.materialize('x'),OBJECTS['a'])
        self.assertEqual(m.spent,2);self.assertEqual(m.pending,0)
        self.assertEqual([e['kind'] for e in m.events if e['kind'] in ('fetch','effect')],['fetch','effect'])

    def test_untrusted_or_empty_partial_is_immediate_with_original_error_timing(self):
        for assumptions,partial in [(Assumptions(),{'title':'alpha'}),(TRUSTED,{})]:
            m=DeferredReadModel(OBJECTS,2);m.bind('x','a',partial,assumptions)
            self.assertEqual(m.spent,1);self.assertEqual(m.pending,0)
        m=DeferredReadModel(OBJECTS,1)
        with self.assertRaises(KeyError):m.bind('x','missing',{'title':'unknown'},Assumptions())
        self.assertEqual(m.spent,1);self.assertEqual(m.bindings,{})

    def test_alias_survives_rebinding_and_export_is_a_defensive_copy(self):
        m=DeferredReadModel(OBJECTS,3);m.bind('x','a',{'title':'alpha'},TRUSTED);m.alias('y','x')
        m.bind('x','b',{'title':'beta'},TRUSTED)
        self.assertEqual(m.pending,2);self.assertEqual(m.field('y','rating'),1)
        v=m.materialize('y');v['title']='outside'
        self.assertEqual(m.field('y','title'),'alpha');m.drop('x')
        self.assertEqual(m.spent,1);self.assertEqual(m.pending,0)

    def test_missing_field_is_keyerror_after_exactly_one_materialization(self):
        m=DeferredReadModel(OBJECTS,1);m.bind('x','a',{'title':'alpha'},TRUSTED)
        with self.assertRaises(KeyError):m.field('x','absent')
        self.assertEqual(m.spent,1);self.assertEqual(m.pending,0)
        with self.assertRaises(KeyError):m.field('x','absent')
        self.assertEqual(m.spent,1)

    def test_failed_fallback_is_charged_poisoned_and_not_retried(self):
        m=DeferredReadModel(OBJECTS,2);m.bind('x','a',{'title':'alpha'},TRUSTED);m.fail_next_fetch=True
        with self.assertRaises(ContractViolation):m.field('x','rating')
        self.assertEqual(m.spent,1);self.assertEqual(m.pending,0)
        for action in (lambda:m.field('x','rating'),lambda:m.effect({'a':{}}),lambda:m.drop('x')):
            with self.assertRaises(ContractViolation):action()
        self.assertEqual(m.spent,1);self.assertEqual(m.epoch,0)

    def test_false_assumptions_are_failures_not_a_quality_guarantee(self):
        m=DeferredReadModel(OBJECTS,2);m.bind('x','a',{'title':'wrong'},TRUSTED)
        self.assertEqual(m.field('x','title'),'wrong')  # A trusted false premise already leaks error.
        with self.assertRaises(ContractViolation):m.materialize('x')
        n=DeferredReadModel(OBJECTS,2);n.bind('x','a',{'title':'alpha'},TRUSTED);n.epoch+=1
        with self.assertRaises(ContractViolation):n.field('x','rating')
        self.assertEqual(n.spent,0)

    def test_budget_rejection_does_not_perform_the_mutation_or_destroy_old_binding(self):
        m=DeferredReadModel(OBJECTS,1);m.bind('x','a',{'title':'alpha'},TRUSTED)
        with self.assertRaises(BudgetExhausted):m.bind('x','b',{'title':'beta'},TRUSTED)
        self.assertEqual(m.field('x','title'),'alpha')
        with self.assertRaises(BudgetExhausted):m.effect({'a':{'title':'changed'}})
        self.assertEqual(m.objects,OBJECTS);self.assertEqual(m.epoch,0)
        self.assertEqual(m.spent,1);self.assertEqual(m.field('x','rating'),1)


if __name__=='__main__':unittest.main()

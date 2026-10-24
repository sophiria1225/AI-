"""Exercise real Python ownership of the synthetic read capability."""
import copy
import gc
import json
from pathlib import Path
import pickle
import sys
import unittest
import weakref

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from explicit_deferred_read_views import ClosedReadView, ReadView, ReadViews
from deferred_read_obligations import Assumptions, ContractViolation

TRUSTED=Assumptions(True,True,True)
OBJECTS={'a':{'title':'alpha','rating':1,'tags':['old']}}


class ExplicitDeferredReadViewTests(unittest.TestCase):
    def test_container_and_closure_keep_full_future_read_available(self):
        owner=ReadViews(OBJECTS,3);view=owner.read('a',{'title':'alpha'},TRUSTED)
        cache={'saved':view};future=lambda:cache['saved']['rating']
        self.assertEqual(view['title'],'alpha');del view
        gc.collect();self.assertEqual(owner.model.pending,1)
        owner.effect({'a':{'title':'new','rating':9,'tags':[]}})
        self.assertEqual(future(),1);self.assertEqual(owner.model.spent,2)
        self.assertEqual(cache['saved']['title'],'alpha')

    def test_last_python_reference_releases_reservation_without_fetch(self):
        owner=ReadViews(OBJECTS,1);view=owner.read('a',{'title':'alpha'},TRUSTED)
        alias=[view];reference=weakref.ref(view);del view;gc.collect()
        self.assertIsNotNone(reference());self.assertEqual(owner.model.pending,1)
        alias.clear();gc.collect()
        self.assertIsNone(reference());self.assertEqual(owner.model.pending,0)
        self.assertEqual(owner.model.spent,0);self.assertEqual(owner.released_views,1)

    def test_shallow_copy_cannot_outlive_its_reservation_by_accident(self):
        owner=ReadViews(OBJECTS,1);view=owner.read('a',{'title':'alpha'},TRUSTED)
        alias=copy.copy(view);self.assertIs(alias,view);del view;gc.collect()
        self.assertEqual(owner.model.pending,1);self.assertEqual(alias['rating'],1)
        self.assertEqual(owner.model.spent,1)

    def test_full_conversion_and_serialization_materialize_and_match_immediate(self):
        for operation in (dict,repr,copy.deepcopy,lambda v:pickle.loads(pickle.dumps(v))):
            values=[]
            for defer in (False,True):
                owner=ReadViews(OBJECTS,2,defer=defer);view=owner.read('a',{'title':'alpha'},TRUSTED)
                self.assertIsInstance(view,ReadView);self.assertNotIsInstance(view,dict)
                values.append(operation(view));self.assertEqual(owner.model.spent,1)
                self.assertEqual(owner.model.pending,0)
            self.assertEqual(values[0],values[1])

    def test_readonly_copy_semantics_are_explicit_in_both_policies(self):
        for defer in (False,True):
            owner=ReadViews(OBJECTS,1,defer=defer);view=owner.read('a',{'tags':['old']},TRUSTED)
            tags=view['tags'];tags.append('local')
            self.assertEqual(view['tags'],['old'])
            with self.assertRaises(TypeError):view['rating']=2
            with self.assertRaises(TypeError):json.dumps(view)
            self.assertEqual(json.loads(json.dumps(dict(view))),OBJECTS['a'])

    def test_cyclic_python_references_delay_release_but_never_fabricate_savings(self):
        owner=ReadViews(OBJECTS,1);view=owner.read('a',{'title':'alpha'},TRUSTED)
        cycle=[view];cycle.append(cycle);del view;del cycle
        gc.collect()
        self.assertEqual(owner.model.pending,0);self.assertEqual(owner.model.spent,0)

    def test_close_is_explicit_capability_expiry_and_not_task_completion(self):
        owner=ReadViews(OBJECTS,1);view=owner.read('a',{'title':'alpha'},TRUSTED)
        owner.close();self.assertEqual(owner.task_close_releases,1)
        self.assertEqual(owner.released_views,0);self.assertEqual(owner.model.spent,0)
        with self.assertRaises(ClosedReadView):view['title']
        with self.assertRaises(ClosedReadView):owner.read('a')
        with self.assertRaises(ClosedReadView):owner.effect({})

    def test_failed_contract_remains_charged_after_python_gc(self):
        owner=ReadViews(OBJECTS,1);view=owner.read('a',{'title':'alpha'},TRUSTED)
        owner.model.fail_next_fetch=True
        with self.assertRaises(ContractViolation):view['rating']
        del view;gc.collect()
        self.assertEqual(owner.model.spent,1);self.assertTrue(owner.model.poisoned)
        self.assertEqual(owner.released_views,0)


if __name__=='__main__':unittest.main()

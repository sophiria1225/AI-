import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from contract_use_retention import use_evidence

class ContractUseTests(unittest.TestCase):
    def example(self,rows,boundary=8):
        events=[];spans={}
        for i,(call,name,args,ok) in enumerate(rows,1):
            sid='s'+str(i)
            events.append({'call':f'call_{call:03d}','span_id':sid,'stage':'python_api',
                'api_request_sent':ok,'effects_unknown':False})
            spans[sid]={'action':{'name':name,'arguments':json.dumps(args)},
                'observation':{'observation':'{}'} if ok else {'format_error':'rejected'}}
        return {'events':events,'spans':spans,'manifest':{'state':{'model_calls':boundary}}}
    schemas={'x__read':{'parameters':{'properties':{'id':{},'optional':{}}}}}
    doc=(1,'api_docs__show_api_doc',{'app_name':'x','api_name':'read'},True)

    def test_unused_contract_is_retained(self):
        row=use_evidence(self.example([self.doc]),self.schemas)['s1']
        self.assertFalse(row['used_since_document'])

    def test_use_and_complete_parameter_coverage_are_separate(self):
        prefix=self.example([self.doc,(2,'x__read',{'id':1},True)])
        row=use_evidence(prefix,self.schemas)['s1']
        self.assertTrue(row['used_since_document']);self.assertFalse(row['all_parameters_observed'])
        self.assertFalse(row['future_irrelevance_proven']);self.assertFalse(row['semantic_success_verified'])

    def test_parameter_union_is_observed_use_only(self):
        prefix=self.example([self.doc,(2,'x__read',{'id':1,'optional':'x'},True)])
        self.assertTrue(use_evidence(prefix,self.schemas)['s1']['all_parameters_observed'])

    def test_later_failure_preserves_contract(self):
        prefix=self.example([self.doc,(2,'x__read',{'id':1},True),(3,'x__read',{'bad':2},False)])
        self.assertFalse(use_evidence(prefix,self.schemas)['s1']['used_since_document'])

    def test_old_use_does_not_retire_a_new_document(self):
        prefix=self.example([self.doc,(2,'x__read',{'id':1},True),
            (3,'api_docs__show_api_doc',{'app_name':'x','api_name':'read'},True)])
        rows=use_evidence(prefix,self.schemas)
        self.assertTrue(rows['s1']['used_since_document']);self.assertFalse(rows['s3']['used_since_document'])

    def test_future_or_reordered_events_are_rejected(self):
        for rows in ([self.doc,(9,'x__read',{'id':1},True)],
                     [(2,'x__read',{'id':1},True),self.doc]):
            with self.assertRaises(ValueError):use_evidence(self.example(rows),self.schemas)

    def test_api_error_payload_is_not_success(self):
        prefix=self.example([self.doc,(2,'x__read',{'id':1},True)])
        prefix['spans']['s2']['observation']={'observation':'{"detail":"error"}'}
        self.assertFalse(use_evidence(prefix,self.schemas)['s1']['used_since_document'])

if __name__=='__main__':unittest.main()

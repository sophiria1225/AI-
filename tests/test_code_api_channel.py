import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel

def tool(name, fields=()):
    return {'type':'function','function':{'name':name,'parameters':{'properties':{k:{} for k in fields}}}}

class Bridge:
    def __init__(self): self.calls=[];self.fail=False
    def request(self, value):
        self.calls.append(value)
        if self.fail: raise TimeoutError('unknown after send')
        return {'ok':True,'result':{'observation':'[1, 2]',
            'declared_complete':value['call']['api']=='complete_task'}}

class Channels(unittest.TestCase):
    def channel(self,budget=10):
        return ApiChannel(NativeCatalog([tool('api_docs__show_api_doc',['app_name','api_name']),
            tool('shop__list'),tool('shop__write',['value']),
            tool('supervisor__complete_task')]),Bridge(),budget)
    def packet(self,c,app,api,args=None):
        return {'kind':'api','id':c.last_id+1,'app':app,'api':api,'arguments':args or {}}
    def test_discovery_is_required_and_available_within_code(self):
        c=self.channel()
        self.assertFalse(c.exchange(self.packet(c,'shop','list'))['ok'])
        self.assertEqual(len(c.bridge.calls),0)
        c.exchange(self.packet(c,'api_docs','show_api_doc',{'app_name':'shop','api_name':'list'}))
        self.assertEqual(c.exchange(self.packet(c,'shop','list'))['value'],[1,2])
        self.assertEqual(sum(x['api_request_sent'] for x in c.rows),2)
    def test_budget_and_completion_stop_later_effects(self):
        c=self.channel(1)
        c.exchange(self.packet(c,'supervisor','complete_task'))
        self.assertTrue(c.complete)
        self.assertFalse(c.exchange(self.packet(c,'supervisor','complete_task'))['ok'])
        self.assertEqual(len(c.bridge.calls),1)
        c=self.channel(0)
        self.assertFalse(c.exchange(self.packet(c,'supervisor','complete_task'))['ok'])
        self.assertEqual(len(c.bridge.calls),0)
    def test_unknown_effects_are_counted_and_block_later_calls(self):
        c=self.channel();c.bridge.fail=True
        self.assertFalse(c.exchange(self.packet(c,'supervisor','complete_task'))['ok'])
        self.assertTrue(c.fatal)
        self.assertTrue(c.rows[0]['effects_unknown'])
        self.assertFalse(c.exchange(self.packet(c,'supervisor','complete_task'))['ok'])
        self.assertEqual(len(c.bridge.calls),1)
    def test_protocol_identity_and_unknown_parameters_are_rejected(self):
        c=self.channel()
        p=self.packet(c,'supervisor','complete_task');p['id']=2
        with self.assertRaises(ValueError): c.exchange(p)
        self.assertFalse(c.exchange(self.packet(c,'supervisor','complete_task',{'secret':1}))['ok'])
        self.assertEqual(len(c.bridge.calls),0)

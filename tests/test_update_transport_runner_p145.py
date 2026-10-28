"""Failure-aware saved-input factorial checks; no models, task APIs or evaluators."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_update_transport_p145 as driver
from checkpoint_update_schema_p145 import UPDATE_SUMMARY_PROMPT, FIELDS


def fixture():
    old = {field: (['old'] if field == 'completed' else []) for field in FIELDS}
    packet = dict(previous_checkpoint=old,
        original_instructions_and_task=[{'role':'system','content':'synthetic task'}],
        older_history=[{'role':'assistant','content':'older'}, {'role':'user','content':'older observation'}],
        recent_context=[{'role':'assistant','content':'recent'}, {'role':'user','content':'recent observation'}])
    saved = dict(model='synthetic', messages=[{'role':'system','content':UPDATE_SUMMARY_PROMPT},
        {'role':'user','content':json.dumps(packet)}], max_tokens=4096, stream=False,
        reasoning_budget_tokens=-1, reasoning_format='deepseek',
        chat_template_kwargs={'thinking_mode':'enabled'}, seed=257, temperature=0.7)
    ordinary = deepcopy(saved)
    ordinary['messages'] = packet['original_instructions_and_task'] + [driver.summary_note(old)] + packet['older_history'] + packet['recent_context'] + [{'role':'user','content':'<whole_task_budget_v1>synthetic frozen budget'}]
    ordinary.update(tools=[{'type':'function','function':{'name':'synthetic'}}], tool_choice='auto', max_tokens=3097)
    updates = {field:{'keep':[],'update':[],'delete':[],'add':[]} for field in FIELDS}
    updates['completed']['update'] = [{'index':0,'text':'new'}]
    return dict(saved=saved, old=old, packet=packet, ordinary=ordinary), updates


class UpdateTransportRunnerTests(unittest.TestCase):
    def test_exact_rotated_twelve_schedule_and_payload_factor_isolation(self):
        expected = [(1,a) for a in driver.ARMS] + [(2,a) for a in driver.ARMS[1:]+driver.ARMS[:1]] + [(4,a) for a in driver.ARMS[2:]+driver.ARMS[:2]]
        self.assertEqual(driver.schedule(), expected)
        self.assertEqual(len(set(expected)), 12)
        data, _ = fixture()
        before = deepcopy(data)
        for arm in driver.ARMS:
            result = driver.payload(data['saved'], data['old'], arm)
            self.assertEqual(result['messages'], data['saved']['messages'])
            self.assertEqual(result['max_tokens'], 4096)
            self.assertEqual(result['reasoning_budget_tokens'], 2048 if arm.endswith('_bounded') else -1)
            self.assertEqual('response_format' in result, arm.startswith('schema_'))
        self.assertEqual(data, before)

    def test_materialized_actor_view_preserves_tools_budget_notice_and_recent_context(self):
        data, updates = fixture()
        before = deepcopy(data)
        result, outcome = driver.assess({'role':'assistant','content':json.dumps(updates)}, 'stop', data)
        self.assertTrue(outcome['patch_valid'])
        self.assertEqual(outcome['changed_old_items'], 1)
        self.assertEqual({k:v for k,v in result.items() if k!='messages'},
                         {k:v for k,v in data['ordinary'].items() if k!='messages'})
        self.assertEqual(result['messages'][-1], data['ordinary']['messages'][-1])
        self.assertEqual(result['messages'][-3:-1], data['packet']['recent_context'])
        self.assertEqual(result['messages'][:1], data['packet']['original_instructions_and_task'])
        self.assertEqual(data, before)

    def run_synthetic(self, kind):
        data, updates = fixture()
        calls = []
        def generate(config, endpoint, request, timeout):
            self.assertEqual(endpoint, '/v1/chat/completions')
            calls.append(deepcopy(request))
            if kind == 'unknown' and len(calls) == 1:
                raise TimeoutError('synthetic unknown usage')
            message = {'role':'assistant','content':json.dumps(data['old'] if kind=='invalid_first' and len(calls)==1 else updates)}
            count = 101 if kind=='last_usage_mismatch' and len(calls)==12 else 100
            return {'usage':{'prompt_tokens':count,'completion_tokens':10,'total_tokens':count+10},
                    'choices':[{'finish_reason':'stop','message':message}]}
        def count(request):
            if len(request['messages']) == 2:
                return 100
            if kind=='last_actor_count_failure' and len(calls)==12:
                raise ValueError('synthetic post-generation count failure')
            return 300 if request['messages']==data['ordinary']['messages'] else 200
        with tempfile.TemporaryDirectory() as temp:
            storage=Path(temp)
            (storage/'records/context_pilot').mkdir(parents=True)
            with patch.object(driver,'post',side_effect=generate), \
                    patch.object(driver,'native_count',side_effect=count), \
                    patch.object(driver,'live_identity',return_value=({'synthetic':True},'unused')), \
                    patch.object(driver,'wait_idle',return_value={'one_slot_idle':True}), \
                    patch.object(driver.signal,'alarm',return_value=0), redirect_stdout(io.StringIO()):
                state=driver.run_batch(storage,ROOT,{}, {},{n:deepcopy(data) for n,_,_ in driver.CASES},
                    {'synthetic':True},driver.time.time()+9000)
            saved=json.loads((storage/driver.BATCH/'status.json').read_text())
            self.assertEqual(saved,state)
        return state,calls

    def test_unknown_usage_stops_after_one_dispatch_without_retry(self):
        state,calls=self.run_synthetic('unknown')
        self.assertEqual(len(calls),1)
        self.assertEqual(state['status'],'stopped')
        self.assertEqual(state['unknown_usage_calls'],1)
        self.assertEqual(state['rows'][0]['status'],'unknown')
        self.assertFalse(state['mechanism_preflight_passed'])

    def test_structural_invalidity_is_charged_and_remaining_fixed_calls_continue(self):
        state,calls=self.run_synthetic('invalid_first')
        self.assertEqual(len(calls),12)
        self.assertEqual(state['status'],'complete')
        self.assertFalse(state['rows'][0]['patch_valid'])
        self.assertEqual(state['unknown_usage_calls'],0)
        self.assertEqual(state['known_total_tokens'],1320)
        self.assertTrue(state['mechanism_preflight_passed'])
        self.assertEqual(state['candidate_for_whole_task'],'schema_bounded')

    def test_last_generation_usage_mismatch_or_actor_count_failure_blocks_gate(self):
        for kind in ('last_usage_mismatch','last_actor_count_failure'):
            with self.subTest(kind=kind):
                state,calls=self.run_synthetic(kind)
                self.assertEqual(len(calls),12)
                self.assertEqual(state['status'],'stopped')
                self.assertEqual(state['rows'][-1]['status'],'ok')
                self.assertFalse(state['mechanism_preflight_passed'])
                self.assertNotIn('finished_at',state['rows'][-1])

    def test_candidate_never_switches_to_successful_alternative_arm(self):
        state,_=self.run_synthetic('valid')
        self.assertTrue(state['mechanism_preflight_passed'])
        rows=deepcopy(state['rows'])
        for row in rows:
            if row['arm']=='schema_bounded':row['patch_valid']=False
        result=driver.summarize(rows,'complete')
        self.assertFalse(result['mechanism_preflight_passed'])
        self.assertEqual(result['candidate_for_whole_task'],'schema_bounded')
        self.assertFalse(result['candidate_selection_from_results'])
        self.assertFalse(result['whole_task_savings_established'])
        self.assertFalse(result['task_success_evaluated'])


if __name__=='__main__':
    unittest.main()

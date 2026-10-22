import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from contract_comparison import ARMS, CONDITIONS, FeedbackProgram
from run_contract_comparison import run_order


class ContractIntegrationTests(unittest.TestCase):
    def test_wrapped_execution_keeps_base_channel_effect_completion_and_budget_state(self):
        class Bridge:
            calls = 0
            def request(self, request):
                self.calls += 1
                return {'ok': True, 'result': {'observation': '{}', 'declared_complete': True}}
        catalog = NativeCatalog([{'type': 'function', 'function': {'name': 'sample__finish',
            'parameters': {'type': 'object', 'properties': {'value': {'type': 'integer'}}}}}])
        catalog.visible.add('sample__finish')
        bridge = Bridge(); base = ApiChannel(catalog, bridge, 2)
        replies = []
        def program(source, observations, channel):
            for i, args in enumerate(({'typo': 'DO_NOT_ECHO'}, {'value': 1}, {'typo': 2}), 1):
                replies.append(channel.exchange({'kind': 'api', 'id': i, 'app': 'sample',
                                                 'api': 'finish', 'arguments': args}))
            return channel.complete
        runtime = FeedbackProgram(program, 'public_schema')
        self.assertTrue(runtime('', [], base))
        self.assertTrue(base.complete); self.assertFalse(base.fatal)
        self.assertEqual(bridge.calls, 1); self.assertEqual(base.remaining, 1)
        self.assertEqual(len(base.rows), 3)
        self.assertIn('contract_feedback', replies[0]['error'])
        self.assertNotIn('DO_NOT_ECHO', replies[0]['error'])
        self.assertEqual(replies[2]['error'], 'completion, unknown effects or run budget')
        self.assertEqual(runtime.summary()['checked_requests'], 3)
        self.assertEqual(len(runtime.summary()['feedback_events']), 1)

    def test_unknown_effect_still_blocks_later_requests_on_the_original_channel(self):
        class Bridge:
            calls = 0
            def request(self, request):
                self.calls += 1
                raise TimeoutError('synthetic unknown effect')
        catalog = NativeCatalog([{'type': 'function', 'function': {'name': 'sample__send',
            'parameters': {'type': 'object', 'properties': {}}}}])
        catalog.visible.add('sample__send'); bridge = Bridge(); base = ApiChannel(catalog, bridge, 5)
        def program(source, observations, channel):
            for i in (1, 2):
                channel.exchange({'kind': 'api', 'id': i, 'app': 'sample', 'api': 'send', 'arguments': {}})
        runtime = FeedbackProgram(program, 'parameter_names'); runtime('', [], base)
        self.assertTrue(base.fatal); self.assertEqual(bridge.calls, 1)
        self.assertEqual(runtime.summary()['feedback_events'], [])

    def test_all_three_controls_cover_each_known_task_once_with_shared_schema_feedback(self):
        order = run_order([{'task_id': str(i)} for i in range(4)])
        self.assertEqual(len(order), 12)
        self.assertEqual(len({(n, arm) for n, _, arm in order}), 12)
        for n in range(1, 5):
            self.assertEqual({arm for k, _, arm in order if k == n}, set(ARMS))
        self.assertEqual(CONDITIONS[ARMS[0]][1], CONDITIONS[ARMS[2]][1])
        self.assertEqual(CONDITIONS[ARMS[1]][0], CONDITIONS[ARMS[2]][0])


if __name__ == '__main__': unittest.main()

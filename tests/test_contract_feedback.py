import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from appworld_native_tools import NativeCatalog
from contract_feedback import ContractFeedbackChannel, UNKNOWN_PARAMETER, canonical, make_feedback


FUNCTION = {'name': 'sample__send', 'description': 'Send once.', 'parameters': {
    'type': 'object', 'properties': {'private': {'type': 'boolean', 'default': False},
                                  'access_token': {'type': 'string'}}}}


class Bridge:
    def __init__(self): self.calls = []
    def request(self, value):
        self.calls.append(value)
        return {'ok': True, 'result': {'observation': '{"accepted":true}'}}


def rejected():
    return {'action': {'name': 'sample__send', 'arguments': json.dumps(
        {'privacy': 'private', 'access_token': 'DO_NOT_ECHO_CREDENTIAL'})},
        'api_request_sent': False, 'observation': {'format_error': UNKNOWN_PARAMETER}}


class ContractFeedbackTests(unittest.TestCase):
    def test_contract_is_exact_copy_without_echoing_values_or_inventing_required(self):
        row = rejected(); schema = copy.deepcopy(FUNCTION)
        result = make_feedback(row, {'sample__send': schema}, 'public_schema')
        self.assertEqual(result['public_schema'], FUNCTION)
        self.assertNotIn('DO_NOT_ECHO_CREDENTIAL', canonical(result))
        self.assertNotIn('required', result['public_schema']['parameters'])
        result['public_schema']['parameters']['properties']['private']['default'] = True
        self.assertEqual(schema, FUNCTION)
        self.assertEqual(row, rejected())

    def test_generic_and_names_remain_explicit_controls(self):
        row = rejected(); exposed = {'sample__send': FUNCTION}
        self.assertIsNone(make_feedback(row, exposed, 'generic'))
        names = make_feedback(row, exposed, 'parameter_names')
        self.assertEqual(names['allowed_parameters'], ['access_token', 'private'])
        self.assertNotIn('public_schema', names)

    def test_no_disclosure_for_unexposed_sent_ambiguous_or_other_failures(self):
        self.assertIsNone(make_feedback(rejected(), {}, 'public_schema'))
        for field, value in [('api_request_sent', True), ('effects_unknown', True),
                             ('observation', {'api_error': 'failure'}),
                             ('observation', {'not_executed': 'budget'})]:
            row = rejected(); row[field] = value
            self.assertIsNone(make_feedback(row, {'sample__send': FUNCTION}, 'public_schema'))

    def test_bounded_schema_falls_back_to_names_without_truncating_contract(self):
        schema = copy.deepcopy(FUNCTION); schema['description'] = 'x' * 20000
        result = make_feedback(rejected(), {'sample__send': schema}, 'public_schema', 1024)
        self.assertEqual(result['mode'], 'parameter_names')
        self.assertNotIn('public_schema', result)
        self.assertLessEqual(len(canonical(result)), 1024)

    def test_rejected_request_never_dispatches_or_automatically_retries(self):
        catalog = NativeCatalog([{'type': 'function', 'function': FUNCTION}])
        catalog.visible.add('sample__send'); bridge = Bridge()
        channel = ContractFeedbackChannel(catalog, bridge, 4, feedback_mode='public_schema')
        reply = channel.exchange({'kind': 'api', 'id': 1, 'app': 'sample', 'api': 'send',
                                  'arguments': {'privacy': 'secret-value'}})
        self.assertFalse(reply['ok']); self.assertEqual(bridge.calls, [])
        self.assertEqual(channel.remaining, 4)
        feedback = channel.rows[-1]['observation']['contract_feedback']
        self.assertFalse(feedback['request_dispatched']); self.assertFalse(feedback['automatic_retry'])
        self.assertNotIn('secret-value', reply['error'])

    def test_successful_request_and_budget_stop_keep_original_dispatch_semantics(self):
        catalog = NativeCatalog([{'type': 'function', 'function': FUNCTION}])
        catalog.visible.add('sample__send'); bridge = Bridge()
        channel = ContractFeedbackChannel(catalog, bridge, 1, feedback_mode='public_schema')
        packet = {'kind': 'api', 'id': 1, 'app': 'sample', 'api': 'send', 'arguments': {'private': True}}
        self.assertTrue(channel.exchange(packet)['ok']); self.assertEqual(len(bridge.calls), 1)
        self.assertEqual(channel.remaining, 0)
        packet.update(id=2, arguments={'privacy': 'invalid'})
        self.assertFalse(channel.exchange(packet)['ok']); self.assertEqual(len(bridge.calls), 1)
        self.assertNotIn('contract_feedback', channel.rows[-1]['observation'])


if __name__ == '__main__': unittest.main()

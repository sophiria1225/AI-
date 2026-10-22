import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from appworld_native_tools import NativeCatalog, dispatch_native_calls
from container_api_python import ApiChannel
from public_name_catalog import PublicNameCatalog


def tool(name, fields=None):
    return {'type': 'function', 'function': {'name': name, 'description': 'Synthetic public API',
        'parameters': {'type': 'object', 'properties': fields or {}}}}


TOOLS = [tool('api_docs__show_api_doc', {'app_name': {}, 'api_name': {}}),
         tool('supervisor__complete_task'), tool('phone__get_current_date_and_time'),
         tool('files__write', {'path': {}, 'value': {}})]


class Bridge:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def request(self, request):
        self.calls.append(copy.deepcopy(request))
        if self.fail:
            raise TimeoutError('synthetic uncertain effect')
        action = request['call']
        return {'ok': True, 'result': {'observation': '{"ok": true}',
            'declared_complete': action['app'] == 'supervisor' and action['api'] == 'complete_task'}}


def packet(number=1, app='phone', api='get_current_date_and_time', arguments=None):
    return {'kind': 'api', 'id': number, 'app': app, 'api': api, 'arguments': arguments or {}}


class PublicNameCatalogTests(unittest.TestCase):
    def test_legacy_policy_still_requires_documentation_exposure(self):
        function = {'name': 'phone__get_current_date_and_time', 'arguments': '{}'}
        with self.assertRaisesRegex(ValueError, 'supplied public schema'):
            NativeCatalog(TOOLS).decode(function)
        self.assertEqual(PublicNameCatalog(TOOLS).decode(function),
            {'app': 'phone', 'api': 'get_current_date_and_time', 'args': {}})

    def test_invocation_does_not_disclose_unrequested_schemas(self):
        catalog = PublicNameCatalog(TOOLS)
        before = catalog.tools()
        channel = ApiChannel(catalog, Bridge(), 1)
        reply = channel.exchange(packet())
        self.assertTrue(reply['ok'])
        self.assertEqual(reply['new_schemas'], {})
        self.assertEqual(catalog.tools(), before)
        self.assertNotIn('phone__get_current_date_and_time', catalog.visible)

    def test_known_call_uses_one_exact_request_without_discovery_or_repair(self):
        bridge = Bridge()
        channel = ApiChannel(PublicNameCatalog(TOOLS), bridge, 2)
        arguments = {'path': '/example', 'value': 'unchanged'}
        reply = channel.exchange(packet(app='files', api='write', arguments=arguments))
        self.assertTrue(reply['ok'])
        self.assertEqual(bridge.calls, [{'op': 'call', 'call': {'app': 'files', 'api': 'write', 'args': arguments}}])
        self.assertEqual(channel.remaining, 1)

    def test_unknown_private_and_misspelled_names_are_not_dispatched(self):
        for app, api in [('admin', 'query'), ('phone', '_private'), ('phone', 'get_current_time')]:
            with self.subTest(app=app, api=api):
                bridge = Bridge()
                channel = ApiChannel(PublicNameCatalog(TOOLS), bridge, 2)
                self.assertFalse(channel.exchange(packet(app=app, api=api))['ok'])
                self.assertEqual(bridge.calls, [])

    def test_catalog_rejects_private_or_duplicate_registration(self):
        for extra in [tool('admin__query'), tool('phone___private'), TOOLS[-1]]:
            with self.assertRaises(ValueError):
                PublicNameCatalog(TOOLS + [extra])

    def test_unknown_argument_is_not_deleted_or_dispatched(self):
        bridge = Bridge()
        channel = ApiChannel(PublicNameCatalog(TOOLS), bridge, 2)
        self.assertFalse(channel.exchange(packet(arguments={'invented': 1}))['ok'])
        self.assertEqual(bridge.calls, [])
        self.assertEqual(channel.remaining, 2)

    def test_budget_and_time_checks_still_precede_dispatch(self):
        for remaining, continue_check in [(0, lambda: True), (2, lambda: False)]:
            bridge = Bridge()
            channel = ApiChannel(PublicNameCatalog(TOOLS), bridge, remaining, continue_check)
            self.assertFalse(channel.exchange(packet())['ok'])
            self.assertEqual(bridge.calls, [])

    def test_unknown_effect_is_not_retried_and_blocks_following_calls(self):
        bridge = Bridge(fail=True)
        channel = ApiChannel(PublicNameCatalog(TOOLS), bridge, 2)
        self.assertFalse(channel.exchange(packet())['ok'])
        self.assertFalse(channel.exchange(packet(number=2))['ok'])
        self.assertEqual(len(bridge.calls), 1)
        self.assertTrue(channel.rows[0]['effects_unknown'])
        self.assertFalse(channel.rows[1]['api_request_sent'])

    def test_completion_prevents_further_dispatch(self):
        bridge = Bridge()
        channel = ApiChannel(PublicNameCatalog(TOOLS), bridge, 2)
        self.assertTrue(channel.exchange(packet(app='supervisor', api='complete_task'))['ok'])
        self.assertFalse(channel.exchange(packet(number=2))['ok'])
        self.assertEqual(len(bridge.calls), 1)

    def test_explicit_documentation_still_exposes_its_schema(self):
        catalog = PublicNameCatalog(TOOLS)
        channel = ApiChannel(catalog, Bridge(), 2)
        reply = channel.exchange(packet(app='api_docs', api='show_api_doc',
            arguments={'app_name': 'phone', 'api_name': 'get_current_date_and_time'}))
        self.assertIn('phone__get_current_date_and_time', reply['new_schemas'])
        self.assertIn('phone__get_current_date_and_time', catalog.visible)

    def test_native_explicit_schema_snapshot_is_not_bypassed(self):
        bridge = Bridge()
        message = {'tool_calls': [{'function': {'name': 'phone__get_current_date_and_time', 'arguments': json.dumps({})}}]}
        rows = dispatch_native_calls(message, PublicNameCatalog(TOOLS), bridge, lambda *a: None, remaining_api_calls=2)
        self.assertFalse(rows[0]['api_request_sent'])
        self.assertEqual(bridge.calls, [])


if __name__ == '__main__':
    unittest.main()

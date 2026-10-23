import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from code_agent_interface import CODE_TOOLS as LEGACY_TOOLS
from inventory_display import build_condition as legacy_condition
from public_display import (ARMS, CODE_TOOLS, audit_access, build_condition,
                            capability_prompt, validate_matched_views, validate_plan)
from public_name_comparison import interface
from run_handoff_factors import ROOT, read
from run_public_display_comparison import cell_id, run_order
from stateful_code_prompts import stateful_system_prompt
import test_contract_retention_controls as fixtures
from test_public_name_catalog import TOOLS, Bridge, packet
from container_api_python import ApiChannel
from public_name_catalog import PublicNameCatalog


class PublicDisplayTests(unittest.TestCase):
    def fixture(self):
        item = fixtures.DetailControlTests().fixture()
        item['prefix']['conversation_private'][0]['content'] = stateful_system_prompt(
            read(ROOT / 'configs/P29_stateful_code_v01.json'))
        return item

    def test_all_arms_share_capability_and_leave_original_turns_and_sources_unchanged(self):
        item = self.fixture(); original = copy.deepcopy(item)
        old_tools = copy.deepcopy(LEGACY_TOOLS)
        systems = []
        for arm in ARMS:
            old = legacy_condition(item, arm)[0].messages()
            new, meta = build_condition(item, arm)
            messages = new.messages()
            self.assertEqual(old[1:], messages[1:])
            self.assertEqual(capability_prompt(old[0]['content']), messages[0]['content'])
            self.assertEqual(meta['catalog_policy'], 'public_names')
            systems.append(messages[0])
        self.assertEqual(systems[0], systems[1]); self.assertEqual(systems[1], systems[2])
        self.assertEqual(item, original); self.assertEqual(LEGACY_TOOLS, old_tools)
        self.assertIn('registered public simulated APIs', CODE_TOOLS[0]['function']['description'])

    def test_matched_detail_receipts_and_listing_control_survive_permission_change(self):
        checked = validate_matched_views(self.fixture())
        self.assertEqual(checked[ARMS[1]]['detail_receipt_ids'], ['i1', 'i3', 'i5'])
        self.assertEqual(checked[ARMS[1]]['detail_receipt_ids'], checked[ARMS[2]]['detail_receipt_ids'])
        self.assertEqual(checked[ARMS[2]]['listing_receipt_ids'], ['i0', 'i2', 'i4', 'i6'])

    def test_changed_capability_source_is_refused(self):
        item = self.fixture()
        item['prefix']['conversation_private'][0]['content'] = 'unexpected guide'
        with self.assertRaisesRegex(ValueError, 'capability wording'):
            build_condition(item, ARMS[0])

    def test_capability_and_tool_wording_match_previously_validated_p64_interface(self):
        config = read(ROOT / 'configs/P29_stateful_code_v01.json') | {'max_api_requests': 80}
        prompt, definitions = interface('named', config)
        self.assertEqual(definitions, CODE_TOOLS)
        self.assertEqual(prompt.split('\nTask limits are ')[0],
                         capability_prompt(stateful_system_prompt(config)))

    def test_fixed_plan_accepts_only_declared_cohort_and_limits(self):
        plan = read(ROOT / 'configs/P71_public_display_v01.json')
        validate_plan(plan)
        for change in ({'catalog_policy': 'documented'}, {'max_calls': 17},
                       {'source_runs': ['P29_01_CODE']}, {'reserved_scenarios_read': 1},
                       {'source_comparison_sha256': 'changed'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_plan({**plan, **change})

    def test_all_twelve_cells_have_unique_fixed_identity_and_order(self):
        order = run_order([{'task_id': n} for n in range(4)])
        self.assertEqual([arm for _, _, arm in order],
                         [*ARMS, ARMS[1], ARMS[2], ARMS[0], ARMS[2], ARMS[0], ARMS[1],
                          ARMS[0], ARMS[2], ARMS[1]])
        self.assertEqual(len({cell_id(n, arm) for n, _, arm in order}), 12)
        with self.assertRaises(ValueError): run_order([{}, {}, {}])

    def records(self, packets, *, fail=False):
        catalog = PublicNameCatalog(TOOLS); visible = sorted(catalog.visible)
        channel = ApiChannel(catalog, Bridge(fail=fail), 20)
        for request in packets: channel.exchange(request)
        events, spans = [], {}
        for number, row in enumerate(channel.rows):
            sid = f's{number}'
            spans[sid] = {'action': row['action'], 'observation': row['observation']}
            events.append({k: v for k, v in row.items() if k not in ('action', 'observation')}
                          | {'stage': 'python_api', 'span_id': sid})
        return events, spans, visible

    def test_actual_channel_receipts_allow_unexposed_registered_name_without_exposing_schema(self):
        events, spans, visible = self.records([packet()])
        result = audit_access(events, spans, TOOLS, visible)
        self.assertEqual(result['sent_before_documentation_exposure'], {'phone__get_current_date_and_time': 1})
        self.assertEqual(events[0]['new_tools'], [])
        self.assertEqual(result['sent_api_requests'], 1)

    def test_documentation_exposure_is_recomputed_and_subsequent_call_is_not_unexposed(self):
        events, spans, visible = self.records([
            packet(app='api_docs', api='show_api_doc',
                   arguments={'app_name': 'phone', 'api_name': 'get_current_date_and_time'}),
            packet(number=2)])
        self.assertEqual(audit_access(events, spans, TOOLS, visible)['sent_before_documentation_exposure'], {})
        events[0]['new_tools'] = []
        with self.assertRaisesRegex(ValueError, 'schema exposure'):
            audit_access(events, spans, TOOLS, visible)

    def test_unknown_name_and_unknown_argument_rejections_cannot_be_relabelled_as_sent(self):
        for request in (packet(app='admin', api='query'), packet(api='_private'),
                        packet(arguments={'unexpected': 3})):
            events, spans, visible = self.records([request])
            self.assertEqual(audit_access(events, spans, TOOLS, visible)['sent_api_requests'], 0)
            events[0]['api_request_sent'] = True
            with self.assertRaises(ValueError): audit_access(events, spans, TOOLS, visible)

    def test_legacy_discovery_gate_leak_is_detected(self):
        events, spans, visible = self.records([packet()])
        events[0]['api_request_sent'] = False
        spans['s0']['observation'] = {'format_error': 'API not in supplied public schema'}
        with self.assertRaisesRegex(ValueError, 'valid public-name'):
            audit_access(events, spans, TOOLS, visible)

    def test_completion_and_unknown_effects_stop_later_dispatch(self):
        for requests, fail in (([packet(app='supervisor', api='complete_task'), packet(number=2)], False),
                               ([packet(), packet(number=2)], True)):
            events, spans, visible = self.records(requests, fail=fail)
            self.assertEqual(audit_access(events, spans, TOOLS, visible)['sent_api_requests'], 1)
            events[1]['api_request_sent'] = True
            with self.assertRaises(ValueError): audit_access(events, spans, TOOLS, visible)

    def test_api_outside_python_channel_and_spurious_exposure_are_detected(self):
        events, spans, visible = self.records([packet()])
        changed = copy.deepcopy(events); changed[0]['stage'] = 'model_tool'
        with self.assertRaises(ValueError): audit_access(changed, spans, TOOLS, visible)
        changed = copy.deepcopy(events); changed[0]['new_tools'] = ['phone__get_current_date_and_time']
        with self.assertRaises(ValueError): audit_access(changed, spans, TOOLS, visible)


if __name__ == '__main__': unittest.main()

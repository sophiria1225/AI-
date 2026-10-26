"""Handwritten synthetic region tests; no saved task program or model calls."""
import builtins
import contextlib
from copy import deepcopy
from dataclasses import asdict
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from region_field_projection import (RegionProjectionRuntime, execute_region_projection,
                                    plan_region_projection)
from test_automatic_field_projection import setup as base_setup, song

SOURCE = '''import json
prefix_count = prefix_count + 1
library = call_api('spotify', 'show_song_library', access_token='synthetic-credential')
collected = {}
keys = sorted([number for number in incoming if number not in collected])
for key in keys:
    entry = call_api('spotify', 'show_song', song_id=key)
    collected[key] = {'label': entry['title'], 'people': [person['name'] for person in entry['artists']]}
print(json.dumps(collected, sort_keys=True))
print(','.join(['finished', 'synthetic']))
'''


def setup(observed=False):
    raw, budget, host, scope, old, stops = base_setup(observed=observed)
    runtime = RegionProjectionRuntime(old.fetch_full, old.lookup_fields, old.stop)
    scope.update(prefix_count=0, incoming=[2, 5, 9])
    return raw, budget, host, scope, runtime, stops


def run(source, scope, runtime, optimized=True):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        if optimized:
            result = execute_region_projection(asdict(plan_region_projection(source)), scope, runtime)
        else:
            exec(compile(source, '<synthetic-eager>', 'exec'), scope, scope)
            result = {'transformed': False}
    return out.getvalue(), result


class RegionProjectionTests(unittest.TestCase):
    def test_dynamic_prefix_once_normal_stdout_final_root_and_segment_hashes(self):
        results = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            output, report = run(SOURCE, scope, runtime, optimized)
            self.assertEqual(scope['prefix_count'], 1)
            self.assertEqual(sum(c['api'] == 'show_song_library' for c in raw.calls), 1)
            self.assertEqual(scope['entry'], song(9))
            self.assertEqual(type(scope['entry']), dict)
            self.assertEqual(scope['key'], 9)
            self.assertFalse(any(n.startswith('_harness_projection_') for n in scope))
            self.assertFalse(stops)
            results.append((output, scope['collected'], scope['entry']))
            if optimized:
                self.assertEqual((runtime.hits, budget.spent), (2, 2))
                self.assertTrue(report['regions'][0]['admitted'])
                self.assertTrue(all(s['completed'] for s in report['segments']))
                self.assertNotEqual(report['regions'][0]['original_sha256'], report['regions'][0]['executed_sha256'])
                self.assertFalse(report['assembly_artifact_is_executed_whole_source'])
            else:
                self.assertEqual(budget.spent, 4)
        self.assertEqual(results[0], results[1])

    def test_entry_guard_fallback_preserves_once_only_prefix_and_suffix(self):
        source = SOURCE.replace('keys = sorted([number for number in incoming if number not in collected])',
                                'keys = [0, 2, 5]')
        results = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            output, report = run(source, scope, runtime, optimized)
            self.assertEqual(scope['prefix_count'], 1)
            self.assertEqual(len(raw.calls), 4)
            self.assertEqual(runtime.hits, 0)
            self.assertFalse(stops)
            if optimized:
                self.assertFalse(report['regions'][0]['admitted'])
                self.assertEqual(report['regions'][0]['reason'], 'dynamic_iterable_domain_rejected')
                self.assertEqual(report['regions'][0]['original_sha256'], report['regions'][0]['executed_sha256'])
            results.append((output, scope['entry'], scope['collected']))
        self.assertEqual(results[0], results[1])

    def test_nonempty_plain_destination_is_supported(self):
        source = SOURCE.replace('collected = {}', "collected = {77: {'label': 'already', 'people': []}}")
        raw, budget, host, scope, runtime, stops = setup()
        _, info = run(source, scope, runtime)
        self.assertTrue(info['regions'][0]['admitted'])
        self.assertEqual(scope['collected'][77]['label'], 'already')
        self.assertEqual(runtime.hits, 2)

    def test_empty_singleton_duplicate_and_tuple_boundaries(self):
        for incoming in ([], [5], [2, 2, 9], (2, 5, 9)):
            with self.subTest(size=len(incoming)):
                outcomes = []
                source = SOURCE.replace('keys = sorted([number for number in incoming if number not in collected])',
                                        'keys = incoming')
                for optimized in (False, True):
                    raw, budget, host, scope, runtime, stops = setup()
                    scope['incoming'] = incoming
                    sentinel = {'previous': True}; scope.update(entry=sentinel, key='prior-loop-value')
                    output, report = run(source, scope, runtime, optimized)
                    self.assertEqual(scope['entry'], song(incoming[-1]) if incoming else sentinel)
                    self.assertEqual(scope['key'], incoming[-1] if incoming else 'prior-loop-value')
                    outcomes.append((output, scope['entry'], scope['collected']))
                    self.assertFalse(stops)
                self.assertEqual(outcomes[0], outcomes[1])
        raw, budget, host, scope, runtime, stops = setup()
        scope['incoming'] = []
        run(SOURCE, scope, runtime)
        self.assertNotIn('entry', scope); self.assertNotIn('key', scope)

    def test_more_than_512_runtime_items_falls_back_at_region(self):
        raw, budget, host, scope, runtime, stops = setup()
        scope['incoming'] = [2] * 513
        # Ordinary complete cache prevents a large backend budget in this synthetic case.
        _, info = run(SOURCE, scope, runtime)
        self.assertEqual(scope['prefix_count'], 1)
        self.assertFalse(info['regions'][0]['admitted'])
        self.assertEqual(runtime.hits, 0)
        self.assertEqual(scope['entry'], song(2))

    def test_referenced_custom_value_or_subclass_gets_original_program(self):
        class CustomList(list): pass
        raw, budget, host, scope, runtime, stops = setup()
        scope['incoming'] = CustomList([2, 5, 9])
        _, info = run(SOURCE, scope, runtime)
        self.assertFalse(info['transformed'])
        self.assertEqual(info['reason'], 'non_plain_referenced_namespace')
        self.assertEqual(scope['prefix_count'], 1)
        self.assertEqual((runtime.hits, budget.spent), (0, 4))

    def test_root_or_item_alias_to_iterator_falls_back_without_restarting(self):
        source = SOURCE.replace('for key in keys:', 'entry = keys\nfor key in keys:')
        raw, budget, host, scope, runtime, stops = setup()
        _, info = run(source, scope, runtime)
        self.assertEqual(scope['prefix_count'], 1)
        self.assertFalse(info['regions'][0]['admitted'])
        self.assertEqual(info['regions'][0]['reason'], 'overwritten_binding_alias')
        self.assertEqual(budget.spent, 4)

    def test_prior_root_alias_is_preserved_when_unrelated_to_destination(self):
        raw, budget, host, scope, runtime, stops = setup()
        old = {'previous': ['value']}; scope.update(entry=old, prior_alias=old)
        run(SOURCE, scope, runtime)
        self.assertIs(scope['prior_alias'], old)
        self.assertIsNot(scope['entry'], old)
        self.assertEqual(scope['entry'], song(9))

    def test_final_read_and_body_failures_are_sticky_only_after_partial(self):
        for kind in ('read', 'body', 'suffix'):
            raw, budget, host, scope, runtime, stops = setup()
            source = SOURCE
            if kind == 'read': raw.fail = 9
            elif kind == 'body': raw.bad_body = 9
            else: source += 'print(1 / 0)\n'
            with self.assertRaises(Exception): run(source, scope, runtime)
            self.assertEqual(scope['prefix_count'], 1)
            self.assertTrue(runtime.failed); self.assertTrue(budget.stopped)
            self.assertEqual(len(stops), 1)
            self.assertEqual([c['args'].get('song_id') for c in raw.calls], [None, 9])
            self.assertFalse(any(n.startswith('_harness_projection_') for n in scope))
            before = len(raw.calls)
            with self.assertRaisesRegex(RuntimeError, 'stopped'): run(SOURCE, scope, runtime)
            self.assertEqual(len(raw.calls), before)

    def test_prefix_exception_has_no_projection_stop_or_retry(self):
        source = SOURCE.replace('collected = {}', 'print(1 / 0)\ncollected = {}')
        raw, budget, host, scope, runtime, stops = setup()
        with self.assertRaises(ZeroDivisionError): run(source, scope, runtime)
        self.assertEqual(scope['prefix_count'], 1)
        self.assertEqual(len(raw.calls), 1)
        self.assertFalse(runtime.failed); self.assertFalse(stops)

    def test_miss_only_failure_remains_ordinary(self):
        source = SOURCE.replace("library = call_api('spotify', 'show_song_library', access_token='synthetic-credential')\n", '')
        raw, budget, host, scope, runtime, stops = setup()
        raw.fail = 9
        with self.assertRaises(Exception): run(source, scope, runtime)
        self.assertEqual(scope['entry'], song(5))
        self.assertFalse(runtime.failed); self.assertFalse(stops)
        self.assertEqual(runtime.hits, 0)

    def test_two_regions_second_fallback_never_repeats_first(self):
        second = '''more = [0, 2]
for second_key in more:
    second_entry = call_api('spotify', 'show_song', song_id=second_key)
    collected[second_key] = {'label': second_entry['title']}
'''
        raw, budget, host, scope, runtime, stops = setup()
        _, info = run(SOURCE + second, scope, runtime)
        self.assertEqual(scope['prefix_count'], 1)
        self.assertEqual([r['admitted'] for r in info['regions']], [True, False])
        self.assertEqual(runtime.hits, 2)
        self.assertEqual([c['args'].get('song_id') for c in raw.calls], [None, 9, 0, 2])

    def test_cache_shared_both_arms_and_skipped_full_values_not_invented(self):
        totals = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            first, _ = run(SOURCE, scope, runtime, optimized)
            second, _ = run(SOURCE, scope, runtime, optimized)
            self.assertEqual(first, second)
            self.assertEqual(scope['prefix_count'], 2)
            self.assertEqual(len(host.provider.cache.exact), 1 if optimized else 3)
            self.assertEqual(host.ordinary_complete_reuses, 1 if optimized else 3)
            totals.append(budget.spent)
        self.assertEqual(totals, [5, 3])

    def test_invalid_lookup_does_not_materialize_or_resume(self):
        raw, budget, host, scope, runtime, stops = setup()
        runtime.lookup_fields = lambda *args: {'title': 'synthetic_bad_shape'}
        with self.assertRaisesRegex(RuntimeError, 'contract_false'): run(SOURCE, scope, runtime)
        self.assertTrue(runtime.failed); self.assertTrue(stops)
        self.assertEqual(len(raw.calls), 1)

    def test_reflection_identity_escape_callbacks_and_future_are_static_fallback(self):
        cases = [SOURCE + 'print(globals())\n', SOURCE + 'print(entry is collected)\n',
            SOURCE + 'unknown_callback()\n', SOURCE + 'try:\n    pass\nexcept Exception:\n    pass\n',
            'from __future__ import annotations\n' + SOURCE, '"module documentation"\n' + SOURCE,
            SOURCE.replace("{'label': entry['title'], 'people': [person['name'] for person in entry['artists']]}", 'entry'),
            SOURCE.replace("[person['name'] for person in entry['artists']]", "entry['artists']"),
            SOURCE + 'json.dumps(collected, default=print)\n',
            SOURCE + 'alias = json\n', SOURCE + 'print(json)\n',
            SOURCE + 'json.dumps = print\n', SOURCE + 'import sys\n']
        for source in cases:
            self.assertFalse(plan_region_projection(source).eligible)

    def test_whole_source_compile_rejection_precedes_all_effects(self):
        for ending in ('break\n', 'continue\n'):
            raw, budget, host, scope, runtime, stops = setup()
            plan = plan_region_projection(SOURCE + ending)
            self.assertFalse(plan.eligible)
            with self.assertRaises(SyntaxError): run(SOURCE + ending, scope, runtime)
            self.assertEqual(scope['prefix_count'], 0)
            self.assertEqual(len(raw.calls), 0)

    def test_bounded_parser_size_depth_and_syntax(self):
        for source in ('x' * 20001, 'x = ' + '[' * 100 + '0' + ']' * 100,
                       'x = [' + ','.join(['1'] * 6000) + ']\n' + SOURCE, 'if :\n'):
            plan = plan_region_projection(source)
            self.assertFalse(plan.eligible)
            self.assertTrue('limit' in plan.reason or 'analysis_error' in plan.reason)

    def test_hash_tamper_and_json_monkeypatch_are_not_accepted(self):
        raw, budget, host, scope, runtime, stops = setup()
        plan = asdict(plan_region_projection(SOURCE)); plan['segments'][0]['source'] += '\nprint(123)'
        with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
            execute_region_projection(plan, scope, runtime)
        self.assertEqual(scope['prefix_count'], 0)
        old = json.JSONEncoder.default
        try:
            json.JSONEncoder.default = lambda self, value: None
            _, info = run(SOURCE, scope, runtime)
        finally:
            json.JSONEncoder.default = old
        self.assertFalse(info['transformed']); self.assertEqual(info['reason'], 'json_binding_changed')
        self.assertEqual(scope['prefix_count'], 1)

    def test_name_string_join_and_dictionary_methods_are_ordinary_prefix(self):
        source = SOURCE.replace('collected = {}', "separator = ','\nprint(separator.join(['one', 'two']))\nlookup = {'x': 1}\nprint(lookup.get('x'))\ncollected = {}")
        raw, budget, host, scope, runtime, stops = setup()
        _, info = run(source, scope, runtime)
        self.assertTrue(info['transformed']); self.assertEqual(runtime.hits, 2)

    def test_json_instance_and_added_class_callbacks_force_original_source(self):
        for owner, name in ((json._default_encoder, 'encode'),
                            (json.JSONEncoder, '__getattribute__')):
            raw, budget, host, scope, runtime, stops = setup()
            original = getattr(owner, name)
            try:
                setattr(owner, name, original)
                _, info = run(SOURCE, scope, runtime)
            finally:
                delattr(owner, name)
            self.assertFalse(info['transformed'])
            self.assertEqual(info['reason'], 'json_binding_changed')
            self.assertEqual(scope['prefix_count'], 1)

    def test_planner_and_hash_validation_do_not_call_mutated_json_encoder(self):
        calls = []
        original = json.JSONEncoder.encode
        source = SOURCE.replace('print(json.dumps(collected, sort_keys=True))', 'print(collected)')
        source = source.replace("library = call_api('spotify', 'show_song_library', access_token='synthetic-credential')", 'library = []')
        def full(app, api, **args):
            return song(args['song_id'])
        runtime = RegionProjectionRuntime(full, lambda *args: None, lambda reason: None)
        scope = {'call_api': full, 'prefix_count': 0, 'incoming': [2, 5, 9]}
        def callback(self, value):
            calls.append(1)
            return original(self, value)
        try:
            json.JSONEncoder.encode = callback
            plan = plan_region_projection(source)
            self.assertTrue(plan.eligible)
            self.assertEqual(calls, [])
            with contextlib.redirect_stdout(io.StringIO()):
                info = execute_region_projection(plan, scope, runtime)
            self.assertFalse(info['transformed'])
            self.assertEqual(info['reason'], 'json_binding_changed')
            self.assertEqual(calls, [])
        finally:
            json.JSONEncoder.encode = original

    def test_planner_builtin_integrity_rejection_uses_captured_constructors(self):
        calls = []
        original = builtins.dict
        def replacement(*args, **kwargs):
            calls.append(1)
            raise AssertionError('mutated_dict_called')
        try:
            builtins.dict = replacement
            plan = plan_region_projection(SOURCE)
        finally:
            builtins.dict = original
        self.assertFalse(plan.eligible)
        self.assertEqual(plan.reason, 'builtin_module_changed')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()

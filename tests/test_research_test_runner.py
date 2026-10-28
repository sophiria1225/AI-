"""Pure/fake tests for six exact historical method wrappers; no experiment I/O."""
import io
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_research_tests as runner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.original_clock = SimpleNamespace(time=lambda: 9999999999.0,
                                              monotonic=lambda: 17.5, sleep=lambda _: None)
        self.driver = SimpleNamespace(time=self.original_clock)
        self.test_id = sorted(runner.HISTORICAL_CLOCKS)[0]

    def make_case(self, body, *, identity=None, setup=None, teardown=None):
        identifier = self.test_id if identity is None else identity
        class Synthetic(unittest.TestCase):
            def id(self): return identifier
            def setUp(self):
                if setup: setup()
            def tearDown(self):
                if teardown: teardown()
            def test_body(self): body()
        return Synthetic('test_body')

    def test_exact_six_ids_no_wildcard_or_new_phase(self):
        self.assertEqual(len(runner.HISTORICAL_CLOCKS), 6)
        expected = {f'test_threshold_object_driver_p{phase}.DriverTests.{method}'
                    for phase in (142, 143) for method in runner._METHODS}
        self.assertEqual(set(runner.HISTORICAL_CLOCKS), expected)
        for name in ('test_other', self.test_id + '_suffix', 'tests.' + self.test_id,
                     self.test_id.replace('p142', 'p144')):
            case = self.make_case(lambda: None, identity=name)
            method = case.test_body
            self.assertFalse(runner.bind_historical_clock(case))
            self.assertEqual(case.test_body, method)

    def test_only_method_clock_changes_preserving_id_object_and_monotonic(self):
        observations = []
        wall_function = time.time
        def body():
            observations.append(self.driver.time.time())
            self.assertEqual(self.driver.time.monotonic(), 17.5)
            self.assertIs(time.time, wall_function)
        outside = lambda: self.assertIs(self.driver.time, self.original_clock)
        case = self.make_case(body, setup=outside, teardown=outside)
        suite = unittest.TestSuite([case]); original_id = case.id()
        self.assertEqual(runner.prepare_suite(suite), [original_id])
        class Result(unittest.TestResult):
            def startTest(result, test):
                self.assertIs(test, case); self.assertEqual(test.id(), original_id)
                super().startTest(test)
        result = Result()
        with patch.object(runner.importlib, 'import_module', return_value=self.driver): suite.run(result)
        self.assertTrue(result.wasSuccessful()); self.assertEqual(result.testsRun, 1)
        self.assertEqual(observations, [runner.HISTORICAL_INSTANT])
        self.assertIs(self.driver.time, self.original_clock)

    def test_failures_errors_and_skips_keep_standard_outcomes_and_restore(self):
        for exception, bucket in ((AssertionError('synthetic failure'), 'failures'),
                                  (RuntimeError('synthetic error'), 'errors'),
                                  (unittest.SkipTest('preexisting skip'), 'skipped')):
            def body(): raise exception
            case = self.make_case(body); runner.bind_historical_clock(case)
            result = unittest.TestResult()
            with patch.object(runner.importlib, 'import_module', return_value=self.driver): case.run(result)
            self.assertEqual(result.testsRun, 1)
            self.assertEqual(len(getattr(result, bucket)), 1)
            self.assertIs(getattr(result, bucket)[0][0], case)
            self.assertIs(self.driver.time, self.original_clock)

    def test_debug_exception_propagates_and_restores(self):
        def body(): raise RuntimeError('not swallowed')
        case = self.make_case(body); runner.bind_historical_clock(case)
        with patch.object(runner.importlib, 'import_module', return_value=self.driver), self.assertRaisesRegex(RuntimeError, 'not swallowed'):
            case.debug()
        self.assertIs(self.driver.time, self.original_clock)

    def test_nested_suite_unlisted_case_untouched_and_rebinding_idempotent(self):
        seen = []
        listed = self.make_case(lambda: seen.append(self.driver.time.time()))
        other = self.make_case(lambda: seen.append(self.driver.time.time()), identity='different.Case.test_body')
        suite = unittest.TestSuite([unittest.TestSuite([listed]), other])
        self.assertEqual(runner.prepare_suite(suite), [self.test_id])
        first = listed.test_body
        self.assertEqual(runner.prepare_suite(suite), [self.test_id])
        self.assertIs(listed.test_body, first)
        result = unittest.TestResult()
        with patch.object(runner.importlib, 'import_module', return_value=self.driver): suite.run(result)
        self.assertEqual(seen, [runner.HISTORICAL_INSTANT, 9999999999.0])
        self.assertEqual(result.testsRun, 2); self.assertTrue(result.wasSuccessful())

    def test_runner_exit_status_follows_unittest_failure_without_skipping(self):
        for failure in (False, True):
            def body():
                if failure: raise AssertionError('expected fake failure')
            case = self.make_case(body, identity='different.Case.test_body')
            suite = unittest.TestSuite([case])
            with (patch.object(unittest.TestLoader, 'discover', return_value=suite),
                  patch.object(sys, 'stderr', io.StringIO())):
                self.assertEqual(runner.main(['--pattern', 'synthetic.py', '--verbosity', '0']), int(failure))


if __name__ == '__main__': unittest.main()

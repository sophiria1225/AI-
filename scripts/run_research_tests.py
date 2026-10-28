"""Run the original unittest IDs, pinning six historical wall-clock fixtures.

The frozen P142/P143 test bytes predate their experiment deadlines. Only their
six named method calls get a driver-local wall-clock proxy. The system clock,
other modules, monotonic timers, production commands and other tests are not
changed. This is test execution support, not an experiment launcher.
"""
import argparse
from datetime import datetime
from functools import wraps
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_INSTANT = datetime.fromisoformat('2026-10-28T00:00:00+00:00').timestamp()
_METHODS = (
    'test_bounded_worker_exit_receipt_captures_failure_and_timeout_no_retry',
    'test_idle_start_is_persisted_before_failed_wait_and_missing_cost_stays_unknown',
    'test_evaluation_start_is_persisted_before_call_and_timeout_wall_is_saved',
)
HISTORICAL_CLOCKS = {
    f'test_threshold_object_driver_p{phase}.DriverTests.{method}':
        (f'run_whole_task_threshold_object_p{phase}', HISTORICAL_INSTANT)
    for phase in (142, 143) for method in _METHODS
}


class FixedWallClock:
    """Delegate all clock operations except wall time to the original module."""
    def __init__(self, original, instant):
        self._original, self._instant = original, instant

    def time(self):
        return self._instant

    def __getattr__(self, name):
        return getattr(self._original, name)


def bind_historical_clock(case):
    """Keep the actual TestCase and ID; restrict the patch to its method call."""
    binding = HISTORICAL_CLOCKS.get(case.id())
    if binding is None:
        return False
    method_name = case._testMethodName
    method = getattr(case, method_name)
    if getattr(method, '_research_historical_clock', False):
        return True
    module_name, instant = binding

    @wraps(method)
    def fixed_method(*args, **kwargs):
        driver = importlib.import_module(module_name)
        with patch.object(driver, 'time', FixedWallClock(driver.time, instant)):
            return method(*args, **kwargs)

    fixed_method._research_historical_clock = True
    setattr(case, method_name, fixed_method)
    return True


def prepare_suite(suite):
    """Recursively adapt only exact allowlisted IDs without filtering any case."""
    bound = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            bound.extend(prepare_suite(item))
        elif bind_historical_clock(item):
            bound.append(item.id())
    return bound


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test_*.py')
    parser.add_argument('--verbosity', type=int, choices=(0, 1, 2), default=1)
    parser.add_argument('--failfast', action='store_true')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'scripts'))
    suite = unittest.TestLoader().discover(str(ROOT / 'tests'), pattern=args.pattern)
    bound = prepare_suite(suite)
    print(f'Test-only historical wall-clock bindings: {len(bound)} exact test IDs.', file=sys.stderr)
    result = unittest.TextTestRunner(verbosity=args.verbosity, failfast=args.failfast).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

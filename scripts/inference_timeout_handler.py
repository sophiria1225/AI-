"""Catch inference alarms in new worker entrypoints without changing old transports.

The existing adapters own each request's alarm, timeout and terminal recording.
A fresh worker must supply a handler: SIG_DFL otherwise terminates Python before
their exception/finally paths can record unknown usage and close task resources.
This context changes neither an inference payload nor its time/output budget.
"""
from contextlib import contextmanager
import signal


@contextmanager
def inference_timeout_handler():
    """Wrap a new main-thread worker dispatch, restoring its handler on exit.

    The worker owns the process alarm for this scope. This is not an outer wall
    timer and does not preserve an independently armed enclosing alarm.
    """
    def expired(*_):
        raise TimeoutError('local_inference_deadline')

    previous_handler = signal.signal(signal.SIGALRM, expired)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)

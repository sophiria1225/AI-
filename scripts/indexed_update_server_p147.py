"""P147 owned-server identity and finite lease, with the fixed recovery supervisor.

Limited copies of the historical live_identity/wait_idle entrypoints. Model
provenance, single idle slot and lease checks remain mandatory. This module
never starts, stops, repairs, attaches to, or retries a model process.
"""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

from inference_cache_control import require_idle
from model_provenance import check_live_model

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = 'scripts/serve_research_model_recovery.py'
SUPERVISOR_SHA256 = 'e2b95b612426a318821c6295be156122deaebbdda074c10fbd727f0502a82d68'
LEASE_SECONDS = 21600
PIPELINE = 'records/context_pilot/P147_pipeline_v01/status.json'


def read(path):
    return json.loads(Path(path).read_text())


def positive(value):
    return type(value) is int and value > 0


def finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def get(endpoint):
    with urllib.request.urlopen('http://127.0.0.1:8011' + endpoint, timeout=10) as response:
        return json.load(response)


def owned_lease(runtime, command, now, *, storage, source_plan, owner):
    """Authenticate the exact new supervisor, not an arbitrary renamed process."""
    storage = Path(storage).resolve()
    expected = ROOT / SUPERVISOR
    if (not expected.is_file() or expected.is_symlink()
            or hashlib.sha256(expected.read_bytes()).hexdigest() != SUPERVISOR_SHA256):
        raise ValueError('fixed recovery supervisor source differs')
    args = shlex.split(command)
    if len(args) != 14 or not Path(args[1]).is_absolute() or Path(args[1]) != expected:
        raise ValueError('exact recovery supervisor process path required')
    options = args[2:]
    keys = options[::2]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate supervisor option')
    flags = dict(zip(keys, options[1::2], strict=True))
    wanted = {'--storage-root': str(storage), '--selection': source_plan['model_selection'],
        '--ctx-size': str(source_plan['model']['num_ctx']), '--cache-type-k': 'q8_0',
        '--cache-type-v': 'q8_0', '--max-seconds': str(LEASE_SECONDS)}
    if flags != wanted:
        raise ValueError('fixed recovery supervisor options or lease differ')
    if (not positive(runtime.get('supervisor_pid')) or not positive(runtime.get('pid'))
            or runtime['pid'] == runtime['supervisor_pid']
            or type(owner) is not dict or owner.get('phase') != 'P147_pipeline'
            or owner.get('status') not in ('starting', 'preflight', 'probe', 'activation', 'batch')
            or owner.get('server_owned') is not True
            or type(owner.get('server_supervisor_pid')) is not int
            or owner['server_supervisor_pid'] != runtime['supervisor_pid']
            or owner.get('server_record_directory') != runtime.get('record_directory')):
        raise ValueError('P147 owned supervisor identity differs')
    if type(runtime.get('record_directory')) is not str:
        raise ValueError('owned server record path required')
    record = Path(runtime['record_directory'])
    if record.is_absolute() or '..' in record.parts or record.parts[:2] != ('records', 'p2_servers'):
        raise ValueError('owned server record path escapes storage')
    started = dt.datetime.fromisoformat(runtime['started_at'])
    if started.tzinfo is None or now.tzinfo is None or started > now:
        raise ValueError('timezone-aware nonfuture server start required')
    end = started + dt.timedelta(seconds=LEASE_SECONDS)
    return (end - now).total_seconds(), end.isoformat()


def live_identity(storage, source_plan, required_seconds):
    if not finite_positive(required_seconds):
        raise ValueError('finite positive required lease seconds')
    storage = Path(storage).resolve()
    runtime = read(storage / '.runtime/model_server.json')
    owner = read(storage / PIPELINE)
    command = subprocess.check_output(
        ['ps', '-p', str(runtime['supervisor_pid']), '-o', 'command='], text=True).strip()
    remaining, end = owned_lease(runtime, command, dt.datetime.now(dt.timezone.utc),
                                storage=storage, source_plan=source_plan, owner=owner)
    parent = subprocess.check_output(
        ['ps', '-p', str(runtime['pid']), '-o', 'ppid='], text=True).strip()
    if not parent.isascii() or not parent.isdigit() or int(parent) != runtime['supervisor_pid']:
        raise ValueError('model process is not the owned supervisor child')
    check_live_model(source_plan['model_selection'], runtime, get('/props'), root=storage,
                     expected_ctx=source_plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    require_idle(get('/slots'))
    # Read-only checks consume lease; count that time before accepting the call.
    remaining, end = owned_lease(runtime, command, dt.datetime.now(dt.timezone.utc),
                                storage=storage, source_plan=source_plan, owner=owner)
    if remaining < required_seconds:
        raise ValueError('not enough server lease for bounded calibration')
    return {k: runtime[k] for k in ('model_revision', 'runtime', 'started_at', 'pid', 'supervisor_pid', 'ctx_size')}, end


def wait_idle(storage, original, identity, timeout):
    if not finite_positive(timeout):
        raise ValueError('finite positive idle timeout required')
    started = time.monotonic()
    observations = 0
    while time.monotonic() - started < timeout:
        with urllib.request.urlopen(original['model']['base_url'] + '/slots',
                timeout=min(5, max(0.001, timeout - (time.monotonic() - started)))) as response:
            slots = json.load(response)
        observations += 1
        if len(slots) != 1 or type(slots[0].get('is_processing')) is not bool:
            raise ValueError('unexpected slot state')
        if slots[0]['is_processing'] is False:
            current, _ = live_identity(storage, original, 1)
            if current != identity:
                raise ValueError('runtime identity changed during recovery')
            return {'one_slot_idle': True, 'observations': observations,
                    'wall_seconds': time.monotonic() - started}
        time.sleep(min(0.5, max(0, timeout - (time.monotonic() - started))))
    raise TimeoutError('server failed to become idle; do not continue')

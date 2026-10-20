"""Run a bounded setup/check command and retain output, timing and exit status."""
import argparse
import datetime
import json
import os
import pathlib
import signal
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--timeout', type=int, default=300)
parser.add_argument('command', nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ['--'] else args.command
root = pathlib.Path(__file__).resolve().parents[1]
out = root / 'records' / 'commands'
out.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
name = stamp + '_' + args.name
record = {'name': name, 'command': command, 'cwd': str(pathlib.Path.cwd()),
          'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'timeout_seconds': args.timeout}
start = time.monotonic()
try:
    with (out / (name + '.log')).open('wb') as f:
        process = subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            record['exit_code'] = process.wait(timeout=args.timeout)
            record['timed_out'] = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            record.update(exit_code=process.returncode, timed_out=True)
except Exception as error:
    record.update(exit_code=None, error=repr(error))
record['elapsed_seconds'] = time.monotonic() - start
record['output_log'] = str((out / (name + '.log')).relative_to(root))
(out / (name + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(record, ensure_ascii=False))
raise SystemExit(0 if record.get('exit_code') == 0 else 1)

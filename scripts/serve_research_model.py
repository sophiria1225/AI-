"""Supervise one pinned local model, recording sampled memory and server status."""
import argparse
import datetime
import json
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import urllib.request

from model_provenance import LEGACY_SELECTION, verified_model

ROOT = Path(__file__).resolve().parents[1]


def poll_backend_error(path, offset=0, carry=''):
    """Catch fatal compute failures even when /health still returns ok."""
    with path.open('rb') as source:
        source.seek(offset)
        content = carry + source.read(1024 * 1024).decode('utf-8', errors='replace')
        position = source.tell()
    fatal = ('kIOGPUCommandBufferCallbackErrorOutOfMemory',
             'backend is in error state from a previous command buffer failure',
             'decode() failed: Compute error.')
    failure = next((line[:500] for line in content.splitlines()
                    if any(marker in line for marker in fatal)), None)
    return failure, position, content[-512:]


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def memory_sample(pid):
    rss = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], text=True, capture_output=True).stdout.strip()
    swap = subprocess.check_output(['sysctl', '-n', 'vm.swapusage'], text=True).strip()
    match = re.search(r'used\s*=\s*([0-9.]+)([MG])', swap)
    used = float(match[1]) * (1024**2 if match[2] == 'M' else 1024**3) if match else None
    vm = subprocess.check_output(['vm_stat'], text=True)
    page = int(re.search(r'page size of (\d+) bytes', vm)[1])
    fields = {name: int(value) for name, value in re.findall(r'^([^:\n]+):\s+(\d+)\.', vm, re.M)}
    return {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'rss_bytes': int(rss) * 1024 if rss else None, 'swap_used_bytes': used,
            'swap_raw': swap, 'system_wired_bytes': fields['Pages wired down'] * page,
            'system_compressor_bytes': fields['Pages occupied by compressor'] * page,
            'system_free_bytes': fields['Pages free'] * page,
            'vm_stat_raw': vm}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ctx-size', type=int, default=8192)
    parser.add_argument('--port', type=int, default=8011)
    parser.add_argument('--max-seconds', type=int, default=7200)
    parser.add_argument('--max-swap-growth-gib', type=float, default=8)
    parser.add_argument('--selection', default=LEGACY_SELECTION)
    parser.add_argument('--cache-type-k', choices=['f16', 'q8_0'], default='f16')
    parser.add_argument('--cache-type-v', choices=['f16', 'q8_0'], default='f16')
    args = parser.parse_args()
    selection, download, model = verified_model(args.selection)
    runtime = json.loads((ROOT / 'records/models/p2_runtime_install.json').read_text())
    if runtime['runtime'] != selection['runtime']:
        raise RuntimeError('runtime provenance mismatch')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', args.port))
    # Only read Ollama status; do not unload unrelated user models implicitly.
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        if json.load(response).get('models'):
            raise RuntimeError('another Ollama model is loaded; serialize large model experiments')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out = ROOT / 'records/p2_servers' / stamp
    out.mkdir(parents=True)
    (out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (out / 'model_provenance.py').write_bytes((ROOT / 'scripts/model_provenance.py').read_bytes())
    write_json(out / 'selection.json', selection)
    write_json(out / 'download_record.json', download)
    command = [str(ROOT / runtime['server_path']), '--model', str(model),
               '--alias', selection['model_alias'], '--host', '127.0.0.1', '--port', str(args.port),
               '--ctx-size', str(args.ctx_size), '--parallel', '1', '--n-gpu-layers', '999',
               '--flash-attn', 'on', '--batch-size', '256', '--ubatch-size', '128',
               '--cache-type-k', args.cache_type_k, '--cache-type-v', args.cache_type_v, '--cache-ram', '0',
               '--ctx-checkpoints', '1', '--jinja', '--reasoning-format', 'deepseek',
               '--no-context-shift', '--no-webui', '--log-timestamps']
    state = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'status': 'loading', 'command': command, 'ctx_size': args.ctx_size,
             'runtime': selection['runtime'], 'model_revision': selection['revision'],
             'selection': args.selection, 'model_alias': selection['model_alias'],
             'quantization': selection['quantization'],
             'cache_type_k': args.cache_type_k, 'cache_type_v': args.cache_type_v,
             'record_directory': str(out.relative_to(ROOT)),
             'memory_note': '5-second RSS samples and system swap; RSS is not total unified GPU allocation'}
    stop_requested = False

    def request_stop(signum, frame):
        nonlocal stop_requested
        stop_requested = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    with (out / 'server.log').open('w') as log, (out / 'memory.jsonl').open('w') as samples:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        state.update(pid=process.pid, supervisor_pid=__import__('os').getpid())
        write_json(ROOT / '.runtime/model_server.json', state)
        baseline = memory_sample(process.pid)
        state['baseline'] = baseline
        peak_rss = 0
        peak_swap = baseline['swap_used_bytes'] or 0
        was_ready = False
        log_offset, log_carry = 0, ''
        started = time.monotonic()
        try:
            while process.poll() is None:
                sample = memory_sample(process.pid)
                peak_rss = max(peak_rss, sample['rss_bytes'] or 0)
                peak_swap = max(peak_swap, sample['swap_used_bytes'] or 0)
                samples.write(json.dumps(sample) + '\n'); samples.flush()
                elapsed = time.monotonic() - started
                state.update(wall_seconds=elapsed, sampled_peak_rss_bytes=peak_rss,
                             peak_system_swap_bytes=peak_swap)
                failure, log_offset, log_carry = poll_backend_error(out / 'server.log', log_offset, log_carry)
                if failure:
                    state.update(status='failed', stop_reason='backend_compute_error', backend_error=failure)
                    write_json(out / 'summary.json', state)
                    write_json(ROOT / '.runtime/model_server.json', state)
                    break
                if state['status'] == 'loading':
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health', timeout=1) as response:
                            healthy = json.load(response).get('status') == 'ok'
                        if healthy:
                            was_ready = True
                            state.update(status='ready', load_wall_seconds=elapsed)
                            print(json.dumps({'status': 'ready', 'seconds': elapsed, 'path': str(out)}), flush=True)
                    except Exception:
                        pass
                reason = None
                if stop_requested:
                    reason = 'requested_stop'
                elif elapsed > args.max_seconds:
                    reason = 'supervisor_time_limit'
                elif elapsed > 900 and state['status'] == 'loading':
                    reason = 'load_timeout'
                elif peak_swap - (baseline['swap_used_bytes'] or 0) > args.max_swap_growth_gib * 1024**3:
                    reason = 'swap_growth_guard'
                write_json(out / 'summary.json', state)
                write_json(ROOT / '.runtime/model_server.json', state)
                if reason:
                    state['stop_reason'] = reason
                    break
                time.sleep(5)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            state.update(status='stopped', exit_code=process.returncode,
                         wall_seconds=time.monotonic() - started,
                         sampled_peak_rss_bytes=peak_rss, peak_system_swap_bytes=peak_swap)
            state.setdefault('stop_reason', 'server_exit')
            write_json(out / 'summary.json', state)
            write_json(ROOT / '.runtime/model_server.json', state)
            print(json.dumps({'status': state['status'], 'reason': state['stop_reason'],
                              'exit_code': state['exit_code'], 'path': str(out)}), flush=True)
    return was_ready and state['stop_reason'] in ('requested_stop', 'supervisor_time_limit')


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)

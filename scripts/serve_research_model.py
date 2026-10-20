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

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def memory_sample(pid):
    rss = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], text=True, capture_output=True).stdout.strip()
    swap = subprocess.check_output(['sysctl', '-n', 'vm.swapusage'], text=True).strip()
    match = re.search(r'used\s*=\s*([0-9.]+)([MG])', swap)
    used = float(match[1]) * (1024**2 if match[2] == 'M' else 1024**3) if match else None
    return {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'rss_bytes': int(rss) * 1024 if rss else None, 'swap_used_bytes': used,
            'swap_raw': swap}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ctx-size', type=int, default=8192)
    parser.add_argument('--port', type=int, default=8011)
    parser.add_argument('--max-seconds', type=int, default=7200)
    parser.add_argument('--max-swap-growth-gib', type=float, default=8)
    args = parser.parse_args()
    download = json.loads((ROOT / 'records/models/p2_minimax_download.json').read_text())
    if download['status'] != 'verified':
        raise RuntimeError('download must pass every hash before loading')
    selection = json.loads((ROOT / 'configs/models/minimax_m3_selection.json').read_text())
    if download['manifest']['revision'] != selection['revision']:
        raise RuntimeError('model revision mismatch')
    model = ROOT / download['destination'] / download['manifest']['files'][0]['path']
    for entry in download['manifest']['files']:
        if (ROOT / download['destination'] / entry['path']).stat().st_size != entry['bytes']:
            raise RuntimeError('verified model file size changed')
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
    command = [str(ROOT / runtime['server_path']), '--model', str(model),
               '--alias', 'minimax-m3-q3kl', '--host', '127.0.0.1', '--port', str(args.port),
               '--ctx-size', str(args.ctx_size), '--parallel', '1', '--n-gpu-layers', '999',
               '--flash-attn', 'on', '--batch-size', '256', '--ubatch-size', '128',
               '--cache-type-k', 'f16', '--cache-type-v', 'f16', '--cache-ram', '0',
               '--ctx-checkpoints', '1', '--jinja', '--reasoning-format', 'deepseek',
               '--no-context-shift', '--no-webui', '--log-timestamps']
    state = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'status': 'loading', 'command': command, 'ctx_size': args.ctx_size,
             'runtime': selection['runtime'], 'model_revision': selection['revision'],
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
                if state['status'] == 'loading':
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health', timeout=1) as response:
                            healthy = json.load(response).get('status') == 'ok'
                        if healthy:
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


if __name__ == '__main__':
    main()

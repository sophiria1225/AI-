"""Render fixed P101 inputs with the already verified vocabulary-only binary."""
import os
from pathlib import Path
import signal
import subprocess
import time

from choice_context_replay import CASES, CHOICES, condition
from probe_prompt_identity import render_summary
from run_handoff_factors import read, sha
from run_context_comparison import write_json


def render_inputs(storage, root, plan, requests, folder, runtime, check_stop,
                  operations, save, deadline):
    build = read(root/'reports/P83_renderer_build.json')
    if (build['exit_code'] != 0 or runtime['runtime']['commit'] != build['runtime_commit']
            or sha(storage/build['renderer_relative']) != build['renderer_sha256']
            or sha(root/'scripts/render_fallback_chat.cpp') != build['source_cpp_sha256']):
        raise ValueError('pinned_vocabulary_renderer_or_runtime_changed')
    for name, expected in build['library_sha256'].items():
        if sha(storage/name) != expected:
            raise ValueError('pinned_renderer_library_changed')
    command = runtime['command']
    model = command[command.index('--model') + 1]
    rendered = {}
    for choice in CHOICES:
        check_stop(storage)
        out = folder/('render_' + choice); out.mkdir()
        cases = []
        for case in CASES:
            key = condition(case, choice)
            path = out/(key + '_request_private.json')
            write_json(path, requests[key])
            cases.append({'id':key, 'request_path':str(path)})
        manifest = out/'manifest_private.json'
        write_json(manifest,dict(recorded_server_command=command,model_path=model,
                               output_dir=str(out),cases=cases))
        row = dict(tool_choice=choice,status='starting',renderings=0,decode_calls=0,
                   sampled_peak_rss_bytes=0,manifest_sha256=sha(manifest))
        operations.append(row);save()
        began = time.monotonic(); process = None
        try:
            with (out/'renderer_private.log').open('w') as log:
                process = subprocess.Popen([str(storage/build['renderer_relative']),str(manifest)],
                    stdout=log,stderr=log,start_new_session=True)
            row.update(pid=process.pid,status='rendering');save()
            while process.poll() is None:
                check_stop(storage)
                if time.monotonic() >= min(deadline,began+plan['max_renderer_seconds']):
                    raise TimeoutError('bounded_vocabulary_renderer_deadline')
                sample = subprocess.run(['ps','-o','rss=','-p',str(process.pid)],
                    capture_output=True,text=True,timeout=10)
                if sample.returncode == 0 and sample.stdout.strip():
                    row['sampled_peak_rss_bytes'] = max(row['sampled_peak_rss_bytes'],int(sample.stdout.strip())*1024)
                    if row['sampled_peak_rss_bytes'] > plan['max_renderer_rss_bytes']:
                        raise MemoryError('bounded_vocabulary_renderer_RSS')
                time.sleep(.05)
            row['exit_code'] = process.returncode
            if process.returncode or read(out/'renderer_complete.json') != {'renderings':6,'decode_calls':0}:
                raise ValueError('complete_six_renderings_required')
            meta = read(out/'renderer_metadata_private.json')
            if (meta['vocabulary_only'] is not True or meta['inference_contexts_created'] != 0
                    or meta['decode_calls'] != 0):
                raise ValueError('vocabulary_only_renderer_required')
            row['metadata_sha256'] = sha(out/'renderer_metadata_private.json')
            for case in CASES:
                key = condition(case,choice); path=out/(key+'_rendered_private.json')
                if path.stat().st_size > 16777216: raise ValueError('bounded_rendered_file_required')
                rendered[key] = {**render_summary(read(path)), 'private_rendered_sha256':sha(path)}
            row.update(status='complete',renderings=6)
        except BaseException as error:
            row.update(status='stopped',error_type=type(error).__name__)
            raise
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
            row['wall_seconds'] = time.monotonic()-began;save()
    return rendered

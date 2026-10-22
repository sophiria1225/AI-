"""Separate, bounded streaming adapter; frozen non-stream experiments stay intact."""
import json
from pathlib import Path
import signal
import threading
import time
import urllib.parse
import urllib.request

from local_llama import payload_for, parse_response
from streaming_usage_receipt import CompletionReceipt, SSEDecoder, StreamProtocolError


class ProbeDisconnect(Exception):
    """Only for a predeclared calibration of incomplete receipts."""


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def stream_payload(config, messages, tools):
    payload = payload_for(config, messages, tools)
    payload.update(stream=True, stream_options={'include_usage':True},
                   timings_per_token=True, return_progress=True)
    return payload


def model_call_stream(config, messages, out, remaining_wall, tools,
                      *, stop_after_observed_tokens=None, opener=urllib.request.urlopen):
    """Persist partial counters, return executable message only on complete stream.

    EOF after valid terminal usage can preserve exact counts while quarantining
    the message. A disconnect never turns the last per-token count into a total.
    """
    base = config.get('base_url','http://127.0.0.1:8011').rstrip('/')
    url = urllib.parse.urlsplit(base)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('loopback HTTP required')
    if threading.current_thread() is not threading.main_thread():
        raise ValueError('absolute deadline requires the main thread')
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ValueError('do not replace another active deadline')
    if (stop_after_observed_tokens is not None and
            (type(stop_after_observed_tokens) is not int or stop_after_observed_tokens < 1)):
        raise ValueError('invalid calibration disconnect bound')
    timeout = min(float(config['call_timeout_seconds']), float(remaining_wall))
    if not 0 < timeout <= 600:
        raise ValueError('invalid finite request deadline')
    fingerprint = config['expected_system_fingerprint']
    if type(fingerprint) is not str or not fingerprint:
        raise ValueError('pinned server fingerprint required')
    out = Path(out)
    if any((out/name).exists() for name in ('request.json','response.json','wire_private.sse','progress.json')):
        raise FileExistsError('preserve previous request')
    out.mkdir(parents=True,exist_ok=True)
    payload = stream_payload(config,messages,tools)
    save(out/'request.json',payload)
    decoder, receipt = SSEDecoder(), CompletionReceipt()
    result = {'status':'error','input_tokens':None,'output_tokens':None,
        'message':{'role':'assistant','content':''},'backend':'llama.cpp',
        'timeout_seconds':timeout,'timeout_scope':'run_wall' if remaining_wall <= config['call_timeout_seconds'] else 'call',
        'error_kind':None,'partial_message_executed':False,'automatic_retries':0}
    started=time.monotonic()
    previous_handler=signal.getsignal(signal.SIGALRM)
    def expire(signum,frame):
        raise TimeoutError('absolute streaming deadline')
    signal.signal(signal.SIGALRM,expire)
    signal.setitimer(signal.ITIMER_REAL,timeout)
    try:
        request=urllib.request.Request(base+'/v1/chat/completions',
            data=json.dumps(payload,allow_nan=False).encode(),headers={'Content-Type':'application/json'})
        with opener(request,timeout=timeout) as response, (out/'wire_private.sse').open('xb') as wire:
            if not response.headers.get('Content-Type','').lower().startswith('text/event-stream'):
                raise StreamProtocolError('event_stream_required')
            while not receipt.done:
                chunk=response.read1(4096)
                if not chunk:
                    decoder.finish()
                    raise StreamProtocolError('stream_ended_before_done')
                wire.write(chunk);wire.flush()
                for event in decoder.feed(chunk):
                    receipt.consume(event)
                    if receipt.identity is not None and receipt.identity[2] != fingerprint:
                        receipt.valid=False
                        raise StreamProtocolError('server_fingerprint_changed')
                    save(out/'progress.json',receipt.summary())
                    if (stop_after_observed_tokens is not None and not receipt.done
                            and receipt.output_lower_bound >= stop_after_observed_tokens):
                        raise ProbeDisconnect('predeclared receipt-disconnect probe')
                    if receipt.done:
                        break
            raw=receipt.final_response()
            save(out/'raw_response.json',raw)
            result.update(parse_response(raw))
    except ProbeDisconnect:
        result['error_kind']='intentional_probe_disconnect'
    except Exception as exc:
        result['error_kind']='timeout' if (isinstance(exc,TimeoutError)
            or isinstance(getattr(exc,'reason',None),TimeoutError)) else 'request_or_stream'
        result['error_type']=type(exc).__name__
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous_handler)
        result['wall_seconds']=time.monotonic()-started
        result['stream_receipt']=receipt.summary()
        if receipt.summary()['terminal_usage_received']:
            result['input_tokens']=receipt.usage['prompt_tokens']
            result['output_tokens']=receipt.usage['completion_tokens']
        save(out/'progress.json',receipt.summary())
        save(out/'response.json',result)
    return result

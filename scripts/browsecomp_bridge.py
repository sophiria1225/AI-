"""Persistent corpus-only JSONL service; heavy imports never write to protocol stdout."""
import argparse
import json
import os
import sys
import time

from browsecomp_tools import CorpusTools, LuceneBackend

MAX_REQUEST_BYTES = 16384


def serve(backend, source, destination):
    tools = CorpusTools(backend)
    destination.write(json.dumps({'type': 'ready', 'protocol': 1,
                                  'corpus_documents': backend.num_docs}) + '\n')
    destination.flush()
    while True:
        raw = source.readline(MAX_REQUEST_BYTES + 1)
        if not raw:
            return
        # Reject the whole connection on an oversized or incomplete frame. Do not
        # interpret its suffix as a second request.
        if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b'\n'):
            raise ValueError('invalid protocol frame size')
        value = json.loads(raw)
        if (not isinstance(value, dict) or type(value.get('id')) is not int
                or value['id'] < 1):
            raise ValueError('invalid protocol request identity')
        if value.get('op') == 'close' and set(value) == {'id', 'op'}:
            destination.write(json.dumps({'id': value['id'], 'ok': True, 'closed': True}) + '\n')
            destination.flush()
            return
        if set(value) != {'id', 'op', 'name', 'arguments'} or value['op'] != 'tool':
            raise ValueError('unsupported protocol operation')
        started = time.monotonic()
        try:
            result = tools.dispatch(value['name'], value['arguments'])
            response = {'id': value['id'], 'ok': True, 'result': result}
        except Exception as error:
            # A failed backend is not an empty search result. Detailed errors stay
            # on private stderr; the controller stops instead of silently retrying.
            print(repr(error), file=sys.stderr, flush=True)
            response = {'id': value['id'], 'ok': False, 'error_type': type(error).__name__}
        response.update(requests=tools.requests, wall_seconds=time.monotonic() - started)
        destination.write(json.dumps(response, ensure_ascii=False) + '\n')
        destination.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', required=True)
    args = parser.parse_args()
    # Native JVM/Python dependencies may print to fd 1, not just sys.stdout.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    try:
        serve(LuceneBackend(args.index), sys.stdin.buffer, protocol)
    finally:
        protocol.close()


if __name__ == '__main__':
    main()

"""After timed prerequisites, check real tools and exact first-input counts, no generation."""
import argparse
import datetime
import json
from pathlib import Path
import urllib.request

from browsecomp_client import CorpusClient
from browsecomp_terminal import digest, exclusive_json
from browsecomp_tools import TOOLS
from local_llama import count_input, payload_for
from model_provenance import check_live_model
from native_conversation import NativeConversation
from run_browsecomp_baseline import SOURCES, SYSTEM_PROMPT, read_question

ROOT = Path(__file__).resolve().parents[1]


def preflight(plan, plan_path, storage, private):
    prior = json.loads((storage / 'records/context_pilot/P14_batch_v01/status.json').read_text())
    if prior['status'] != 'complete':
        raise ValueError('wait for all timed P14 runs before starting the actual retriever')
    private.mkdir(parents=True, exist_ok=False)
    runtime = json.loads((storage / '.runtime/model_server.json').read_text())
    with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(plan['model_selection'], runtime, props, root=storage,
                     expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    client = CorpusClient(storage / plan['retriever_python'], storage / plan['index_path'],
                          storage / plan['java_home'], private / 'bridge.stderr')
    try:
        found = client.request('search', {'query': 'theory of evolution', 'top_k': 3})['result']
        if found['status'] != 'ok' or [r['docid'] for r in found['results']] != ['68688', '29200', '91225']:
            raise ValueError('generic search differs from the installed-index check')
        top = found['results'][0]
        opened = client.request('get_document', {'docid': top['docid'], 'length': 2048})['result']
        if opened != {k: v for k, v in top.items() if k != 'score'}:
            raise ValueError('search excerpt and document retrieval disagree')
        absent = client.request('get_document', {'docid': '99999999999999999999'})['result']
        invalid = client.request('get_document', {'docid': '../qa/answer'})['result']
        if absent['status'] != 'not_found' or invalid['status'] != 'invalid_arguments':
            raise ValueError('document boundary controls failed')
        controls = {'corpus_documents': client.ready['corpus_documents'],
                    'generic_search_ids': [r['docid'] for r in found['results']],
                    'search_and_open_match': True, 'absent_id': absent['status'],
                    'path_request': invalid['status'], 'requests': client.sequence,
                    'startup_seconds': client.startup_seconds}
    finally:
        client.close()
    rows = []
    cfg = dict(plan['model'], temperature=plan['agent_temperature'], seed=plan['seed'],
               num_predict=plan['max_output_tokens'])
    for query_id in plan['run_ids']:
        task = read_question(storage / '.runtime/browsecomp/executor/development_questions_v01.jsonl',
                             plan['questions_sha256'], plan['selected_ids'], query_id)
        messages = NativeConversation(SYSTEM_PROMPT, task).messages()
        record = private / (query_id + '_request.json')
        exclusive_json(record, payload_for(cfg, messages, TOOLS))
        count = count_input(cfg, messages, TOOLS)['input_tokens']
        fits = count + plan['max_output_tokens'] <= cfg['num_ctx']
        if not fits:
            raise ValueError('initial query and tools exceed context budget')
        rows.append({'query_id': query_id, 'input_tokens': count, 'fits_context': fits,
                     'request_sha256': digest(record)})
    return {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'plan_sha256': digest(plan_path), 'controls': controls, 'initial_inputs': rows,
            'source_hashes': {'scripts/' + name: digest(ROOT / 'scripts' / name) for name in
                              SOURCES + ['preflight_browsecomp_execution.py', 'run_browsecomp_batch.py']},
            'model_generations': 0, 'answer_or_evidence_labels_read': False,
            'scope': 'Actual retriever controls and initial token counting, not answer accuracy.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError('keep prior preflight')
    result = preflight(json.loads(args.plan.read_text()), args.plan, args.storage_root.resolve(),
                       args.private_output)
    exclusive_json(args.report, result)
    print(json.dumps(result))

"""Evaluator-only projection, gated on sealed completion of the entire generation batch."""
import argparse
import json
from pathlib import Path

from browsecomp_terminal import digest, exclusive_json, load_terminal
from prepare_browsecomp_questions import column_rows, decrypt_question, public_canary


def terminal_inputs(batch, trials_root):
    if batch['status'] != 'generation_complete_evaluation_pending':
        raise ValueError('all selected generation must finish before opening answer labels')
    plan = batch['plan']
    run_ids = list(plan['run_ids'].values())
    if batch['completed'] != run_ids:
        raise ValueError('generation cohort incomplete or changed')
    selected, unsubmitted = {}, []
    for query_id, run_id in plan['run_ids'].items():
        trial = trials_root / run_id
        if digest(trial / 'terminal_manifest.json') != batch['terminal_manifest_sha256'][run_id]:
            raise ValueError('terminal seal differs from the batch selection')
        summary, answer = load_terminal(trial)
        if summary['query_id'] != query_id:
            raise ValueError('generation task identity changed')
        if not summary['submitted']:
            unsubmitted.append(run_id)
            continue
        question = json.loads((trial / 'question_private.json').read_text())
        if set(question) != {'query_id', 'query'} or question['query_id'] != query_id:
            raise ValueError('invalid original question projection')
        selected[query_id] = {'run_id': run_id, 'question': question['query'],
                              'response': answer['response'],
                              'final_answer_sha256': summary['final_answer_sha256'],
                              'terminal_manifest_sha256': digest(trial / 'terminal_manifest.json')}
    return selected, unsubmitted


def project_labels(rows, selected, canary):
    found, encrypted_rows = {}, 0
    for row in rows:
        encrypted_rows += 1
        if set(row) != {'query_id', 'query', 'answer'}:
            raise ValueError('answer-only projection contains unexpected columns')
        query_id = row['query_id']
        if query_id not in selected:
            continue
        if query_id in found:
            raise ValueError('duplicate answer row')
        question = decrypt_question(row['query'], canary)
        if question != selected[query_id]['question']:
            raise ValueError('evaluation question differs from generation')
        answer = decrypt_question(row['answer'], canary)
        if not answer.strip():
            raise ValueError('empty official answer')
        found[query_id] = {'query_id': query_id, **selected[query_id], 'answer': answer}
    if set(found) != set(selected):
        raise ValueError('missing selected answer')
    return [found[key] for key in selected], encrypted_rows


def prepare(storage, batch_folder, output, report):
    if not output.resolve().is_relative_to((storage / 'private_eval/browsecomp').resolve()):
        raise ValueError('grading input must stay in the evaluator-only local directory')
    if output.exists() or report.exists():
        raise FileExistsError('preserve previous grading preparation')
    state = json.loads((batch_folder / 'status.json').read_text())
    state['plan'] = json.loads((batch_folder / 'plan.json').read_text())
    # This gate occurs before imports/readers can open a QA answer column.
    selected, unsubmitted = terminal_inputs(state, storage / 'records/browsecomp_pilot')
    rows, encrypted = [], 0
    if selected:
        source = storage / 'records/sources/20261021_browsecomp_preflight_v02'
        canary = public_canary(source / 'scripts_build_index__decrypt_dataset.py',
                              'd25c7565ee7c1d9c8ec37f610b1f67756db8f8924ac6b8175ffff6d261a0e32d')
        download_path = storage / 'records/browsecomp_setup/qa_download_v01.json'
        download = json.loads(download_path.read_text())
        if download['revision'] != '144cff8e35b5eaef7e526346aa60774a9deb941f':
            raise ValueError('wrong answer source revision')
        rows, encrypted = project_labels(column_rows(storage / '.runtime/browsecomp/source/qa',
            download, ['query_id', 'query', 'answer']), selected, canary)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    with output.open('x', encoding='utf-8') as stream:
        output.chmod(0o600)
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    result = {'batch': batch_folder.name, 'submitted_rows': len(rows),
              'unsubmitted_runs': unsubmitted, 'encrypted_projection_rows_read': encrypted,
              'answers_decrypted': len(rows), 'evidence_or_gold_document_columns_read': False,
              'grading_input_sha256': digest(output), 'batch_plan_sha256': digest(batch_folder / 'plan.json'),
              'terminal_manifests': state['terminal_manifest_sha256'], 'model_calls': 0,
              'scope': 'Private answer-only projection after generation. Citation-label metrics remain uncomputed.'}
    exclusive_json(report, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--batch-folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.storage_root.resolve(), args.batch_folder, args.output, args.report)))

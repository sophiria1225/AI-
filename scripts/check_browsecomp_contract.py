"""Validate the pinned grading parser on synthetic cases, never benchmark answers."""
import argparse
import json
from pathlib import Path

from browsecomp_judge_contract import official_contract, SOURCE_SHA256, SAMPLING


def check(source):
    contract = official_contract(source)
    parse = contract['parse_judge_response']
    cases = [
        ('extracted_final_answer: SyntheticA\nreasoning: same\ncorrect: yes\nconfidence: 75%', True, False),
        ('**extracted_final_answer:** SyntheticB\n**correct:** no\n**confidence:** 80', False, False),
        ('A malformed judgment without the required decision', None, True),
        ('', None, True),
    ]
    for text, correct, parse_error in cases:
        result = parse(text)
        if result['correct'] is not correct or result['parse_error'] is not parse_error:
            raise AssertionError('official parser synthetic case failed')
    citations = contract['extract_citations_from_response']('Synthetic [7] [8, 9] [7]')
    if set(citations) != {'7', '8', '9'}:
        raise AssertionError('citation syntax differs')
    metrics = contract['compute_citation_metrics'](citations, ['7', '8'])
    if metrics['recall'] != 1 or abs(metrics['precision'] - 2 / 3) > 1e-9:
        raise AssertionError('citation metrics differ')
    prompt = contract['create_judge_prompt']('Synthetic {question}', 'Synthetic {response}', 'Synthetic {answer}')
    if not all(value in prompt for value in ('Synthetic {question}', 'Synthetic {response}', 'Synthetic {answer}')):
        raise AssertionError('template placeholders were not preserved as data')
    return {'official_source_sha256': SOURCE_SHA256, 'synthetic_parser_cases_passed': 4,
            'citation_and_prompt_checks_passed': True, 'sampling': SAMPLING,
            'benchmark_answers_read': 0, 'model_generations': 0,
            'scope': 'Parser and template integration only; no grading accuracy measurement.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.source)
    with args.report.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))

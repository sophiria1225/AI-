"""Preserve P99's first draft and clarify its one missing-usage observation.

Presentation only: all eight conditions were evaluated, so generic language
about missing evaluations is narrowed. Numerical tables and decisions stay fixed.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json

SOURCE = 'papers/202610_letter/tool_choice_observed'
TARGET = 'papers/202610_letter/tool_choice_observed_v02'


def clarify(root=ROOT):
    old, new = root / SOURCE, root / TARGET
    report = read(root / 'reports/P99_comparison.json')
    manifest = read(old / 'build_manifest.json')
    if (new.exists() or report['batch_status'] != 'complete' or report['audit_errors']
            or len(report['rows']) != 8 or report['development_gate_met'] is not False
            or any(r['record_status'] != 'evaluated' for r in report['rows'])
            or sum(r['unknown_usage_calls'] for r in report['rows']) != 1
            or any(sum(r['success'] for r in report['rows'] if r['tool_choice_policy'] == p) != 3
                   for p in ('auto', 'required'))):
        raise ValueError('exact_closed_P99_result_and_fresh_presentation_required')
    for name, expected in manifest['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('original_source_changed:' + name)
    for name, expected in manifest['generated_sha256'].items():
        if sha(old / name) != expected:
            raise ValueError('original_generated_source_changed:' + name)
    ja = ('状態保持型LLMエージェントの通常ツール提出設定を既知４課題８条件で比較した. '
          '全８条件を評価し，両設定とも３課題が成功した. 使用量不明の１生成が残り，全仕事費用差は未確定である.')
    en = ('We compared ordinary tool-choice settings across eight evaluated conditions on four known tasks. '
          'Both settings succeeded on three tasks. One generation had unknown token usage, preventing an '
          'exact whole-task cost comparison. General quality preservation remains untested.')
    assert len(ja) <= 120 and len(en.split()) <= 50
    contents = {name: (old / name).read_text() for name in manifest['generated_sha256']}
    text = contents['draft.tex']
    old_ja = text.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    old_en = text.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    contents['draft.tex'] = text.replace(old_ja, ja, 1).replace(old_en, en, 1).replace(SOURCE + '/', TARGET + '/')
    replacements = {
        'whole_task.tex': ('欠測または未評価があるため，固定した全件比較の費用差は未確定とする．',
            '全８条件を評価したが，Aの１生成で終端使用量が不明なため，全件の正確な費用差は未確定とする．'),
        'conclusion.tex': ('使用量の欠測または未評価・未実行を含む全８枠を保持した．',
            '全８条件を評価し，両設定とも３課題が成功した．Aの１生成の使用量不明を保持した．')}
    for name, (before, after) in replacements.items():
        if contents[name].count(before) != 1:
            raise ValueError('expected_presentation_sentence_missing:' + name)
        contents[name] = contents[name].replace(before, after, 1)
    assert contents['submission.tex'] == (old / 'submission.tex').read_text()
    assert contents['resources.tex'] == (old / 'resources.tex').read_text()
    new.mkdir()
    for name, text in contents.items():
        with (new / name).open('x') as stream:
            stream.write(text)
    out = {k: v for k, v in manifest.items() if k not in
           ('pdf_sha256', 'renderer_sha256', 'pages', 'body_pages', 'visual_reviewed')}
    out.update(generated_at=datetime.now(timezone.utc).isoformat(), visual_reviewed=False,
        source_sha256={**manifest['source_sha256'],
            **{SOURCE + '/' + name: sha(old / name) for name in manifest['generated_sha256']},
            SOURCE + '/build_manifest.json': sha(old / 'build_manifest.json'),
            'scripts/clarify_tool_choice_observed.py': sha(Path(__file__))},
        generated_sha256={name: sha(new / name) for name in contents},
        preserved_original_pdf_sha256=sha(old / 'draft.pdf'),
        presentation_revision='Clarify eight evaluated conditions and exactly one unknown-usage generation.',
        numerical_tables_and_original_gate_unchanged=True,
        ja_abstract_characters=len(ja), en_summary_words=len(en.split()))
    write_json(new / 'build_manifest.json', out)
    print(json.dumps({'folder': TARGET, 'ja_characters': len(ja), 'en_words': len(en.split()),
        'original_pdf_preserved': True, 'new_model_or_API_calls': 0}))


if __name__ == '__main__':
    clarify()

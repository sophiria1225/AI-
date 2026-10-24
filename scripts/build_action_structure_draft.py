"""Create a fresh edition distinguishing public equality from tool submission."""
from datetime import datetime, timezone
import json

from build_observed_control_draft import replace_once
from run_handoff_factors import ROOT, read, sha

PARENT = 'papers/202610_letter/closed_results_final'
FOLDER = 'papers/202610_letter/closed_results_action_structure'
REPORT = 'reports/P93_public_action_structure.json'


def build():
    target = ROOT / FOLDER
    if target.exists():
        raise FileExistsError('preserve_action_structure_edition')
    parent = ROOT / PARENT
    old = read(parent / 'build_manifest.json')
    sources = dict(old['source_sha256'])
    for name, expected in old['generated_sha256'].items():
        sources[PARENT + '/' + name] = expected
    report = read(ROOT / REPORT)
    if (report['status'] != 'complete' or len(report['rows']) != 18
            or report['original_known_logical_tokens'] != 422475
            or report['original_unknown_usage_calls'] != 0
            or not report['original_public_comparisons_preserved']
            or report['semantic_equivalence_established']
            or report['task_quality_measured'] or report['novel_method_claim']):
        raise ValueError('closed_P93_all_eighteen_required')
    rows = report['rows']
    if (sum(r['structure']['tool_calls'] for r in rows) != 12
            or sum(r['structure']['Python_ASTs_valid'] for r in rows) != 12
            or sum(r['structure']['interface_shapes_valid'] for r in rows) != 12
            or sum(r['structure']['content_characters'] == 2152 for r in rows) != 6):
        raise ValueError('fixed_P93_structure_required')
    contrasts = {(p['left'], p['right']): p for p in report['comparison']['cross']}
    ab = contrasts['P83_P80_ORIGINAL', 'P83_R2_ORIGINAL']
    cd = contrasts['P83_P80_NORMALIZED', 'P83_R2_NORMALIZED']
    an = contrasts['P83_P80_ORIGINAL', 'P83_NATIVE_IDS_CONTROL']
    if (len(contrasts) != 15 or ab['json_actions']['different'] != 9
            or ab['syntax_actions']['different'] != 9
            or cd['public_output']['equal'] != 9
            or cd['both_without_structured_calls'] != 9
            or cd['syntax_actions']['comparable'] != 0
            or an['syntax_actions']['equal'] != 9):
        raise ValueError('fixed_P93_comparisons_required')
    for name in (REPORT, 'configs/P93_public_action_structure_v01.json',
                 'docs/experiments/P93_public_action_structure.md',
                 'scripts/build_action_structure_draft.py',
                 'scripts/public_action_structure.py',
                 'scripts/inspect_fallback_action_structure.py',
                 PARENT + '/build_manifest.json', PARENT + '/draft.pdf',
                 PARENT + '/visual_review.json'):
        sources[name] = sha(ROOT / name)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('bound_source_changed:' + name)
    generated = {name: (parent / name).read_text() for name in old['generated_sha256']}
    source = generated['draft.tex'].replace(PARENT + '/', FOLDER + '/')
    source = replace_once(source,
        '状態保持型LLMエージェントの通知と参照表現を評価した. 既知４課題24条件で後半通知の全仕事費用改善は示せなかった. １保存文脈で参照ID差に伴う次出力差を確認した.',
        '状態保持型LLMエージェントの通知と参照表現を評価した. 既知４課題24条件で後半通知の全仕事費用改善は示せなかった. １保存文脈でID差に伴うコード構文差を確認したが，統一入力の同一出力はツール提出を伴わなかった.')
    source = replace_once(source,
        'We evaluated notices and references in stateful LLM agents. Late notices did not demonstrate whole-task cost improvement across 24 conditions on four known tasks. Reference-ID variants produced different next outputs in one saved context. These observations do not establish general quality preservation.',
        'We evaluated notices and references in stateful LLM agents. Late notices did not demonstrate whole-task cost improvement across 24 conditions. Reference-ID variants produced different code syntax in one saved context. Canonicalized inputs yielded identical text without tool submissions. Output agreement alone does not establish execution repair or task quality.')
    generated['draft.tex'] = source
    table = generated['local_replay.tex'].split('\\end{table}', 1)[0] + '\\end{table}\n'
    generated['local_replay.tex'] = table + (
        '公開出力はA/Bで0/9対，C/DとA/Nで各9/9対が一致した．'
        '全18生成は既知422,475論理token，使用量不明０で，推論器稼働は4,386.052秒だった．'
        '全15入力間比較と返却messageの不透明hashを保持し，内部推論の意味内容は読まない．\n'
        '終了後の構造点検では，A/Bの差はJSON整形とコード位置情報を除いてもASTに残った．'
        'Aにはログインと曲・アルバム・プレイリスト一覧取得，Bにはログインと曲一覧取得の構文があった．'
        'これらは実行回数ではない．A/B/N/Xの12件は引数形式とPython構文の検査を通ったが，'
        'C/Dの６件は本文だけで構造化されたツール提出がなく，有効な操作の一致とは数えない．'
        '値・名前・文順は保持し，追加生成・コード実行・API・評価なしで全18件を点検した．'
        '出力の一致を実行の修復や課題品質へ読み替えない．\n')
    generated['conclusion.tex'] = (
        '後半通知は全４採用基準未達で，全仕事費用の改善として採用しない．'
        '１保存文脈の元ID一対ではコード構文が異なり，統一入力の一致出力はツール提出を伴わなかった．'
        '通知・参照の整合を課題成功へ読み替えず，未達と欠測を残す．'
        '既知４課題と１保存文脈から，一般的な品質維持や新規手法の有効性は結論できない．\n')
    target.mkdir(parents=True, exist_ok=False)
    for name, content in generated.items():
        (target / name).write_text(content)
    manifest = {**old, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sources, 'generated_sha256': {n: sha(target / n) for n in generated},
        'parent_draft': PARENT, 'P93_structure_inspection_included': True,
        'P93_inspected_outputs': 18, 'P93_structured_submissions': 12,
        'P93_text_only_outputs': 6, 'P93_saved_code_executions': 0,
        'visual_reviewed': False, 'submission_ready': False}
    for key in ('pdf_sha256', 'renderer_sha256', 'pages', 'body_pages',
                'visual_reviewed_pages', 'visual_review_sha256'):
        manifest.pop(key, None)
    (target / 'build_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print({'folder': FOLDER, 'P93_outputs': 18, 'additional_generations': 0})


if __name__ == '__main__':
    build()

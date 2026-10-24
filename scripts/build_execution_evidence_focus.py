"""Create an editorial edition focused on the closed execution evidence."""
from datetime import datetime, timezone
import json

from build_observed_control_draft import replace_once
from run_handoff_factors import ROOT, read, sha

PARENT = 'papers/202610_letter/closed_results_action_execution'
FOLDER = 'papers/202610_letter/execution_evidence_focus'


def build():
    target, parent = ROOT / FOLDER, ROOT / PARENT
    if target.exists():
        raise FileExistsError('preserve_evidence_focus_edition')
    old = read(parent / 'build_manifest.json')
    sources = dict(old['source_sha256'])
    for name, expected in old['generated_sha256'].items():
        sources[PARENT + '/' + name] = expected
    for name in ('build_manifest.json', 'draft.pdf', 'visual_review.json'):
        sources[PARENT + '/' + name] = sha(parent / name)
    for name in ('scripts/build_execution_evidence_focus.py',
                 'scripts/render_bound_letter_draft.py',
                 'docs/letter_evidence_focus_20261024.md'):
        sources[name] = sha(ROOT / name)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('closed_source_changed:' + name)
    generated = {n: (parent / n).read_text() for n in old['generated_sha256']}
    source = generated['draft.tex'].replace(PARENT + '/', FOLDER + '/')
    old_ja = source.split('\\textbf{あらまし案}\\quad\n', 1)[1].split('\n\n', 1)[0]
    old_en = source.split('\\textbf{Summary draft}\\quad ', 1)[1].split('\n', 1)[0]
    ja = ('状態保持型LLMエージェントで制御入力の表現と実行を評価した. '
          '参照統一後の一致出力６件はツールを提出せず，構文が異なる出力から同じAPI列も実行された. '
          '既知４課題24条件の通知比較を併せ，一致指標と全仕事費用の限界を示す.')
    en = ('We examined control-input representations in stateful LLM agents. '
          'Six matching outputs after reference canonicalization submitted no tools, '
          'while syntactically different outputs executed identical API requests. '
          'Together with 24 whole-task conditions, these cases show why output agreement '
          'must be checked against executable actions, task outcomes, and full costs.')
    if len(ja) > 120 or len(en.split()) > 50 or any(c in ja for c in ('。', '・')):
        raise ValueError('abstract_format')
    source = replace_once(source, old_ja, ja)
    source = replace_once(source, old_en, en)
    start = source.index('\\section{問題設定と関連研究}')
    end = source.index('\\section{共通の履歴処理と通知}', start)
    introduction = r'''\section{問題設定と関連研究}
状態保持型LLMエージェントの費用を減らすには，必要な情報を残し，操作と最終成果を損なわない制御が必要である．しかし，ハーネスの入力表現をそろえて出力が安定しても，有効な操作を提出できたとは限らない．本稿では，呼出し参照の表現統一と残時間の通知を対象に，入力・出力の一致が実操作と全仕事の改善にどこまで対応するかを調べる．CodeAct\cite{codeact}型のコード行動とAppWorld\cite{appworld}の状態を持つアプリ操作を対象とする．

時間通知と期限強制の分離\cite{clock}，時間適応\cite{timely}，数値実行の非決定性\cite{nondeterminism}，ツール列・引数・出力の反復照合\cite{consistency}には先行研究がある．ハーネス探索\cite{beyondprompts}，実行形式\cite{localprotocol}と情報提示\cite{delivery}の影響，出典記録\cite{repro}，参照IDの改名感度と正規化\cite{canonical}も扱われている．また，論理tokenと実費用の違い\cite{costproxy}，cacheと圧縮・遅延の関係\cite{capc,cacheeval}が知られている．

本稿では，誤った引数を文章化する際に通信参照が通常文へ移る具体的な経路を確認し，保存した１文脈の全18出力を新しい環境で実行して照合する．表現を統一した同一本文がツールを提出しない場合と，構文が異なっても同じAPI要求列を実行する場合を示す．併せて既知４課題24条件の通知比較を全件報告する．参照統一の新アルゴリズムや一般的な高速化の提案ではなく，局所的な一致を評価するときに実行口と全仕事の結果を確認するための事例を示す．

'''
    source = source[:start] + introduction + source[end:]
    source = replace_once(source, '\\section{解釈の範囲}', '\\section{考察と適用範囲}')
    marker = '独立した課題は調整に用いた既知４つであり，'
    discussion = (
        '参照統一は，通常文へ移る前の構造を対象にすることで入力差を取り除いた．'
        'ただしC/Dの同じ本文を「同じ有効行動」と採点すれば，実行口で拒否された６出力を見落とす．'
        '逆にA/Xの構文不一致だけからAPI操作の不一致を判定すると，実際には同じ要求列を実行した事例を区別できない．'
        'このため，公開出力の比較にはツール提出・実行の可否を添え，API要求列と標準出力も分けて報告する．'
        'これは一致率を課題成功の代わりに用いる判断を避けるための，今回の測定範囲での解釈である．\n'
    )
    source = replace_once(source, marker, discussion + marker)
    generated['draft.tex'] = source
    generated['conclusion.tex'] = (
        '制御入力の表現と通知を，次出力・実操作・全仕事の三段階で評価した．'
        '１保存文脈では，参照統一後の６出力が同じ本文でもツールを提出せず，'
        '別の出力対では構文の違いがAPI要求列の違いを伴わなかった．'
        '通知比較の全24条件も保持し，後半通知の全４採用基準は未達だった．'
        'これらは出力一致を有効行動や省費用の代理とすると誤解する具体例である．'
        '既知４課題と１文脈を超える頻度，一般的な品質維持，新手法の優位性は今後の検証を要する．\n')
    target.mkdir(parents=True, exist_ok=False)
    for name, value in generated.items():
        (target / name).write_text(value)
    manifest = {**old, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sources, 'generated_sha256': {n: sha(target / n) for n in generated},
        'parent_draft': PARENT, 'editorial_focus_only': True,
        'all_numeric_result_sections_byte_unchanged':
            [n for n in generated if n not in ('draft.tex', 'conclusion.tex')],
        'new_model_generations': 0, 'new_environment_api_requests': 0,
        'new_evaluations': 0, 'reserved_scenarios_read': 0,
        'P97_intermediate_results_used': False,
        'visual_reviewed': False, 'submission_ready': False}
    for key in ('pdf_sha256', 'renderer_sha256', 'pages', 'body_pages',
                'visual_reviewed_pages', 'visual_review_sha256'):
        manifest.pop(key, None)
    (target / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print({'folder': FOLDER, 'ja_characters': len(ja), 'en_words': len(en.split()),
           'new_generations': 0})


if __name__ == '__main__':
    build()

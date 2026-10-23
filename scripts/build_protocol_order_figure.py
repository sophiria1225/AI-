"""Draw the existing reference-rendering mechanism, without private histories."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output):
    ledger_names = ('reports/protocol_minimal_reproducer_20261024.json',
                    'reports/P81_P83_results_provenance_20261024.json')
    expected_hashes = {}
    for name in ledger_names:
        expected_hashes.update(json.loads((ROOT / name).read_text())['source_sha256'])
    names = ('scripts/protocol_stable_history.py', 'scripts/native_conversation.py',
             'scripts/budget_visibility_comparison.py', 'reports/P83_fallback_prompt.json')
    for name in names:
        if sha(ROOT / name) != expected_hashes[name]:
            raise ValueError('closed_mechanism_source_changed:' + name)
    report = json.loads((ROOT / names[-1]).read_text())
    if (report['status'] != 'complete' or report['completed_renderings'] != 6
            or not all(report['normalized_pair_equal'].values())):
        raise ValueError('closed_input_equivalence_required')
    normalized = [report['rendered'][key]['input_tokens']
                  for key in ('P83_P80_NORMALIZED', 'P83_R2_NORMALIZED')]
    if normalized != [22650, 22650]:
        raise ValueError('expected_closed_input_counts_changed')
    output.mkdir(parents=True, exist_ok=False)
    # Outline Japanese glyphs: this installed CFF font does not survive the
    # TrueType PDF path. Keep vector output portable without a system font.
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11, 'pdf.fonttype': 3,
                         'svg.fonttype': 'path'})
    fig = plt.figure(figsize=(12.0, 7.8), facecolor='white')
    ax = fig.add_axes([.025, .025, .95, .95])
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    navy, teal, orange, muted = '#243b53', '#177b79', '#a65730', '#526578'
    ax.text(.02, .96, '参照の統一と文章化の順序を分けて考える',
            fontsize=20, color=navy, va='top', weight='bold')
    ax.text(.02, .895, 'C：対応を保った参照欄の統一　　R：モデルへ渡す表示の作成',
            fontsize=12, color=muted, va='top')
    ax.text(.02, .854, '不正な引数を含む呼出しは文章として保持する。下図の a / b は合成した参照である。',
            fontsize=11, color=muted, va='top')

    def box(x, y, w, h, title, body, accent, fill):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.008,rounding_size=0.008',
                                   edgecolor=accent, facecolor=fill, linewidth=1.2))
        ax.text(x+w/2, y+h-(.02 if h < .14 else .028), title,
                ha='center', va='top', color=accent, fontsize=12, weight='bold')
        ax.text(x+w/2, y+(.02 if h < .14 else .035), body,
                ha='center', va='bottom', color=navy, fontsize=11, linespacing=1.45)

    xs, w, h = (.03, .27, .51, .75), .205, .145
    for y, accent in ((.62, orange), (.36, teal)):
        for a, b in zip(xs, xs[1:]):
            ax.add_patch(FancyArrowPatch((a+w+.01, y+h/2), (b-.015, y+h/2),
                         arrowstyle='-|>', mutation_scale=15, linewidth=1.25, color=accent))
    ax.text(.02, .802, '表示後に統一する順序　C(R(h))', fontsize=14, color=orange, weight='bold')
    box(xs[0], .62, w, h, '元の会話', '参照欄 a / b\n他の値は同じ', orange, '#fff9f4')
    box(xs[1], .62, w, h, '先に R：文章化', '参照が文字列の\n内部へ移る', orange, '#fff9f4')
    box(xs[2], .62, w, h, '次に C：参照統一', '構造上の欄だけが対象\n文章内の a / b は残る', orange, '#fff9f4')
    box(xs[3], .62, w, h, 'モデルへ渡す表示', '文章内は a / b\n入力の差が残る', orange, '#fff0e7')
    ax.text(.02, .542, '表示前に統一する順序　R(C(h))', fontsize=14, color=teal, weight='bold')
    box(xs[0], .36, w, h, '元の会話', '参照欄 a / b\n他の値は同じ', teal, '#f4fbfa')
    box(xs[1], .36, w, h, '先に C：参照統一', '両方の参照を同じ\n初出順の名前へ', teal, '#f4fbfa')
    box(xs[2], .36, w, h, '次に R：文章化', '統一済みの参照で\n文章を作る', teal, '#f4fbfa')
    box(xs[3], .36, w, h, 'モデルへ渡す表示', 'この対応改名に対して\n入力の値が一致', teal, '#e7f5f2')
    ax.text(.03, .312, 'Cは通常文・引数・観測・エラー・返却推論の値を変更しない。元記録を保持し、参照の不整合は拒否する。',
            fontsize=10, color=muted, va='top')
    box(.03, .135, .445, .125, 'P83：保存入力の照合で確認済み',
        '表示前統一した２入力は各22,650 token。\n実テンプレートの文章とtoken列が一致した。', teal, '#f4fbfa')
    box(.515, .135, .44, .125, 'P84：次の公開出力は別の診断',
        '保存した全６入力×３反復を固定・本実行前。\n生成コード・環境API・課題評価は実行しない。', muted, '#f5f7fa')
    ax.text(.03, .078, '入力の一致 ≠ 出力の一致 ≠ 成果品質の維持・全仕事費用の削減',
            fontsize=13, color=navy, weight='bold', va='top')
    ax.text(.03, .03, '実装の説明図であり、新アルゴリズムの主張ではない。模式図とP83の測定範囲を区別する。  2026-10-24',
            fontsize=9, color=muted, va='top')
    for ext in ('pdf', 'svg', 'png'):
        fig.savefig(output / f'protocol_order.{ext}', dpi=180, facecolor='white')
    plt.close(fig)
    sources = {name: sha(ROOT / name) for name in names}
    sources.update({name: sha(ROOT / name) for name in ledger_names})
    sources['scripts/build_protocol_order_figure.py'] = sha(Path(__file__))
    manifest = dict(created_at=datetime.now(timezone.utc).isoformat(), source_sha256=sources,
        output_sha256={p.name: sha(p) for p in sorted(output.glob('protocol_order.*'))},
        synthetic_identifiers=True, real_P83_counts_only=True, P84_execution_claimed=False,
        model_generations=0, input_count_requests=0, environment_api_requests=0, evaluations=0,
        private_histories_read=False, private_reasoning_read=False, novel_method_claim=False,
        general_quality_preservation_claim=False, visual_reviewed=False)
    with (output / 'build_manifest.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print({'output': str(output), 'assets': 3, 'model_generations': 0})
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_protocol_order_figure')
    args = parser.parse_args()
    build(args.output)

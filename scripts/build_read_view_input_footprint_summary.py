"""Build a compact public summary of the closed P104 counts without raw rereads."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    with p.open('x') as stream:
        json.dump(d,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
def csv_file(p,rows):
    with p.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def build(root):
    sys.path.insert(0,str(root/'scripts'))
    from read_view_input_footprint import compare_boundaries
    from measure_read_view_input_footprint import PLAN,ZERO
    rel='reports/P104_read_view_input_footprint.json'
    report=read(root/rel);plan=read(root/PLAN)
    if (report['status']!='complete' or report['plan_sha256']!=sha(root/PLAN)
            or report['source_sha256']!=plan['source_sha256']
            or report['private_source_sha256']!=plan['private_source_sha256']
            or len(report['rows'])!=24 or len(report['operations'])!=4
            or any(row['status']!='complete' for row in report['rows'])
            or any(row['status']!='complete' or row['renderings']!=6 or row['decode_calls']!=0
                   or row['owned_process_absent'] is not True for row in report['operations'])
            or any(report[k]!=0 for k in ZERO)
            or report['total_observed_LLM_usage'] is not None or report['task_quality_measured']):
        raise ValueError('closed_complete_P104_counts_required')
    for name,h in plan['source_sha256'].items():
        if sha(root/name)!=h:raise ValueError('fixed_source_changed:'+name)
    pairs=compare_boundaries(report['rows'])
    if pairs!=report['comparisons']:raise ValueError('all_boundary_comparisons_changed')
    output=root/'materials/20261025_p104_results';output.mkdir(parents=True,exist_ok=False)
    fields=('policy','representation','after_program','includes_terminal_boundary','input_tokens',
            'original_program_API_requests','original_cumulative_API_requests',
            'messages_sha256','prompt_sha256','tokens_sha256','session_controls_sha256',
            'parsed_non_message_parameters_sha256','stdout_sha256','program_sha256','request_sha256',
            'outer_observation_sha256','private_rendered_sha256')
    rows=[{**{k:row[k] for k in fields},**row['formatting']} for row in report['rows']]
    csv_file(output/'all_24_renderings.csv',rows)
    csv_file(output/'all_12_boundary_pairs.csv',pairs)
    operation_fields=('policy','representation','status','renderings','decode_calls','exit_code',
                      'sampled_peak_rss_bytes','wall_seconds','owned_process_absent',
                      'manifest_sha256','metadata_sha256')
    operations=[{k:row[k] for k in operation_fields} for row in report['operations']]
    csv_file(output/'all_4_renderer_batches.csv',operations)
    write(output/'summary.json',dict(phase='P104',status='complete',source_report_sha256=sha(root/rel),
        source_plan_sha256=sha(root/PLAN),comparisons=pairs,operations=operations,
        original_API_requests=report['original_API_requests'],total_observed_LLM_usage=None,
        task_quality_measured=False,novel_method_claim=False,**{k:0 for k in ZERO}))
    table='| 表示 | 段階後 | 即時入力T | 遅延入力T | 遅延−即時T | 入力列一致 |\n|---|---:|---:|---:|---:|---|\n'
    for pair in pairs:
        table+='| '+ ' | '.join(str(x) for x in (pair['representation'],pair['after_program'],
            pair['eager_input_tokens'],pair['deferred_input_tokens'],pair['deferred_minus_eager_input_tokens'],
            pair['token_sequence_equal']))+' |\n'
    text='''# P104: 手書き遅延読取の入力経路を全件計数

終了済みの同じ６段階を現在の会話形式へ通し、２方式×２表示×６段階後の全24入力を一度計数した. 新しいモデル生成・API・Python実行・評価は０. 同じプログラム、既知課題、説明、表示上限を使った事後の比較用入力であり、過去に送信されたLLM要求や生成された課題解決過程ではない.

元の実APIは即時11対遅延10で、６段階のstdoutは一致する. 下表の負値は、この限定入力において遅延側が短いことを示す. 入力数の合計を実際の全仕事使用量とはしない. 第６段階後は終端の表示確認で、実際の次のモデル呼出しではない.

'''+table+'''
harnessは通常の実API数・受領参照・登録順span IDを含む. content_attributionはstdoutと成否等を残し、そのメタデータを除いた計測用表示で、品質保持を検証済みの制御方式ではない. 入力列が全て一致する場合、その表示における本文由来のtoken差はない.

[全24入力](all_24_renderings.csv)／[全12組](all_12_boundary_pairs.csv)／[全４描画処理](all_4_renderer_batches.csv)／[固定した比較](../../docs/experiments/P104_read_view_input_footprint.md).

固定の語彙専用rendererを使用し、推論contextとdecodeは０. 実エージェントの生成履歴や各時点の予算通知は再構成せず、共通説明・手書き提出・通常の外側観測を会話へ通した範囲を計数する. 上限・失敗・元記録を変更せず、計数用の時間と標本化RSSを別に保存した. 強い通常方式との実課題比較、生成token、最終品質、再取得や制御費を含む全仕事の改善は未確認. 新規手法の成立を示す結果とはしない. 原稿の逐次改訂は保留を維持する.
'''
    (output/'README.md').write_text(text)
    files={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    write(output/'build_manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        source_report_sha256=sha(root/rel),builder_sha256=sha(Path(__file__)),public_artifact_sha256=files,
        raw_results_reread=False,model_generations=0,environment_API_requests=0,
        manuscript_changed=False,all_renderings=24,all_pairs=12))
    print(json.dumps(dict(status='complete',all_renderings=24,all_pairs=12,raw_results_reread=False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,required=True)
    build(parser.parse_args().repo_root.resolve())

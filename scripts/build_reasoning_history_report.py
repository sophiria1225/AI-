"""Audit closed P75 metadata and build a short, non-private results artifact."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from inspect_reasoning_history import ROOT, PLAN, ZERO_KEYS, read, sha

RAW = 'reports/P75_reasoning_history.json'
RAW_SHA = 'e55380f7d0cc4b4321c81132a606884b411b1a74ca75f3e087317db2cc431461'
STEM = 'AI_harness_reasoning_history_20261023'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def audit():
    if sha(ROOT / RAW) != RAW_SHA:
        raise ValueError('closed_P75_report_changed')
    raw, plan = read(ROOT / RAW), read(ROOT / PLAN)
    if (raw['status'] != 'complete' or raw['accounted_attempts'] != 105 or raw['unprocessed_attempts']
            or len(raw['rows']) != 105 or len(raw['groups']) != 16
            or raw['plan_sha256'] != sha(ROOT / PLAN)
            or raw['protocol_sha256'] != sha(ROOT / 'docs/experiments/P75_reasoning_history.md')
            or any(raw[k] for k in ZERO_KEYS) or raw['novel_method_claim']
            or raw['quality_improvement_established'] or raw['measured_savings'] is not None):
        raise ValueError('complete_unchanged_metadata_inspection_required')
    for path, expected in (raw['source_sha256'] | raw['implementation_sha256']).items():
        if sha(ROOT / path) != expected:
            raise ValueError('fixed_P75_source_changed')
    prefixes = {}; checked = []; offset = 0
    for group, reported in zip(plan['groups'], raw['groups'], strict=True):
        rows = raw['rows'][offset:offset + len(group['calls'])]; offset += len(rows)
        previous_chars, previous_count = prefixes[group['prefix_run']] if group['prefix_run'] else (0, 0)
        for expected, row in zip(group['calls'], rows, strict=True):
            if (row['run_id'] != group['run_id'] or row['source'] != group['source']
                    or row['call_id'] != expected['call_id'] or row['source_sha256'] != expected['files']
                    or row['recorded_status'] != expected['recorded_status'] or not row['public_prefix_matches']
                    or row['input_assistant_messages'] != previous_count
                    or row['preceding_nonempty_reasoning_responses'] != previous_count
                    or row['preceding_reasoning_characters'] != previous_chars
                    or row['restored_reasoning_characters'] != previous_chars
                    or not row['restorable_without_overwrite']
                    or row['reasoning_fields_exactly_match_preceding'] != (previous_count == 0)
                    or any(row[k] for k in ('input_reasoning_fields', 'input_nonempty_reasoning_messages',
                                          'input_reasoning_characters', 'input_inline_think_marker_messages'))):
                raise ValueError('all_call_identity_or_causal_metadata_disagrees')
            shape = row['known_output_reasoning']
            if row['recorded_status'] == 'ok':
                if not shape or not shape['field_present'] or not shape['nonempty'] or shape['characters'] <= 0:
                    raise ValueError('known_reasoning_metadata_disagrees')
                previous_count += 1; previous_chars += shape['characters']
            elif shape is not None:
                raise ValueError('unknown_output_cannot_be_imputed')
        counts = Counter(r['recorded_status'] for r in rows)
        derived = {'run_id': group['run_id'], 'source': group['source'], 'attempts': len(rows),
            'known_output_responses': counts['ok'], 'unknown_usage_attempts': counts['error'],
            'nonempty_known_output_reasoning': sum(bool(r['known_output_reasoning']) for r in rows),
            'known_output_reasoning_characters': sum((r['known_output_reasoning'] or {}).get('characters', 0) for r in rows),
            'requests_containing_nonempty_reasoning': 0,
            'requests_omitting_nonempty_preceding_reasoning': sum(r['input_assistant_messages'] > 0 for r in rows)}
        if reported != derived: raise ValueError('group_totals_disagree')
        checked.append(derived)
        if group['source'] == 'prefix': prefixes[group['run_id']] = (previous_chars, previous_count)
    totals = {k: sum(g[k] for g in checked) for k in raw['totals']}
    if totals != raw['totals'] or list(totals.values()) != [105, 103, 2, 103, 31658, 0, 101]:
        raise ValueError('whole_population_totals_disagree')
    return raw, {'phase': 'P75_audit', 'status': 'complete', 'source_report_sha256': RAW_SHA,
        'audit_errors': [], 'all_105_attempts_accounted': True, 'all_public_prefixes_matched': True,
        'all_causal_character_counts_matched': True, 'groups': checked, 'totals': totals,
        **{k: 0 for k in ZERO_KEYS}, 'novel_method_claim': False,
        'quality_improvement_established': False, 'measured_savings': None,
        'wall_seconds': raw['wall_seconds'], 'auditor_sha256': sha(Path(__file__))}


def build(output):
    raw, checked = audit(); output.mkdir(parents=True, exist_ok=True)
    save(ROOT / 'reports/P75_reasoning_history_audit.json', checked)
    with (output / 'all_history_groups.csv').open('w', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(checked['groups'][0])); w.writeheader(); w.writerows(checked['groups'])
    with (output / 'all_history_attempts.csv').open('w', newline='') as stream:
        fields = ['run_id', 'source', 'call_id', 'recorded_status', 'input_assistant_messages',
                  'input_reasoning_characters', 'preceding_reasoning_characters', 'known_output_reasoning_characters']
        w = csv.DictWriter(stream, fieldnames=fields); w.writeheader()
        for row in raw['rows']:
            w.writerow({k: row[k] for k in fields[:-1]} | {'known_output_reasoning_characters':
                row['known_output_reasoning']['characters'] if row['known_output_reasoning'] is not None else ''})
    slides = [dict(title='全履歴基準が<br>保持していた情報の範囲', cover=True)]
    def add(title, body, takeaway, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, notes=notes, cover=False))
    add('105回を点検：過去の推論は入力へ渡っていなかった',
        '<table><tr><th>固定した範囲</th><th>生成の試行</th><th>非空の推論がある正常応答</th><th>使用量不明</th></tr>'
        '<tr><td>既知４課題の共通前半</td><td>32</td><td>32</td><td>0</td></tr>'
        '<tr><td>P71の全12継続条件</td><td>73</td><td>71</td><td>2</td></tr>'
        '<tr><td>全件</td><td>105</td><td>103</td><td>2</td></tr></table>'
        '<p class="lead">過去応答が存在する101入力すべてで、推論フィールドは未投入。</p>',
        'これはP10から明記された条件。過去の結果を不具合として書き換えない。',
        '105は過去の生成試行数で、今回の新しい生成は０。各課題の初回４入力には過去応答がない。103正常応答の推論は合計31,658文字で、token数・品質差・節約量ではない。')
    table = ''.join(f'<tr><td>{label}</td><td>{r["known_output_reasoning_characters"]:,}</td><td>0</td></tr>'
                    for label, r in zip(('写真整理', '精算', '返金', '曲情報の書出し'), checked['groups'][:4], strict=True))
    add('同じ前半に保持できる情報はあるが、効果は未測定',
        '<table><tr><th>共通前半：各８応答</th><th>保存された推論の文字数</th><th>元入力に渡された文字数</th></tr>' + table + '</table>'
        '<p class="body">各入力の公開content・呼出しを、それ以前の応答へ順番どおり照合。<br>全105回で対応が一致し、追加するフィールドの文字数も検算した。</p>',
        '保持ありの通常対照を試していない、という比較条件の制約が残る。',
        '最後の前半応答の推論は、その前半応答自身への入力にはまだ存在しない。表の保存文字数は前半８応答の合計で、次の継続入力で保持できる量。私的な文章の意味は読まず、公開しない。')
    add('次は通常対照の有限比較を先に固定する',
        f'<p class="lead">今回の読取点検は {raw["wall_seconds"]:.3f}秒。未処理０。</p>'
        '<ul><li>新しい生成・tokenizer・環境API・評価・コード実行は０。</li>'
        '<li>旧部品を残し、全推論を保持する任意選択の通常部品を追加。</li>'
        '<li>保持あり・なしを比べる場合は、同じ予算と独立評価を先に固定。</li>'
        '<li>保持分の入力費用と、成功・失敗・追加処理をまとめて評価する。</li></ul>',
        '推論保持自体は新規手法ではない。新提案の中核は未確立。',
        'M2の記事、M3.1-Flashの現行ガイド、今回の固定M3テンプレートを区別する。別モデルでの推奨をM3の効果量へ移さない。保留12課題は未閲覧のまま維持する。')
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 通常対照の履歴 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P75_findings.md">全結果と限界</a></span>'
                f'<span>{i}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:31px}table{font-size:20px}td{padding:12px 15px}li{font-size:24px;margin:15px 0}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P75 通常対照の推論履歴</title><style>' + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    save(output / 'slides.json', slides)
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'builder_sha256': sha(Path(__file__)), 'source_sha256': {RAW: RAW_SHA,
        'reports/P75_reasoning_history_audit.json': sha(ROOT / 'reports/P75_reasoning_history_audit.json'),
        PLAN: raw['plan_sha256']}, 'claims': checked['totals'], 'visual_reviewed': False,
        'csv_sha256': {p: sha(output / p) for p in ('all_history_groups.csv', 'all_history_attempts.csv')},
        'shared_rendering_sha256': {p: sha(ROOT / 'scripts' / p) for p in ('build_morning_report.py', 'build_budget_report.py')}}
    save(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p75')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    result = build(args.output); print({k: result[k] for k in ('pages', 'claims')})
    if args.pdf: build_budget_report.STEM = STEM; build_budget_report.export(args.output)

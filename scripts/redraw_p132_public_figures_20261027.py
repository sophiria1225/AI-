"""Data-only redraw of published P132 figures; not an experiment/audit rerun.

Requires the separately published manifest digest, exact original renderer source,
figure_data.json and output_manifest.json. Never calls the renderer's private
closed-result loader. No raw experiment/closure/review files are required.
"""
import argparse
import hashlib
import types
import json
from pathlib import Path
import re
import sys

RENDERER_SHA = '26ba450901eff3d1c35cb379b0e0fac3d48f7cf43e5ad3b0fb4401187c8b03aa'
ARTIFACTS = {'README.md', 'figure_data.json', 'p132_inventory_exposure_cost.pdf',
             'p132_inventory_exposure_cost.png', 'p132_tokens_quality.pdf', 'p132_tokens_quality.png'}
MANIFEST_FIELDS = {'phase', 'synthetic_preview', 'actual_results', 'source_sha256',
    'closure_collector_review_sha256', 'renderer_sha256', 'fixed_execution_head', 'fixed_plan_sha256',
    'fixed_independent_review_source_sha256', 'python_version', 'matplotlib_version', 'artifact_sha256',
    'all_two_slots_retained', 'independent_tasks', 'repetitions', 'model_seeds', 'unknown_is_not_zero',
    'primary_baseline', 'treatment', 'shared_grounding_mode',
    'closed_and_independently_reviewed_public_artifacts_verified', 'general_quality_preservation_claim',
    'novel_method_claim', 'timing_superiority_claim', 'inventory_capture_metadata_recomputed_from_program_values',
    'additional_model_API_evaluator_tokenizer_calls', 'saved_program_execution', 'outcome_based_selection'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def is_hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def read_bytes(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64 * 1024 * 1024,
            'bounded_regular_input_required')
    return path.read_bytes()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def public_name(value):
    return (type(value) is str and not Path(value).is_absolute() and '\\' not in value
        and '..' not in Path(value).parts and value.split('/')[0] in
        ('scripts', 'tests', 'configs', 'docs', 'reports', 'materials'))


def renderer_from_source(path, raw):
    require(digest(raw) == RENDERER_SHA, 'fixed_original_renderer_source_required')
    # Only the exact public source is loaded. Its __main__ is not executed;
    # load_closed is never called by this entrypoint.
    module = types.ModuleType('_p132_hash_bound_figure_renderer')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(digest(read_bytes(path)) == RENDERER_SHA, 'renderer_changed_during_import')
    return module


def validate_package(data, manifest, renderer, data_sha):
    require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS, 'fixed_original_manifest_schema_required')
    require(manifest['phase'] == 'P132' and manifest['renderer_sha256'] == RENDERER_SHA,
            'fixed_P132_renderer_binding_required')
    require(type(manifest['artifact_sha256']) is dict and set(manifest['artifact_sha256']) == ARTIFACTS
        and all(is_hash(v) for v in manifest['artifact_sha256'].values())
        and manifest['artifact_sha256']['figure_data.json'] == data_sha, 'original_figure_data_hash_required')
    require(type(manifest['synthetic_preview']) is bool and type(manifest['actual_results']) is bool
        and manifest['actual_results'] is not manifest['synthetic_preview'], 'exact_actual_or_synthetic_status_required')
    for key, wanted in {'fixed_execution_head': renderer.HEAD, 'fixed_plan_sha256': renderer.PLAN_SHA,
            'fixed_independent_review_source_sha256': renderer.REVIEW_SHA, 'all_two_slots_retained': True,
            'independent_tasks': 1, 'repetitions': 1, 'model_seeds': [57], 'unknown_is_not_zero': True,
            'primary_baseline': 'off', 'treatment': 'checkpoint_inventory', 'shared_grounding_mode': 'feedback',
            'closed_and_independently_reviewed_public_artifacts_verified': manifest['actual_results'],
            'general_quality_preservation_claim': False, 'novel_method_claim': False,
            'timing_superiority_claim': False, 'inventory_capture_metadata_recomputed_from_program_values': False,
            'additional_model_API_evaluator_tokenizer_calls': 0, 'saved_program_execution': 0,
            'outcome_based_selection': False}.items():
        require(same(manifest[key], wanted), 'fixed_manifest_scope:' + key)
    for key in ('python_version', 'matplotlib_version'):
        require(type(manifest[key]) is str and re.fullmatch(r'[0-9A-Za-z.+-]{1,40}', manifest[key]) is not None,
                'public_version_string_required')
    public = manifest['source_sha256']; external = manifest['closure_collector_review_sha256']
    require(type(public) is dict and all(public_name(k) and is_hash(v) for k, v in public.items()),
            'public_relative_source_hashes_only')
    require(type(external) is dict and all(is_hash(v) for v in external.values()), 'metadata_hash_values_only')
    if manifest['actual_results']:
        require({renderer.PLAN, renderer.REPORT, renderer.SESSION, renderer.MATERIALS + '/summary.json',
                 renderer.MATERIALS + '/build_manifest.json'}.issubset(public), 'original_public_bindings_required')
        require(set(external) == {'collector', 'collector_start', 'closure', 'pipeline_start', 'independent_review'},
                'original_metadata_hash_labels_required')
    else:
        require(public == external == {}, 'synthetic_cannot_claim_actual_bindings')
    require(type(data) is dict and data.get('synthetic') is manifest['synthetic_preview'],
            'data_manifest_synthetic_flag_differs')
    rebuilt = renderer.validate_rows(data['conditions'], data, data['audit_error_count'])
    rebuilt['synthetic'] = data['synthetic']
    require(same(data, rebuilt), 'exact_two_slot_row_recomputed_data_required')
    return rebuilt


def load_package(figure_data, original_manifest, renderer_source, expected_manifest_sha256):
    require(is_hash(expected_manifest_sha256), 'published_manifest_digest_required')
    manifest_bytes = read_bytes(original_manifest)
    require(digest(manifest_bytes) == expected_manifest_sha256, 'published_manifest_hash_differs')
    manifest = parse(manifest_bytes)
    source_bytes = read_bytes(renderer_source)
    require(digest(source_bytes) == RENDERER_SHA, 'fixed_original_renderer_source_required')
    data_bytes = read_bytes(figure_data)
    renderer = renderer_from_source(renderer_source, source_bytes)
    data = validate_package(parse(data_bytes), manifest, renderer, digest(data_bytes))
    return data, manifest, renderer, {'figure_data': data_bytes, 'manifest': manifest_bytes, 'renderer': source_bytes}


def main(args):
    output = Path(args.output_dir).resolve()
    require(not output.exists() and not output.is_symlink(), 'new_output_directory_required')
    data, original, renderer, raw = load_package(args.figure_data, args.original_manifest,
        args.renderer_source, args.manifest_sha256)
    output.mkdir(parents=True, exist_ok=False)
    renderer.render(data, output)
    (output / 'figure_data.json').write_bytes(raw['figure_data'])
    (output / 'original_output_manifest.json').write_bytes(raw['manifest'])
    note = f'''# P132 public figure redraw{' — SYNTHETIC, NOT ACTUAL RESULTS' if data['synthetic'] else ''}

This directory redraws the already published aggregate data. It does not repeat or independently certify the experiment, closure, evaluation, usage audit, or private independent review. The supplied manifest digest must be obtained from the publication; a digest supplied with arbitrary data does not authenticate the scientific claims.

The exact original renderer source, figure-data bytes and original manifest are hash-bound. The two fixed cells, seed 57, official outcomes, unknown/missing data, row-derived aggregates and criteria are checked before rendering. Both conditions are retained. Captures and actual actor exposures are distinct. Bytes are not tokens; a cheap failure is not same-success token reduction. This single known task-seed pair supports no general quality, novelty, or timing-superiority claim. Earlier attempts are not pooled.

Reproduce with Python plus matplotlib:

```
python redraw_p132_public_figures_20261027.py --figure-data figure_data.json --original-manifest original_output_manifest.json --manifest-sha256 {args.manifest_sha256} --renderer-source draw_p132_results_20261027.py --output-dir NEW_DIRECTORY
```

The two Python source files are distributed alongside the publication. No private absolute paths, private audit text, raw task records, saved program execution, model, API, tokenizer, or evaluator are required. The public source/hash references inside the original manifest are preserved as historical bindings, not rechecked against unavailable original execution state.

Scientific plot data and labels are reproduced. PNG/PDF bytes may differ with Python, matplotlib, fonts, platform, creation-time metadata or supplied source filename. Original artifact hashes remain in `original_output_manifest.json`; newly rendered artifact hashes are in `redraw_manifest.json`. This is not a byte-identical archive restoration. No input file is overwritten. The current rendering environment is Python {sys.version.split()[0]}, matplotlib {renderer.matplotlib.__version__}.
'''
    (output / 'README.md').write_text(note)
    for key, path in (('figure_data', args.figure_data), ('manifest', args.original_manifest), ('renderer', args.renderer_source)):
        require(read_bytes(path) == raw[key], 'input_changed_during_redraw:' + key)
    result = dict(phase='P132_public_figure_redraw', data_only_redraw=True, synthetic_preview=data['synthetic'],
        original_manifest_sha256=digest(raw['manifest']), original_figure_data_sha256=digest(raw['figure_data']),
        original_renderer_sha256=digest(raw['renderer']), redraw_script_sha256=digest(read_bytes(__file__)),
        original_artifact_sha256=original['artifact_sha256'],
        artifact_sha256={p.name: digest(read_bytes(p)) for p in sorted(output.iterdir())},
        python_version=sys.version.split()[0], matplotlib_version=renderer.matplotlib.__version__,
        original_experiment_audit_reexecuted=False, original_closure_and_review_revalidated=False,
        publication_digest_authenticity_independently_established=False,
        exact_figure_data_bytes_preserved=True, original_manifest_bytes_preserved=True,
        PNG_PDF_byte_identity_guaranteed=False, planned_conditions=2, independent_tasks=1, model_seeds=[57],
        additional_model_API_evaluator_tokenizer_calls=0, saved_program_execution=0,
        private_trial_records_read=False, general_quality_preservation_claim=False,
        novel_method_claim=False, timing_superiority_claim=False)
    (output / 'redraw_manifest.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return {'data_only_redraw': True, 'synthetic_preview': data['synthetic'], 'conditions': 2,
            'output_directory': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figure-data', type=Path, required=True)
    parser.add_argument('--original-manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--renderer-source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    print(json.dumps(main(parser.parse_args())))

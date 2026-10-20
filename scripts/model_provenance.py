"""Validate per-quantization paths and provenance without changing prior records."""
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SELECTION = 'configs/models/minimax_m3_selection.json'


def local_path(value, root=ROOT):
    value = Path(value)
    path = (root / value).resolve()
    if value.is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('model records must use paths within this repository')
    return path


def load_selection(name=LEGACY_SELECTION, root=ROOT):
    config = json.loads(local_path(name, root).read_text())
    if not re.fullmatch(r'[0-9a-f]{40}', config['revision']):
        raise ValueError('immutable Hub commit required')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', config['repo_id']):
        raise ValueError('invalid public repository identifier')
    if (not re.fullmatch(r'[\w.-]+', config['subdirectory'])
            or config['subdirectory'] in ('.', '..')):
        raise ValueError('one quantization directory required')
    if type(config['total_bytes']) is not int or config['total_bytes'] <= 0:
        raise ValueError('positive pinned weight size required')
    if name == LEGACY_SELECTION:
        if config['quantization'] != 'Q3_K_L' or config['subdirectory'] != 'MiniMax-M3-Q3_K_L':
            raise ValueError('legacy records belong to Q3_K_L only')
        config.setdefault('file_manifest', 'configs/models/minimax_m3_files.json')
        config.setdefault('download_record', 'records/models/p2_minimax_download.json')
        config.setdefault('model_alias', 'minimax-m3-q3kl')
    for key, parent in (('file_manifest', 'configs/models'), ('download_record', 'records/models')):
        path = local_path(config[key], root)
        if not path.is_relative_to(local_path(parent, root)):
            raise ValueError(f'{key} must be under {parent}')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', config['model_alias']):
        raise ValueError('explicit local model alias required')
    return config


def validate_manifest(config, manifest):
    if (manifest['repo_id'] != config['repo_id'] or manifest['revision'] != config['revision']
            or manifest['total_bytes'] != config['total_bytes']):
        raise ValueError('model manifest identity or size differs from selection')
    files = manifest['files']
    if not files or len({entry['path'] for entry in files}) != len(files):
        raise ValueError('empty or duplicate model files')
    for entry in files:
        path = PurePosixPath(entry['path'])
        if (path.is_absolute() or '..' in path.parts or len(path.parts) != 2
                or path.parts[0] != config['subdirectory'] or path.suffix != '.gguf'):
            raise ValueError('file outside selected quantization')
        if type(entry['bytes']) is not int or entry['bytes'] <= 0:
            raise ValueError('positive file size required')
        if not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
            raise ValueError('file SHA-256 required')
    if sum(entry['bytes'] for entry in files) != config['total_bytes']:
        raise ValueError('file sizes differ from selection')


def stable_manifest(config, manifest, root=ROOT):
    """Keep an existing fixed manifest byte-for-byte; reject conflicting content."""
    validate_manifest(config, manifest)
    path = local_path(config['file_manifest'], root)
    if path.exists():
        previous = json.loads(path.read_text())
        validate_manifest(config, previous)
        if sorted(previous['files'], key=lambda e: e['path']) != sorted(manifest['files'], key=lambda e: e['path']):
            raise ValueError('existing fixed file manifest differs; preserve it')
        return previous
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def verified_model(name=LEGACY_SELECTION, root=ROOT):
    config = load_selection(name, root)
    record = json.loads(local_path(config['download_record'], root).read_text())
    if record['status'] != 'verified':
        raise ValueError('all model files must be verified before loading')
    manifest = record['manifest']
    validate_manifest(config, manifest)
    fixed = json.loads(local_path(config['file_manifest'], root).read_text())
    validate_manifest(config, fixed)
    if sorted(fixed['files'], key=lambda e: e['path']) != sorted(manifest['files'], key=lambda e: e['path']):
        raise ValueError('verification record differs from fixed manifest')
    destination = local_path(record['destination'], root)
    if not destination.is_relative_to(local_path('models', root)):
        raise ValueError('weights must remain under models/')
    for entry in manifest['files']:
        verified = record['files'][entry['path']]
        if (verified.get('status') != 'verified' or verified.get('sha256') != entry['sha256']
                or verified.get('bytes') != entry['bytes']):
            raise ValueError('individual file verification is incomplete')
        path = (destination / entry['path']).resolve()
        if not path.is_relative_to(destination) or path.stat().st_size != entry['bytes']:
            raise ValueError('verified model file path or size changed')
    model = destination / sorted(manifest['files'], key=lambda e: e['path'])[0]['path']
    return config, record, model


def runtime_cache_types(runtime):
    command = runtime['command']
    actual = []
    for flag, key in (('--cache-type-k', 'cache_type_k'), ('--cache-type-v', 'cache_type_v')):
        if command.count(flag) != 1:
            raise ValueError('supervised command must specify each KV cache type once')
        index = command.index(flag)
        if index + 1 >= len(command):
            raise ValueError('missing supervised KV cache value')
        value = command[index + 1]
        if value not in ('f16', 'q8_0') or runtime.get(key, value) != value:
            raise ValueError('supervised KV cache fields disagree')
        actual.append(value)
    return tuple(actual)


def check_live_model(name, runtime, props, expected_ctx=None, root=ROOT, expected_cache=None):
    config, record, model = verified_model(name, root)
    if runtime.get('status') != 'ready' or runtime['runtime'] != config['runtime']:
        raise ValueError('supervised model/runtime is not the selected ready instance')
    if runtime['model_revision'] != config['revision']:
        raise ValueError('supervised model revision differs')
    if (props['default_generation_settings']['n_ctx'] != runtime['ctx_size']
            or props['total_slots'] != 1 or props['model_alias'] != config['model_alias']):
        raise ValueError('live model settings differ from selection')
    if expected_ctx is not None and runtime['ctx_size'] != expected_ctx:
        raise ValueError('live context differs from experiment')
    if expected_cache is not None and runtime_cache_types(runtime) != tuple(expected_cache):
        raise ValueError('supervised KV cache differs from experiment')
    build = config['runtime']['binary_tag'] + '-' + config['runtime']['commit'][:9]
    if props['build_info'] != build or Path(props.get('model_path', '')).resolve() != model.resolve():
        raise ValueError('live model path or build differs from verified selection')
    return config, record, model

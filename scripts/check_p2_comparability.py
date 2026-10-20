"""Check the prepared Q3/IQ4 conditions without starting model inference."""
import ast
import datetime
import hashlib
import json
from pathlib import Path

from run_mini_pilot import make_templates

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_CHANGES = {
    'model', 'model_path', 'model_selection', 'readiness', 'readiness_scope',
    'readiness_limitations', 'calibration_records',
}
BASELINES = {
    '15380': '20261020_113741_mini_6688ea',
    '15957': '20261020_115912_mini_acf0fa',
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def core_definitions(path):
    names = {'stop', 'OllamaModel', 'RestrictedEnvironment', 'make_templates'}
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(path.read_text()).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names}


def compare_configs(left, right):
    changed = sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
    return {'changed_config_fields': changed,
            'unexpected_changed_fields': sorted(set(changed) - ALLOWED_CHANGES),
            'identical_agent_templates': make_templates(left) == make_templates(right)}


def main():
    pairs = []
    current = ROOT / 'scripts/run_mini_pilot.py'
    for task, baseline in BASELINES.items():
        directory = ROOT / 'records/p2' / baseline
        original = read(directory / 'config.json')
        prepared = read(ROOT / f'configs/P2_minimax_iq4_{task}.json')
        pair = {'task': task, 'Q3_record': str(directory.relative_to(ROOT)),
                **compare_configs(original, prepared), 'IQ4_readiness': prepared['readiness']}
        old_hashes = read(directory / 'summary.json')['source_hashes']
        pair['source_comparison'] = {
            name: {'baseline_sha256': value, 'current_sha256': sha(ROOT / 'scripts' / name),
                   'identical': value == sha(ROOT / 'scripts' / name)}
            for name, value in old_hashes.items()}
        pair['unchanged_inference_environment_template_definitions'] = (
            core_definitions(directory / 'run_mini_pilot.py') == core_definitions(current))
        pair['runner_change_note'] = (
            'The runner file differs: the model-specific startup provenance check was generalized, '
            'a readiness guard and extra provenance records were added. The inference adapter, '
            'environment adapter, templates, and other previously captured sources are compared here. '
            'This is a source/configuration audit, not proof of numerical equivalence.')
        pair['passed'] = (not pair['unexpected_changed_fields']
                          and pair['identical_agent_templates']
                          and pair['unchanged_inference_environment_template_definitions']
                          and all(v['identical'] for k, v in pair['source_comparison'].items()
                                  if k != 'run_mini_pilot.py'))
        pairs.append(pair)
    report = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'Recorded Q3 conditions versus prepared IQ4; no model inference',
              'pairs': pairs, 'runner_sha256': sha(current),
              'checker_sha256': sha(Path(__file__)), 'passed': all(p['passed'] for p in pairs)}
    path = ROOT / 'reports/P2_quantization_comparability.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': str(path.relative_to(ROOT)), 'passed': report['passed']}))
    return report['passed']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)

"""Record a narrow, non-secret environment survey using the standard library."""
import datetime
import hashlib
import json
import pathlib
import shutil
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'records' / 'environment'
OUT.mkdir(parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
commands = {
    'kernel': ['uname', '-srm'],
    'hardware': ['sysctl', '-n', 'hw.model', 'machdep.cpu.brand_string', 'hw.memsize', 'hw.ncpu'],
    'os': ['sw_vers'],
    'disk': ['df', '-k', str(ROOT)],
    'python_default': ['python3', '--version'],
    'python_research': ['/opt/homebrew/opt/python@3.12/bin/python3.12', '--version'],
    'git': ['git', '--version'],
    'ollama_models': ['ollama', 'list'],
}
report = {'recorded_at': now, 'commands': {}, 'tools': {}}
for key, argv in commands.items():
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        report['commands'][key] = {'argv': argv, 'exit_code': result.returncode,
                                    'stdout': result.stdout, 'stderr': result.stderr}
    except Exception as error:
        report['commands'][key] = {'argv': argv, 'error': repr(error)}
for name in ['python3', 'uv', 'docker', 'podman', 'colima', 'ollama', 'brew']:
    report['tools'][name] = shutil.which(name)
for endpoint in ['version', 'tags', 'ps']:
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/' + endpoint, timeout=10) as response:
            report['ollama_' + endpoint] = json.load(response)
    except Exception as error:
        report['ollama_' + endpoint] = {'error': repr(error)}
source = pathlib.Path('/Users/tp26013/Downloads/codex_harness_research_handoff_20261013.md')
report['source_handoff'] = {'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
path = OUT / ('survey_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'record': str(path), 'tools': report['tools']}))

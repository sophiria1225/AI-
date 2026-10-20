"""Pin and acquire only the prespecified second development task image."""
import datetime
import hashlib
import json
import pathlib
import urllib.request

import docker
import pyarrow.parquet as pq
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
task_id = 'django__django-15380'
repo = 'swebench/sweb.eval.x86_64.django_1776_django-15380'
with urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repo + ':pull', timeout=30) as response:
    token = json.load(response)['token']
def manifest(ref):
    request = urllib.request.Request('https://registry-1.docker.io/v2/' + repo + '/manifests/' + ref,
        headers={'Authorization':'Bearer '+token, 'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'})
    with urllib.request.urlopen(request,timeout=30) as response:
        content = response.read()
        digest = response.headers.get('Docker-Content-Digest')
    if digest and digest != 'sha256:' + hashlib.sha256(content).hexdigest():
        raise RuntimeError('registry manifest digest mismatch')
    return json.loads(content), digest
index, index_digest = manifest('latest')
if 'manifests' in index:
    digest = next(x['digest'] for x in index['manifests'] if x.get('platform',{}) == {'architecture':'amd64','os':'linux'})
    data, actual = manifest(digest)
    if actual != digest:
        raise RuntimeError('platform digest mismatch')
else:
    data, digest = index, index_digest
image = repo + '@' + digest
record = {'task_id':task_id, 'image':image, 'index_digest':index_digest,
          'index':index, 'manifest':data, 'compressed_bytes':sum(x['size'] for x in data['layers']),
          'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(ROOT/'records/sources/P1_task_image_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'image':image,'compressed_bytes':record['compressed_bytes']}),flush=True)
client = docker.from_env(timeout=120)
for event in client.api.pull(image,stream=True,decode=True):
    if 'error' in event:
        raise RuntimeError(event['error'])
    if event.get('status','').startswith(('Digest:','Status:')):
        print(json.dumps(event),flush=True)
source = ROOT/'vendor/swe-bench-tasks/tasks'/task_id
hf = next(t for t in pq.read_table(ROOT/'private_eval/verified.parquet').to_pylist() if t['instance_id'] == task_id)
reference = yaml.safe_load((source/'task.yaml').read_text())
public = next(json.loads(line) for line in (ROOT/'data/verified_public_inputs.jsonl').read_text().splitlines() if json.loads(line)['instance_id'] == task_id)
checks = {k: hf[k] == public[k] for k in public}
checks.update(gold_patch=hf['patch'].strip()==(source/'gold.patch').read_text().strip(),
              test_patch=hf['test_patch'].strip()==(source/'test.patch').read_text().strip())
if not all(checks.values()):
    raise RuntimeError('task versions disagree: ' + repr(checks))
reference['image'] = image
for key in ['patch','test_patch','problem_statement','hints_text']:
    reference[key] = hf[key]
reference['eval_script'] = (source/'eval.sh').read_text()
test_labels = json.loads((source/'tests.json').read_text())
for key in ['FAIL_TO_PASS','PASS_TO_PASS']:
    expected = json.loads(hf[key]) if isinstance(hf[key],str) else hf[key]
    if set(expected) != set(test_labels[key]):
        raise RuntimeError('test label versions disagree')
    reference[key] = expected
destination=ROOT/'private_eval/P1_second_task.json'
destination.write_text(json.dumps([reference],indent=2)+'\n')
destination.chmod(0o600)
(ROOT/'records/sources/P1_task_version_comparison.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps({'task_id':task_id,'version_checks':checks}),flush=True)

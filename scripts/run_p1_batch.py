"""Execute the four prespecified development runs once, without evaluation feedback."""
import datetime
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'records/p1_batches'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
out.mkdir(parents=True)
order=['P1_large_15957.json','P1_large_15380.json','P1_small_15380.json','P1_small_15957.json']
manifest={'order':order,'config_hashes':{name:hashlib.sha256((ROOT/'configs'/name).read_bytes()).hexdigest() for name in order},
          'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runs':[],'management_requests':[]}
previous=None
for name in order:
    config=json.loads((ROOT/'configs'/name).read_text())
    if previous!=config['model']:
        for model in ['qwen3.8-flash-next:125b-mlx','qwen3.8:27b-mlx']:
            request=urllib.request.Request('http://127.0.0.1:11434/api/generate',
                data=json.dumps({'model':model,'keep_alive':0,'stream':False}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=60) as response:
                result=json.load(response)
            manifest['management_requests'].append({'model':model,'operation':'unload','response':result})
        previous=config['model']
    before=set((ROOT/'records/p1').glob('*')) if (ROOT/'records/p1').exists() else set()
    started=time.monotonic()
    result=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/run_mini_pilot.py'),
                           '--config','configs/'+name],cwd=ROOT,timeout=1050)
    created=sorted(set((ROOT/'records/p1').glob('*'))-before)
    manifest['runs'].append({'config':name,'exit_code':result.returncode,'seconds':time.monotonic()-started,
                             'paths':[str(p.relative_to(ROOT)) for p in created]})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['runs'][-1]),flush=True)
print(json.dumps({'batch_record':str(out),'completed':len(manifest['runs'])}),flush=True)

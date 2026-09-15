"""Explicit allowlist packaging; excludes user data, secrets, caches and logs."""
import hashlib
import json
import zipfile
from pathlib import Path
from weatherlab.fixtures import sample, config
from weatherlab.strategies import STRATEGIES
from weatherlab.packages import inspect_package

ROOT=Path(__file__).resolve().parent


def build():
    (ROOT/'dist').mkdir(exist_ok=True)
    (ROOT/'configs').mkdir(exist_ok=True)
    (ROOT/'examples').mkdir(exist_ok=True)
    data,history=sample()
    (ROOT/'examples/dataset.synthetic.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (ROOT/'examples/history.synthetic.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in history),encoding='utf-8')
    for key in STRATEGIES:
        (ROOT/'configs'/f'{key}.json').write_text(json.dumps(config(key),indent=2),encoding='utf-8')
    files=[ROOT/'README.md',ROOT/'run.py',ROOT/'build_packages.py',ROOT/'settings.env.example',ROOT/'.gitignore',ROOT/'.gitattributes']
    for directory,pattern in [('weatherlab','*.py'),('tests','*.py'),('web','*'),('docs','*.md'),('configs','*.json'),('examples','*')]:
        files.extend(sorted((ROOT/directory).glob(pattern)))
    files.extend(sorted((ROOT/'weatherlab').glob('*.cjs')))
    contents={p.relative_to(ROOT).as_posix():p.read_bytes() for p in files if p.is_file()}
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in contents.items()}
    outputs=[]
    for index,key in enumerate(STRATEGIES,1):
        manifest={'schema_version':1,'runtime':'weatherlab-1.0.0','bot_id':key,'version':'1.0.0','entrypoint':'python -m weatherlab',
                  'config':config(key),'files':hashes,'paper_only':True}
        name=f'{index:02d}-'+{'wallet_control':'wallet-control','fixed_llm':'fixed-llm','adaptive_llm':'adaptive-llm','polyswarm':'polyswarm'}[key]+'.zip'
        path=ROOT/'dist'/name
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for member,raw in sorted(contents.items()):
                info=zipfile.ZipInfo(member,(2026,9,15,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
            info=zipfile.ZipInfo('manifest.json',(2026,9,15,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,json.dumps(manifest,indent=2))
        inspect_package(path.read_bytes(),ROOT)
        outputs.append(path)
    dashboard=ROOT/'dist/weather-lab-dashboard.zip'
    with zipfile.ZipFile(dashboard,'w',zipfile.ZIP_DEFLATED) as z:
        for member,raw in sorted(contents.items()):z.writestr(member,raw)
    outputs.append(dashboard)
    sums={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in outputs}
    (ROOT/'dist/SHA256SUMS.json').write_text(json.dumps(sums,indent=2),encoding='utf-8')
    print(json.dumps(sums,indent=2))


if __name__=='__main__':build()

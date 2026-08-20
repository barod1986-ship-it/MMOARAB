from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
VERSIONS=json.loads((ROOT/'engine'/'packaging'/'runtime-versions.json').read_text(encoding='utf-8'))
ALLOWED={'windows-x86_64','macos-arm64','linux-x86_64'}

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def main() -> int:
    p=argparse.ArgumentParser(description='Write compatibility metadata for the final post-signing Engine artifact bytes.')
    p.add_argument('artifact', type=Path)
    p.add_argument('--target', required=True, choices=sorted(ALLOWED))
    p.add_argument('--signed', action='store_true')
    p.add_argument('--notarized', action='store_true')
    p.add_argument('--out', type=Path)
    a=p.parse_args(); artifact=a.artifact.resolve()
    if not artifact.is_file(): raise SystemExit('final Engine artifact does not exist')
    if a.notarized and not a.signed: raise SystemExit('notarized artifact must also be signed')
    if a.target.startswith('windows-') and a.notarized: raise SystemExit('Windows artifact cannot be marked notarized')
    if a.target.startswith('macos-') and a.signed and not a.notarized: raise SystemExit('public macOS finalization requires notarization with signing')
    data={'schemaVersion':1,'target':a.target,'engineVersion':VERSIONS['engineVersion'],'protocolMajor':VERSIONS['protocolMajor'],'pythonBuildRuntime':VERSIONS['python'],'artifact':artifact.name,'sha256':'sha256:'+sha256(artifact),'signed':a.signed,'notarized':a.notarized,'finalArtifact':True}
    out=(a.out or artifact.with_name(artifact.name+'.compatibility.json')).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8'); print(out); return 0
if __name__=='__main__': raise SystemExit(main())

from __future__ import annotations
import argparse,json
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('directory',type=Path); p.add_argument('--release-class',required=True,choices=['developer-preview','private-v1','public-v1']); a=p.parse_args()
    candidates=[]
    for meta in sorted(a.directory.rglob('*.compatibility.json')):
        try: d=json.loads(meta.read_text(encoding='utf-8'))
        except Exception: continue
        artifact=meta.parent/str(d.get('artifact',''))
        if not artifact.is_file():
            matches=list(a.directory.rglob(str(d.get('artifact','')))) if d.get('artifact') else []
            artifact=matches[0] if len(matches)==1 else artifact
        if not artifact.is_file(): continue
        target=str(d.get('target','')); signed=bool(d.get('signed')); notarized=bool(d.get('notarized'))
        acceptable=True
        if a.release_class=='public-v1' and target.startswith('windows-'): acceptable=signed
        if a.release_class=='public-v1' and target.startswith('macos-'): acceptable=signed and notarized
        if acceptable: candidates.append((1 if d.get('finalArtifact') else 0,1 if signed else 0,1 if notarized else 0,artifact,meta,str(d.get('sha256','')).removeprefix('sha256:')))
    if not candidates: raise SystemExit(f'no compatible Engine candidate found under {a.directory}')
    candidates.sort(reverse=True,key=lambda x:x[:3])
    _,_,_,artifact,meta,digest=candidates[0]
    print(f'{artifact}\t{meta}\t{digest}')
    return 0
if __name__=='__main__': raise SystemExit(main())

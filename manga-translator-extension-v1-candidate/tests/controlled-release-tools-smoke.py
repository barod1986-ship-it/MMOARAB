from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'prepare_controlled_release.py'
SOURCE_SHA='a'*40

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def extension_zip(path: Path, *, extra_permission: str | None = None) -> None:
    permissions=['activeTab','scripting','storage','sidePanel','alarms']
    if extra_permission:
        permissions.append(extra_permission)
    manifest={
      'manifest_version':3,'name':'fixture','version':'0.9.0','minimum_chrome_version':'148',
      'permissions':permissions,
      'optional_host_permissions':['https://*/*','http://127.0.0.1/*'],'message_serialization':'structured_clone'
    }
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest)); z.writestr('sidepanel.html','ok')

def run(*args: str):
    return subprocess.run([sys.executable,str(SCRIPT),'--source-head-sha',SOURCE_SHA,'--qualified-source-head-sha',SOURCE_SHA,*args],cwd=ROOT,text=True,capture_output=True)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix='mte-phase9-') as td:
        t=Path(td); ext=t/'extension.zip'; extension_zip(ext)
        engine=t/'mte-local-engine-0.5.0-linux-x86_64.tar.gz'; engine.write_bytes(b'engine-fixture')
        compat=t/(engine.name+'.compatibility.json')
        compat.write_text(json.dumps({'schemaVersion':1,'target':'linux-x86_64','engineVersion':'0.5.0','protocolMajor':1,'artifact':engine.name,'sha256':'sha256:'+digest(engine),'signed':False,'notarized':False,'finalArtifact':True}),encoding='utf-8')
        out=t/'release'
        result=run('--release-id','fixture-rc1','--release-class','developer-preview','--extension-zip',str(ext),'--extension-sha256',digest(ext),'--engine',f'{engine}::{compat}::{digest(engine)}','--out',str(out))
        assert result.returncode==0,result.stderr
        release=out/'fixture-rc1'; manifest=json.loads((release/'controlled-release.json').read_text())
        assert manifest['extension']['sha256']==digest(ext)
        assert digest(release/ext.name)==digest(ext)
        assert digest(release/engine.name)==digest(engine)
        assert manifest['engines'][0]['protocolMajor']==1
        # Public Windows must fail closed when the compatibility sidecar says unsigned.
        win=t/'mte-local-engine-0.5.0-windows-x86_64.zip'; win.write_bytes(b'windows-fixture')
        wmeta=t/(win.name+'.compatibility.json'); wmeta.write_text(json.dumps({'schemaVersion':1,'target':'windows-x86_64','engineVersion':'0.5.0','protocolMajor':1,'artifact':win.name,'sha256':'sha256:'+digest(win),'signed':False,'notarized':False,'finalArtifact':True}),encoding='utf-8')
        result=run('--release-id','bad-public','--release-class','public-v1','--extension-zip',str(ext),'--extension-sha256',digest(ext),'--engine',f'{win}::{wmeta}::{digest(win)}','--out',str(out))
        assert result.returncode!=0 and 'must be signed' in (result.stderr+result.stdout)
        assert not (out/'bad-public').exists(), 'failed assembly must not leave a final release directory'
        mac=t/'mte-local-engine-0.5.0-macos-arm64.tar.gz'; mac.write_bytes(b'macos-fixture')
        mmeta=t/(mac.name+'.compatibility.json'); mmeta.write_text(json.dumps({'schemaVersion':1,'target':'macos-arm64','engineVersion':'0.5.0','protocolMajor':1,'artifact':mac.name,'sha256':'sha256:'+digest(mac),'signed':False,'notarized':False}),encoding='utf-8')
        private_engines=[f'{engine}::{compat}::{digest(engine)}',f'{win}::{wmeta}::{digest(win)}',f'{mac}::{mmeta}::{digest(mac)}']
        # Tampered hash must never be archived.
        result=run('--release-id','bad-hash','--release-class','developer-preview','--extension-zip',str(ext),'--extension-sha256','0'*64,'--engine',f'{engine}::{compat}::{digest(engine)}','--out',str(out))
        assert result.returncode!=0 and 'hash mismatch' in (result.stderr+result.stdout)
        assert not (out/'bad-hash').exists(), 'failed assembly must be transactional'
        # Permission drift in the exact Extension artifact is rejected before archival.
        bad_ext=t/'extension-bad-permissions.zip'; extension_zip(bad_ext, extra_permission='tabs')
        result=run('--release-id','bad-permissions','--release-class','developer-preview','--extension-zip',str(bad_ext),'--extension-sha256',digest(bad_ext),'--engine',f'{engine}::{compat}::{digest(engine)}','--out',str(out))
        assert result.returncode!=0 and 'required permission drift' in (result.stderr+result.stdout)
        assert not (out/'bad-permissions').exists(), 'invalid extension must not create a final release directory'
        # V1 cannot be assembled without the locked SBOM/license metadata set.
        args=['--release-id','bad-v1-metadata','--release-class','private-v1','--extension-zip',str(ext),'--extension-sha256',digest(ext),'--out',str(out)]
        for item in private_engines: args += ['--engine',item]
        result=run(*args)
        assert result.returncode!=0 and 'V1 controlled release metadata missing' in (result.stderr+result.stdout)
        assert not (out/'bad-v1-metadata').exists(), 'incomplete V1 assembly must not leave a final release directory'
        # V1 metadata is copied as exact bytes and recorded in the manifest/checksum set.
        meta_files=[]
        for name,payload in {
            'extension.cyclonedx.json':b'{"bomFormat":"CycloneDX","components":[]}',
            'engine.cyclonedx-1.5.json':b'{"bomFormat":"CycloneDX","components":[]}',
            'engine.pylock.toml':b'lock-version = "1.0"\n',
            'MODEL_LICENSES.json':b'{"schemaVersion":1,"artifacts":[]}',
            'production-profile-freeze.json':b'{"schemaVersion":1,"fixture":true}',
        }.items():
            path=t/name; path.write_bytes(payload); meta_files.append(path)
        args=['--release-id','private-with-metadata','--release-class','private-v1','--extension-zip',str(ext),'--extension-sha256',digest(ext),'--out',str(out)]
        for item in private_engines: args += ['--engine',item]
        for path in meta_files: args += ['--metadata',f'{path}::{digest(path)}']
        result=run(*args)
        assert result.returncode==0,result.stderr
        private_manifest=json.loads((out/'private-with-metadata'/'controlled-release.json').read_text())
        assert private_manifest['schemaVersion']==2 and private_manifest['sourceHeadSha']==SOURCE_SHA and private_manifest['qualifiedSourceHeadSha']==SOURCE_SHA
        assert {item['artifact'] for item in private_manifest['metadata']}=={p.name for p in meta_files}
    print('Phase 9 controlled release tooling smoke: 6/6 passed')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

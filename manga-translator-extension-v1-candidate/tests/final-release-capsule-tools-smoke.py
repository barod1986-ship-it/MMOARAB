from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from final_release_capsule import CapsuleError, build_capsule, verify_capsule
from v1_evidence_orchestrator import next_session, seal_session, write_session

SOURCE='a'*40
QUALIFIED='b'*40
TARGETS=('linux-x86_64','macos-arm64','windows-x86_64')


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_fixture(root: Path) -> tuple[Path, Path, Path]:
    release_id='v1-private-fixture'
    controlled=root/'release'/'controlled'/release_id
    controlled.mkdir(parents=True)

    ext=controlled/'extension.zip'; ext.write_bytes(b'extension-exact-bytes')
    engines=[]
    for i,target in enumerate(TARGETS,1):
        suffix='.zip' if target.startswith('windows') else ('.pkg' if target.startswith('macos') else '.tar.gz')
        art=controlled/f'engine-{target}{suffix}'; art.write_bytes(f'engine-{target}'.encode())
        meta=controlled/f'engine-{target}.compatibility.json'
        meta_value={'schemaVersion':1,'target':target,'engineVersion':'0.5.0','protocolMajor':1,'artifact':art.name,'sha256':'sha256:'+digest(art),'signed':target!='linux-x86_64','notarized':target=='macos-arm64','finalArtifact':True}
        write_json(meta,meta_value)
        engines.append({'target':target,'artifact':art.name,'sha256':digest(art),'bytes':art.stat().st_size,'byteIdenticalToTestedArtifact':True,'engineVersion':'0.5.0','protocolMajor':1,'signed':meta_value['signed'],'notarized':meta_value['notarized'],'compatibilityMetadata':meta.name,'compatibilityMetadataSha256':digest(meta)})

    freeze=root/'engine'/'mte_engine'/'benchmark'/'production-profile-freeze.json'; write_json(freeze,{'fixture':True})
    metadata=[]
    meta_sources={
        'extension.cyclonedx.json': b'{}\n',
        'engine.cyclonedx-1.5.json': b'{}\n',
        'engine.pylock.toml': b'lock-version = "1.0"\n',
        'MODEL_LICENSES.json': b'{}\n',
        'production-profile-freeze.json': freeze.read_bytes(),
    }
    for name,raw in meta_sources.items():
        p=controlled/name; p.write_bytes(raw)
        metadata.append({'artifact':name,'sha256':digest(p),'bytes':p.stat().st_size,'kind':'release-metadata','byteIdenticalToInput':True,'byteIdenticalToTestedArtifact':True})

    manifest={'schemaVersion':2,'releaseId':release_id,'sourceHeadSha':SOURCE,'qualifiedSourceHeadSha':QUALIFIED,'releaseClass':'private-v1','extension':{'artifact':ext.name,'sha256':digest(ext),'bytes':ext.stat().st_size,'byteIdenticalToTestedArtifact':True},'engines':engines,'metadata':metadata,'protocolMajor':1,'exactArtifactsOnly':True,'rebuildDuringPromotion':False}
    mf=controlled/'controlled-release.json'; write_json(mf,manifest); msha=digest(mf)
    sums=[f"{manifest['extension']['sha256']}  {ext.name}"]
    for item in engines:
        sums += [f"{item['sha256']}  {item['artifact']}", f"{item['compatibilityMetadataSha256']}  {item['compatibilityMetadata']}"]
    for item in metadata: sums.append(f"{item['sha256']}  {item['artifact']}")
    sums.append(f'{msha}  controlled-release.json')
    (controlled/'SHA256SUMS').write_text('\n'.join(sums)+'\n')

    package_lock=root/'package-lock.json'; package_lock.write_bytes(b'package-lock-real-fixture')
    uv_lock=root/'engine'/'uv.lock'; uv_lock.parent.mkdir(parents=True,exist_ok=True); uv_lock.write_bytes(b'uv-lock-real-fixture')
    privacy=root/'store'/'release'/'profile-privacy.json'; write_json(privacy,{'schemaVersion':2,'fixture':True})
    records=root/'release-control'/'smoke-records.json'; write_json(records,{'schemaVersion':2,'records':[]})
    state=root/'release-control'/'release-state.json'; write_json(state,{'schemaVersion':1,'releaseClass':'private-v1'})
    source_sums=root/'SOURCE_SHA256SUMS.txt'; source_sums.write_text('fixture\n')

    prefinal={
        'schemaVersion':1,'revision':'rev19-v1-evidence-orchestration-v2-public-store-closure','releaseId':release_id,'releaseClass':'private-v1','stage':'evidence-promoted','sequence':5,
        'assemblySourceHeadSha':SOURCE,'qualifiedSourceHeadSha':QUALIFIED,
        'qualification':{'freezeSha256':digest(freeze),'freezeIdentitySha256':'1'*64,'runPlanSha256':'2'*64,'packageLockSha256':digest(package_lock),'uvLockSha256':digest(uv_lock)},
        'controlled':{'manifestSha256':msha,'controlledRunId':100,'candidateRunIds':{'extension':101,'linux':102,'macos':103,'windows':104}},
        'nativeSmoke':{'engineSmokeRunId':200,'observations':{'linux-x86_64':'3'*64,'macos-arm64':'4'*64,'windows-x86_64':'5'*64}},
        'browserSmoke':{'observationsByMajor':{'148':'6'*64,'151':'7'*64}},
        'evidencePromotion':{'profilePrivacySha256':digest(privacy),'smokeRecordsSha256':digest(records),'releaseStateSha256':digest(state)},
        'previousSessionSha256':'8'*64,
    }
    prefinal=seal_session(prefinal)
    prefinal_path=root/'release-control'/'v1-orchestration.json'; write_session(prefinal_path,prefinal)
    ready=next_session(prefinal,'release-ready','finalGate',{'gate':'check:controlled-release-ready','targetClass':'private-v1','passed':True})
    ready_path=root/'release'/'orchestration'/'release-ready.json'; write_session(ready_path,ready)
    return controlled, ready_path, root/'release'/'final'/release_id


def main() -> int:
    checks=0
    with tempfile.TemporaryDirectory(prefix='mte-final-capsule-') as raw:
        root=Path(raw)
        controlled, ready, output=make_fixture(root)
        result=build_capsule(root=root,session_path=ready,controlled_dir=controlled,output=output,finalization_source_head_sha='c'*40,verify_gate=False)
        assert result['valid'] is True and result['releaseClass']=='private-v1' and result['subjects'] >= 20
        assert verify_capsule(output)['releaseManifestSha256']==result['releaseManifestSha256']
        checks+=1

        # Final capsule tampering is detected even when the manifest itself is unchanged.
        extension=output/'artifacts'/'extension.zip'; extension.write_bytes(extension.read_bytes()+b'tamper')
        try:
            verify_capsule(output); raise AssertionError('tampered final artifact passed')
        except CapsuleError:
            pass
        checks+=1

    with tempfile.TemporaryDirectory(prefix='mte-final-capsule-extra-') as raw:
        root=Path(raw); controlled, ready, output=make_fixture(root)
        (controlled/'unexpected.bin').write_bytes(b'not-allowlisted')
        try:
            build_capsule(root=root,session_path=ready,controlled_dir=controlled,output=output,finalization_source_head_sha='c'*40,verify_gate=False); raise AssertionError('extra controlled file passed')
        except CapsuleError as exc:
            assert 'inventory differs' in str(exc)
        checks+=1

    with tempfile.TemporaryDirectory(prefix='mte-final-capsule-controlled-tamper-') as raw:
        root=Path(raw); controlled, ready, output=make_fixture(root)
        (controlled/'engine-linux-x86_64.tar.gz').write_bytes(b'changed')
        try:
            build_capsule(root=root,session_path=ready,controlled_dir=controlled,output=output,finalization_source_head_sha='c'*40,verify_gate=False); raise AssertionError('controlled artifact tampering passed')
        except CapsuleError as exc:
            assert 'hash mismatch' in str(exc)
        checks+=1

    with tempfile.TemporaryDirectory(prefix='mte-final-capsule-chain-') as raw:
        root=Path(raw); controlled, ready, output=make_fixture(root)
        value=json.loads(ready.read_text()); value['previousSessionSha256']='f'*64
        # Re-seal the attacker-modified final session; chain check must still reject it.
        value.pop('sessionSha256',None); value=seal_session(value); write_json(ready,value)
        try:
            build_capsule(root=root,session_path=ready,controlled_dir=controlled,output=output,finalization_source_head_sha='c'*40,verify_gate=False); raise AssertionError('re-sealed broken orchestration chain passed')
        except CapsuleError as exc:
            assert 'not chained' in str(exc)
        checks+=1

    print(f'Final release capsule tooling smoke: {checks}/5 passed')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

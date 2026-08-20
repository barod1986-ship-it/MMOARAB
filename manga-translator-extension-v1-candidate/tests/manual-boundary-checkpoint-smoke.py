from __future__ import annotations
import hashlib, importlib.util, json, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts')); sys.path.insert(0,str(ROOT/'engine'))
from manual_boundary_checkpoint import (
    ManualCheckpointError, create_checkpoint, validate_checkpoint, validate_checkpoint_evidence,
    validate_exact_browser_smoke, validate_store_installed_smoke, validate_benchmark_review, operator_and_head,
)
from v1_evidence_orchestrator import write_session, write_store_handoff
from mte_engine.benchmark.execution import executor_pin, seal_review_draft
from mte_engine.benchmark.run_plan import run_plan_digest

SOURCE='a'*40


def write(path:Path,value:dict): path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path:Path): return hashlib.sha256(path.read_bytes()).hexdigest()

def manifest(path:Path):
    value={'schemaVersion':2,'releaseId':'v1-fixture','sourceHeadSha':SOURCE,'qualifiedSourceHeadSha':SOURCE,'releaseClass':'private-v1','protocolMajor':1,'exactArtifactsOnly':True,'rebuildDuringPromotion':False,
           'extension':{'artifact':'extension.zip','sha256':'1'*64},
           'engines':[{'target':'linux-x86_64','artifact':'engine-linux.tar.gz','sha256':'2'*64},{'target':'macos-arm64','artifact':'engine-macos.tar.gz','sha256':'3'*64},{'target':'windows-x86_64','artifact':'engine-windows.zip','sha256':'4'*64}], 'metadata':[]}
    write(path,value); return sha(path)

def native_session(path:Path,msha:str):
    value={'schemaVersion':1,'revision':'rev19-v1-evidence-orchestration-v2-public-store-closure','releaseId':'v1-fixture','releaseClass':'private-v1','stage':'native-smoke-complete','sequence':3,
           'assemblySourceHeadSha':SOURCE,'qualifiedSourceHeadSha':SOURCE,
           'qualification':{'freezeSha256':'5'*64,'freezeIdentitySha256':'6'*64,'runPlanSha256':'7'*64,'packageLockSha256':'8'*64,'uvLockSha256':'9'*64},
           'controlled':{'manifestSha256':msha,'controlledRunId':100,'candidateRunIds':{'extension':101,'linux':102,'macos':103,'windows':104}},
           'nativeSmoke':{'engineSmokeRunId':200,'observations':{'linux-x86_64':'a'*64,'macos-arm64':'b'*64,'windows-x86_64':'c'*64}},
           'previousSessionSha256':'d'*64}
    write_session(path,value); return json.loads(path.read_text())['sessionSha256']

def browser(path:Path,msha:str,session_sha:str,major:int):
    write(path,{'schemaVersion':2,'id':f'browser-{major}','artifactManifestSha256':msha,'orchestrationSessionSha256':session_sha,'sourceHeadSha':SOURCE,'kind':'unpacked-extension','platform':'browser','artifact':'extension.zip','artifactSha256':'1'*64,
                'engineTargetAtTest':'linux-x86_64','engineArtifactAtTest':'engine-linux.tar.gz','engineArtifactSha256AtTest':'2'*64,'browserVersion':f'{major}.0.0.1','testedAtUtc':'2026-08-20T00:00:00Z','cleanEnvironment':True,
                'checks':{'install':True,'activate':True,'translateFixture':True,'restore':True},'fixtureUrl':'http://127.0.0.1:4173/fixture.html','evidenceMode':'interactive-human-observed-exact-bytes'})

def benchmark(path_plan:Path,path_review:Path):
    artifacts=[{'artifactId':name,'sha256':'sha256:'+str(i)*64,'expectedFilename':f'{name}.bin'} for i,name in enumerate(('det','en','ja','ko','zh','inp'),1)]
    plan={'schemaVersion':2,'runPlanRevision':'rev11-production-benchmark-run-plan-v3','createdAtUtc':'2026-08-20T00:00:00Z','ready':True,'reasons':[],'corpusId':'fixture','corpusManifestSha256':'sha256:'+'1'*64,'policyRevision':'p','policySha256':'sha256:'+'2'*64,'catalogRevision':'c','catalogSha256':'sha256:'+'3'*64,'candidatePlanRevision':'cp','candidatePlanSha256':'sha256:'+'4'*64,'executor':executor_pin(),
          'dependencyLocks':{'revision':'rev11-qualification-dependency-lock-pins-v1','packageLockSha256':'sha256:'+'d'*64,'uvLockSha256':'sha256:'+'c'*64,'npmPackageCount':2,'uvPackageCount':2},
          'artifactPins':artifacts,'artifactReceiptSha256s':{x['artifactId']:'sha256:'+'a'*64 for x in artifacts}}
    plan['runPlanSha256']=run_plan_digest(plan); write(path_plan,plan)
    review=seal_review_draft({'schemaVersion':1,'reviewRevision':'rev10-production-benchmark-review-v1','reportId':'fixture-review','runPlanSha256':plan['runPlanSha256'],
       'inpaintingCandidates':{'inp-1':{'pagesReviewed':20,'humanScore':4.5,'criticalFailures':0}},
       'translation':{'pagesReviewed':30,'pagesByLanguage':{'en':20,'ja':3,'ko':3,'zh-Hans':2,'zh-Hant':2},'criticalFailures':0,'arabicNaturalnessMean':4.5,'adapterId':'external-ocr-text-only-v1','modelOrProviderRevision':'provider-v1','contextMode':'page-block-batch','privacyMode':'explicit-config-no-sfx'},
       'renderer':{'arabicRendererGoldensRun':24,'arabicRendererGoldensFailed':0,'adapterRevision':'pillow-raqm-ar-v1','fontArtifactId':'font','goldenSuiteRevision':'gold-v1'}})
    write(path_review,review)



def public_fixture(root:Path):
    mf=root/'public-controlled-release.json'
    value={'schemaVersion':2,'releaseId':'v1-public','sourceHeadSha':SOURCE,'qualifiedSourceHeadSha':SOURCE,'releaseClass':'public-v1','protocolMajor':1,'exactArtifactsOnly':True,'rebuildDuringPromotion':False,
           'extension':{'artifact':'extension.zip','sha256':'f'*64,'manifestVersion':'1.0.0'},
           'engines':[{'target':'linux-x86_64','artifact':'engine-linux.tar.gz','sha256':'2'*64},{'target':'macos-arm64','artifact':'engine-macos.pkg','sha256':'3'*64},{'target':'windows-x86_64','artifact':'engine-windows.zip','sha256':'4'*64}], 'metadata':[]}
    write(mf,value); msha=sha(mf)
    session_path=root/'public-evidence-promoted.json'
    session={'schemaVersion':1,'revision':'rev19-v1-evidence-orchestration-v2-public-store-closure','releaseId':'v1-public','releaseClass':'public-v1','stage':'evidence-promoted','sequence':5,
      'assemblySourceHeadSha':SOURCE,'qualifiedSourceHeadSha':SOURCE,
      'qualification':{'freezeSha256':'5'*64,'freezeIdentitySha256':'6'*64,'runPlanSha256':'7'*64,'packageLockSha256':'8'*64,'uvLockSha256':'9'*64},
      'controlled':{'manifestSha256':msha,'controlledRunId':100,'candidateRunIds':{'extension':101,'linux':102,'macos':103,'windows':104}},
      'nativeSmoke':{'engineSmokeRunId':200,'observations':{'linux-x86_64':'a'*64,'macos-arm64':'b'*64,'windows-x86_64':'c'*64}},
      'browserSmoke':{'observationsByMajor':{'148':'d'*64,'151':'e'*64}},
      'evidencePromotion':{'profilePrivacySha256':'1'*64,'smokeRecordsSha256':'2'*64,'releaseStateSha256':'3'*64},
      'previousSessionSha256':'4'*64}
    write_session(session_path,session); sess=json.loads(session_path.read_text())
    handoff_path=root/'store-handoff.json'
    handoff={'schemaVersion':1,'revision':'rev19-store-submission-handoff-v1','releaseId':'v1-public','releaseClass':'public-v1','assemblySourceHeadSha':SOURCE,'qualifiedSourceHeadSha':SOURCE,'orchestrationSessionSha256':sess['sessionSha256'],'controlledManifestSha256':msha,'extensionArtifact':'extension.zip','extensionSha256':'f'*64,'gate':'fixture','gatePassed':True}
    write_store_handoff(handoff_path,handoff); ho=json.loads(handoff_path.read_text())
    candidate_zip=root/'extension.zip'; candidate_zip.write_bytes(b'public-store-candidate')
    candidate_sha=sha(candidate_zip); value['extension']['sha256']=candidate_sha; write(mf,value); msha2=sha(mf)
    # Rebuild session/handoff after candidate SHA changes so all identities remain exact.
    session['controlled']['manifestSha256']=msha2; write_session(session_path,session); sess=json.loads(session_path.read_text())
    handoff['orchestrationSessionSha256']=sess['sessionSha256']; handoff['controlledManifestSha256']=msha2; handoff['extensionSha256']=candidate_sha; write_store_handoff(handoff_path,handoff); ho=json.loads(handoff_path.read_text())
    candidate_meta=root/'candidate.json'; write(candidate_meta,{'schemaVersion':2,'artifact':'extension.zip','sha256':candidate_sha,'testedSha256':candidate_sha,'byteIdenticalToTestedZip':True,'byteIdenticalToControlledExtension':True,'manifestVersion':'1.0.0','minimumChromeVersion':'148','firstPublishMode':'manual-dashboard','controlledManifestSha256':msha2,'storeSubmissionHandoffSha256':ho['handoffSha256']})
    def store_obs(path:Path,major:int):
      write(path,{'schemaVersion':2,'id':f'store-{major}','artifactManifestSha256':msha2,'orchestrationSessionSha256':sess['sessionSha256'],'storeSubmissionHandoffSha256':ho['handoffSha256'],'storeCandidateSha256':candidate_sha,'storeItemId':'a'*32,'storeVersion':'1.0.0','sourceHeadSha':SOURCE,'kind':'store-installed-extension','platform':'browser','artifact':'extension.zip','artifactSha256':candidate_sha,'engineTargetAtTest':'linux-x86_64','engineArtifactAtTest':'engine-linux.tar.gz','engineArtifactSha256AtTest':'2'*64,'browserVersion':f'{major}.0.0.1','testedAtUtc':'2026-08-20T00:00:00Z','cleanEnvironment':True,'checks':{'install':True,'activate':True,'translateFixture':True,'restore':True},'fixtureUrl':'http://127.0.0.1:4173/fixture.html','evidenceMode':'interactive-human-observed-store-installed-controlled-candidate'})
    o148=root/'store148.json'; o151=root/'store151.json'; store_obs(o148,148); store_obs(o151,151)
    return {'controlled-manifest':mf,'orchestration-session':session_path,'store-submission-handoff':handoff_path,'store-candidate-metadata':candidate_meta,'store-candidate-zip':candidate_zip,'store-observation-a':o148,'store-observation-b':o151}

def main():
  checks=0
  with tempfile.TemporaryDirectory(prefix='mte-manual-checkpoint-') as td0:
    td=Path(td0); mf=td/'controlled-release.json'; msha=manifest(mf); sess=td/'session.json'; ssha=native_session(sess,msha); b148=td/'b148.json'; b151=td/'b151.json'; browser(b148,msha,ssha,148); browser(b151,msha,ssha,151)
    evidence={'controlled-manifest':mf,'orchestration-session':sess,'browser-observation-a':b148,'browser-observation-b':b151}
    semantic=validate_exact_browser_smoke(evidence,source_head_sha=SOURCE,release_class='private-v1'); assert semantic['browserMajors']==[148,151]; checks+=1
    b150=td/'b150.json'; browser(b150,msha,ssha,150)
    try: validate_exact_browser_smoke({**evidence,'browser-observation-a':b150},source_head_sha=SOURCE,release_class='private-v1'); raise AssertionError('wrong browser set accepted')
    except ManualCheckpointError as exc: assert 'Chrome 148' in str(exc); checks+=1
    plan=td/'plan.json'; review=td/'review.json'; benchmark(plan,review); sem2=validate_benchmark_review({'run-plan':plan,'benchmark-review':review}); assert sem2['runPlanSha256'].startswith('sha256:'); checks+=1
    ledger={'releaseId':'v1-fixture','releaseClass':'private-v1','repository':'owner/repo','repositoryId':123,'currentSourceHeadSha':SOURCE,'authorizedOperatorIds':['12345']}
    cp=create_checkpoint(stage='chrome-148-and-stable-smoke',ledger=ledger,evidence=evidence,actor={'id':'12345','login':'release-operator'},semantic=semantic); validate_checkpoint(cp,stage='chrome-148-and-stable-smoke',ledger=ledger); validate_checkpoint_evidence(cp,evidence,ledger=ledger); checks+=1
    cp['semanticBinding']['browserMajors']=[148,150]
    try: validate_checkpoint(cp,stage='chrome-148-and-stable-smoke',ledger=ledger); raise AssertionError('tamper accepted')
    except ManualCheckpointError as exc: assert 'Sha256 mismatch' in str(exc); checks+=1
    snap=td/'actor.json'; write(snap,{'actor':{'id':'12345','login':'release-operator'},'repositoryId':123,'defaultBranch':'main','defaultBranchHeadSha':SOURCE}); actor,head=operator_and_head('owner/repo','main',None,snap,'2026-03-10',123); assert actor['id']=='12345' and head==SOURCE; checks+=1
    store_ev=public_fixture(td); store_sem=validate_store_installed_smoke(store_ev,source_head_sha=SOURCE,release_class='public-v1'); assert store_sem['browserMajors']==[148,151]; checks+=1
    store_ev['store-candidate-zip'].write_bytes(b'tampered')
    try: validate_store_installed_smoke(store_ev,source_head_sha=SOURCE,release_class='public-v1'); raise AssertionError('tampered store candidate accepted')
    except ManualCheckpointError as exc: assert 'candidate ZIP bytes' in str(exc); checks+=1
  print(f'Manual boundary checkpoint tooling: {checks}/8 passed'); return 0
if __name__=='__main__': raise SystemExit(main())

from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ENGINE_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ENGINE_ROOT))
from mte_engine.benchmark.acquisition import load_source_registry, source_for_artifact
from mte_engine.benchmark.catalog import artifact_by_id, load_catalog
from mte_engine.benchmark.manual_artifacts import load_manual_policy


def main()->int:
    ap=argparse.ArgumentParser(description='Verify manual-derived LaMa/AOT policy and the pinned Arabic-font source identity against the active catalog.')
    ap.add_argument('--catalog',type=Path,default=ENGINE_ROOT/'model-catalog/model-candidates-v1.json')
    ap.add_argument('--source-registry',type=Path,default=ENGINE_ROOT/'model-catalog/acquisition-source-registry-v3.json')
    ap.add_argument('--manual-policy',type=Path,default=ENGINE_ROOT/'model-catalog/manual-derived-artifact-policy-v1.json')
    a=ap.parse_args()
    catalog=load_catalog(a.catalog); by=artifact_by_id(catalog); reg=load_source_registry(a.source_registry); policy=load_manual_policy(a.manual_policy)
    for artifact_id,item in policy['artifacts'].items():
        cat=by.get(artifact_id)
        if not cat or cat.get('runtimeContract')!=policy['runtimeContract'] or cat.get('expectedFilename')!=item['expectedFilename']:
            raise SystemExit(f'manual-derived policy/catalog mismatch: {artifact_id}')
        src=source_for_artifact(reg,artifact_id)
        if src.get('mode')!='manual-derived' or src.get('expectedFilename')!=item['expectedFilename']:
            raise SystemExit(f'manual-derived source registry mismatch: {artifact_id}')
    font=by['noto-sans-arabic-production-font']; src=source_for_artifact(reg,'noto-sans-arabic-production-font')
    if font['upstreamRevision']!='NotoSansArabic-v2.013' or src['mode']!='https-zip-member' or src['upstreamRevision']!=font['upstreamRevision']:
        raise SystemExit('Noto Sans Arabic source identity is not pinned to the reviewed v2.013 release')
    print(json.dumps({'passed':True,'catalogRevision':catalog['catalogRevision'],'sourceRegistryRevision':reg['registryRevision'],'manualPolicyRevision':policy['policyRevision'],'manualDerivedArtifactIds':sorted(policy['artifacts']),'automatedFontArtifactId':'noto-sans-arabic-production-font'},indent=2))
    return 0
if __name__=='__main__': raise SystemExit(main())

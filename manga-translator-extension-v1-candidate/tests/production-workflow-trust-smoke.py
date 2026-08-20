from __future__ import annotations
import json, re, sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'release-control'/'production-execution-contract.json'

def main():
    c=json.loads(CONTRACT.read_text())
    trust=c['workflowTrust']; var=trust['operatorAllowlistVariable']; workflows=trust['productionWorkflows']
    assert trust['operatorAllowlistFormat']=='json-array-of-github-actor-id-strings' and var=='MTE_PRODUCTION_OPERATOR_ID_ALLOWLIST_JSON'
    # Every production job must independently enforce dispatch + default branch + stable actor id allowlist.
    for rel in workflows:
        data=yaml.safe_load((ROOT/rel).read_text())
        assert data.get('jobs')
        text=(ROOT/rel).read_text()
        assert 'run_intent_nonce:' in text and 'run-name:' in text and 'inputs.run_intent_nonce' in text, rel
        for name,job in data['jobs'].items():
            cond=str(job.get('if',''))
            for token in ['workflow_dispatch','github.event.repository.default_branch','github.actor_id',var,'inputs.run_intent_nonce']:
                assert token in cond, f'{rel}:{name} missing {token}'
    # Previously unprotected candidate-producing jobs are now protected before credentials/artifacts are touched.
    expected={
      '.github/workflows/acquire-production-ml-artifact.yml':'production-qualification',
      '.github/workflows/bootstrap-dependency-locks.yml':'production-qualification',
      '.github/workflows/release-extension.yml':'release-candidate',
      '.github/workflows/release-engine-linux.yml':'release-candidate',
    }
    for rel,env in expected.items():
        data=yaml.safe_load((ROOT/rel).read_text())
        assert all(job.get('environment')==env for job in data['jobs'].values()), rel
    # Qualification modes are distinguishable in immutable run provenance.
    q=(ROOT/'.github/workflows/qualify-production-ml-self-hosted.yml').read_text()
    assert 'run-name:' in q and 'inputs.mode' in q
    # Commit-transition ledger plans include PR creation+merge and the public Store/post-Store path.
    fr=c['firstRealRun']; private=fr['stagePlans']['private-v1']; public=fr['stagePlans']['public-v1']
    assert private.index('qualification-evidence-pr-created') < private.index('qualification-evidence-pr-merged') < private.index('qualification-evidence-checkout-reconciled') < private.index('exact-artifact-builds')
    for stage in ['store-candidate','store-installed-chrome-smoke','public-evidence-local-promotion','public-evidence-pr-merged']:
        assert stage in public
    assert public.index('public-evidence-pr-merged') < public.index('public-evidence-checkout-reconciled') < public.index('final-release-gate-and-capsule')
    # Every source transition is restricted to an explicit path allowlist and required files.
    for stage in fr['sourceCommitTransitionStages']:
        hint=fr['stageLaunchHints'][stage]; allow=fr['sourceTransitionAllowlists'][hint['allowlist']]
        assert allow['paths'] and allow['requiredPaths'] and set(allow['requiredPaths']) <= set(allow['paths'])
    print('Production workflow trust tooling: 7/7 passed')
    return 0
if __name__=='__main__': raise SystemExit(main())

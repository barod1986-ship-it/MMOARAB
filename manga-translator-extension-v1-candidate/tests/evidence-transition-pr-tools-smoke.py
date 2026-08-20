from __future__ import annotations

import base64
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'scripts' / 'evidence_transition_pr.py'
CONTRACT = ROOT / 'release-control' / 'production-execution-contract.json'


def load():
    spec = importlib.util.spec_from_file_location('mte_evidence_pr_smoke', TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    m = load(); contract = json.loads(CONTRACT.read_text())
    ledger = {
        'releaseId':'v1.0.0-rc1','releaseClass':'private-v1','repository':'owner/repo','repositoryId':123,
        'defaultBranch':'main','currentSourceHeadSha':'a'*40,'authorizedOperatorIds':['12345']
    }
    with tempfile.TemporaryDirectory(prefix='mte-evidence-pr-') as td0:
        td = Path(td0); old_root = m.ROOT; m.ROOT = td
        try:
            (td/'release-control').mkdir(parents=True)
            (td/'release-control/v1-orchestration.json').write_text('{"ok":true}\n')
            (td/'SOURCE_SHA256SUMS.txt').write_text('fixture\n')
            changed=['release-control/v1-orchestration.json','SOURCE_SHA256SUMS.txt']
            old_verify = m.H.verify_local_promotion; m.H.verify_local_promotion=lambda stage,led,c: list(changed)

            # 1. Pending plan is content-addressed to exact local bytes and deterministic branch intent.
            pending=m.pending_snapshot('release-evidence-local-promotion',ledger,contract,'mte-pr-'+'1'*32)
            assert pending['changedPaths']==changed and pending['files'][changed[0]]['sha256']==m.sha256_bytes((td/changed[0]).read_bytes())
            assert pending['branch'].startswith('evidence/release-evidence/v1.0.0-rc1-aaaaaaaaaaaa-')
            m.validate_pending(pending,'release-evidence-local-promotion',ledger,contract)

            # 2. Local-byte drift invalidates a sealed pending PR before any remote call.
            (td/'SOURCE_SHA256SUMS.txt').write_text('changed\n')
            try: m.validate_pending(pending,'release-evidence-local-promotion',ledger,contract); raise AssertionError('drift accepted')
            except m.EvidencePrError as exc: assert 'no longer matches' in str(exc)
            (td/'SOURCE_SHA256SUMS.txt').write_text('fixture\n')

            # 3. Exact remote byte verification accepts only the sealed head/paths/parent/bytes.
            head='b'*40
            pr={'number':7,'html_url':'https://github.com/owner/repo/pull/7','base':{'ref':'main'},'head':{'ref':pending['branch'],'sha':head}}
            expected=pending['files']
            def fake_get(url, token, version):
                if '/pulls/7/files' in url: return [{'filename':x,'status':'modified'} for x in changed]
                if f'/commits/{head}' in url: return {'sha':head,'parents':[{'sha':'a'*40}]}
                if '/contents/' in url:
                    rel=url.split('/contents/',1)[1].split('?ref=',1)[0]
                    from urllib.parse import unquote
                    raw=(td/unquote(rel)).read_bytes()
                    return {'type':'file','encoding':'base64','content':base64.b64encode(raw).decode()}
                raise AssertionError(url)
            old_get=m.api_get; m.api_get=fake_get
            got=m.verify_created_pr(ledger=ledger,stage='release-evidence-local-promotion',pr=pr,expected_head_sha=head,expected_branch=pending['branch'],expected_files=expected,contract=contract,token='t',version='v')
            assert got['prNumber']==7 and got['headSha']==head and got['files']==expected

            # 4. Remote-byte tampering is rejected even with the same PR path set and head SHA.
            def tamper_get(url,token,version):
                if '/contents/' in url: return {'type':'file','encoding':'base64','content':base64.b64encode(b'tampered').decode()}
                return fake_get(url,token,version)
            m.api_get=tamper_get
            try: m.verify_created_pr(ledger=ledger,stage='release-evidence-local-promotion',pr=pr,expected_head_sha=head,expected_branch=pending['branch'],expected_files=expected,contract=contract,token='t',version='v'); raise AssertionError('tamper accepted')
            except m.EvidencePrError as exc: assert 'remote file bytes' in str(exc)
            m.api_get=old_get

            # 5. Recovery path reuses the sealed branch/PR and does not synthesize a second commit.
            calls={'commit':0,'post':0}
            old_assert=m.assert_operator_and_repo; old_ref=m.get_ref_sha; old_find=m.find_pr_for_branch; old_verify_pr=m.verify_created_pr; old_commit=m.create_commit_from_files; old_req=m.api_request
            m.assert_operator_and_repo=lambda *a,**k:{'id':'12345','login':'release-operator'}
            m.get_ref_sha=lambda *a,**k: head
            m.find_pr_for_branch=lambda *a,**k:[pr]
            m.verify_created_pr=lambda **k:{'prNumber':7,'url':pr['html_url'],'headRef':pending['branch'],'headSha':head,'baseRef':'main','baseSha':'a'*40,'allowlist':'release-smoke-evidence','changedPaths':changed,'files':expected}
            def should_not_commit(*a,**k): calls['commit']+=1; raise AssertionError('recovery created commit')
            m.create_commit_from_files=should_not_commit
            m.api_request=lambda *a,**k:(calls.__setitem__('post',calls['post']+1) or (500,None))
            recovered=m.create_or_recover(ledger=ledger,stage='release-evidence-local-promotion',pending=pending,contract=contract,token='t',version='v')
            assert recovered['prNumber']==7 and calls=={'commit':0,'post':0}
            m.assert_operator_and_repo=old_assert; m.get_ref_sha=old_ref; m.find_pr_for_branch=old_find; m.verify_created_pr=old_verify_pr; m.create_commit_from_files=old_commit; m.api_request=old_req

            # 6. A PR whose head commit is not a direct child of the ledger source is rejected.
            m.api_get=fake_get
            bad=dict(pr); bad['head']=dict(pr['head']); bad_head='c'*40; bad['head']['sha']=bad_head
            def bad_parent_get(url,token,version):
                if '/pulls/7/files' in url: return [{'filename':x,'status':'modified'} for x in changed]
                if f'/commits/{bad_head}' in url: return {'sha':bad_head,'parents':[{'sha':'9'*40}]}
                return fake_get(url,token,version)
            m.api_get=bad_parent_get
            try: m.verify_created_pr(ledger=ledger,stage='release-evidence-local-promotion',pr=bad,expected_head_sha=bad_head,expected_branch=pending['branch'],expected_files=expected,contract=contract,token='t',version='v'); raise AssertionError('wrong parent accepted')
            except m.EvidencePrError as exc: assert 'single-parent child' in str(exc)

            m.H.verify_local_promotion=old_verify
        finally:
            m.ROOT=old_root
    print('Evidence transition PR tooling: 6/6 passed')
    return 0

if __name__=='__main__': raise SystemExit(main())

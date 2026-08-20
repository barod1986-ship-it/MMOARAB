from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'scripts' / 'reconcile_first_real_run_checkout.py'


def load():
    spec = importlib.util.spec_from_file_location('mte_reconcile_smoke', TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(['git', *args], cwd=repo, text=True, capture_output=True)
    if p.returncode:
        raise AssertionError(p.stdout + p.stderr)
    return p.stdout.strip()


def fixture(td: Path):
    repo = td / 'repo'; repo.mkdir(parents=True)
    git(repo, 'init', '-b', 'main'); git(repo, 'config', 'user.email', 'release@example.invalid'); git(repo, 'config', 'user.name', 'Release Test')
    (repo/'scripts').mkdir(); (repo/'release').mkdir()
    (repo/'app.txt').write_text('base\n'); (repo/'evidence.json').write_text('{"state":"base"}\n'); (repo/'SOURCE_SHA256SUMS.txt').write_text('fixture\n')
    git(repo, 'add', '.'); git(repo, 'commit', '-m', 'base'); before=git(repo,'rev-parse','HEAD')
    (repo/'evidence.json').write_text('{"state":"merged"}\n'); (repo/'SOURCE_SHA256SUMS.txt').write_text('merged-manifest\n')
    git(repo,'add','evidence.json','SOURCE_SHA256SUMS.txt'); git(repo,'commit','-m','evidence merge'); target=git(repo,'rev-parse','HEAD')
    git(repo,'reset','--hard',before)
    git(repo,'remote','add','origin','git@github.com:owner/repo.git'); git(repo,'update-ref','refs/remotes/origin/main',target)
    ledger={'repository':'owner/repo','repositoryId':123,'defaultBranch':'main','currentSourceHeadSha':target}
    merge={'stage':'release-evidence-pr-merged','sourceHeadShaBefore':before,'sourceHeadShaAfter':target,'pullRequest':{'mergeCommitSha':target,'changedPaths':['evidence.json','SOURCE_SHA256SUMS.txt']}}
    return repo, ledger, merge, before, target


def noop_verify(_: Path):
    return None


def main():
    m=load()
    assert m.normalize_repo_from_origin('git@github.com:owner/repo.git')=='owner/repo'
    assert m.normalize_repo_from_origin('https://github.com/owner/repo.git')=='owner/repo'
    with tempfile.TemporaryDirectory(prefix='mte-reconcile-') as raw:
        td=Path(raw)
        # 1. clean pre-merge checkout fast-forwards exactly.
        repo,ledger,merge,before,target=fixture(td/'a')
        r=m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False)
        assert r['previousHeadSha']==before and r['reconciledHeadSha']==target and git(repo,'rev-parse','HEAD')==target

        # 2. dirty reviewed paths are accepted only when bytes already equal the reviewed merge.
        repo,ledger,merge,before,target=fixture(td/'b')
        (repo/'evidence.json').write_text('{"state":"merged"}\n'); (repo/'SOURCE_SHA256SUMS.txt').write_text('merged-manifest\n')
        r=m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False)
        assert set(r['dirtyReviewedPathsBefore'])=={'evidence.json','SOURCE_SHA256SUMS.txt'} and git(repo,'status','--porcelain')==''

        # 3. unexpected source dirt blocks before HEAD movement.
        repo,ledger,merge,before,target=fixture(td/'c'); (repo/'app.txt').write_text('unexpected\n')
        try: m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False); raise AssertionError('expected rejection')
        except m.ReconcileError as e: assert 'outside the reviewed merge transition' in str(e)
        assert git(repo,'rev-parse','HEAD')==before

        # 4. reviewed path with non-target bytes blocks before reset.
        repo,ledger,merge,before,target=fixture(td/'d'); (repo/'evidence.json').write_text('{"state":"tampered"}\n')
        try: m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False); raise AssertionError('expected rejection')
        except m.ReconcileError as e: assert 'differs from the reviewed merge commit bytes' in str(e)
        assert git(repo,'rev-parse','HEAD')==before

        # 5. staged changes are always rejected even on an allowlisted path.
        repo,ledger,merge,before,target=fixture(td/'e'); (repo/'evidence.json').write_text('{"state":"merged"}\n'); git(repo,'add','evidence.json')
        try: m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False); raise AssertionError('expected rejection')
        except m.ReconcileError as e: assert 'staged/index changes' in str(e)

        # 6. operational untracked release artifacts are preserved and never git-cleaned.
        repo,ledger,merge,before,target=fixture(td/'f'); (repo/'release'/'controlled.json').write_text('{}\n')
        r=m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False)
        assert (repo/'release'/'controlled.json').read_text()=='{}\n' and 'release/controlled.json' in r['preservedOperationalUntracked']

        # 7. already reconciled target is idempotent.
        r2=m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False)
        assert r2['previousHeadSha']==target and r2['reconciledHeadSha']==target

        # 8. origin mismatch is rejected before any checkout mutation.
        repo,ledger,merge,before,target=fixture(td/'g'); git(repo,'remote','set-url','origin','git@github.com:other/repo.git')
        try: m.reconcile_checkout(repo_root=repo,ledger=ledger,merge_record=merge,verify_source_integrity=noop_verify,fetch=False); raise AssertionError('expected rejection')
        except m.ReconcileError as e: assert 'differs from sealed ledger repository' in str(e)
    print('Local checkout reconciliation: 8/8 passed')
    return 0

if __name__=='__main__': raise SystemExit(main())
